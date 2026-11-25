"""Compare held-action 20 ms responses in native physics and the frozen learned model."""
import argparse
import copy
import json
from pathlib import Path

import numpy as np


CHANNELS = (('wheel_rate_rad_s', 12, 35), ('arm_J2_rad', 17, 17), ('jaw_width_m', 22, 22))
PERTURBATION = .03
PREFIX_TICKS = 5


def native(root):
    import mujoco as mj
    from learning.multimodal.sensors import RobotSensors
    from p6_contacts import ContactMeter
    from p6_scene import build
    from scripts.multimodal.collect import load_scenes, teacher_config
    scenes = {x['id']: x for x in load_scenes()['scenes']}
    rows = []
    steps = 0
    for path in sorted(root.rglob('metadata.json')):
        meta = json.loads(path.read_text())
        if meta.get('split') != 'validation' or meta['source'] != 'P6_held_20ms':
            continue
        def arr(k):
            return np.load(path.parent / (k+'.npy'), mmap_mode='r')
        cfg = teacher_config(meta['side'], meta['target_deg'], scenes[meta['scene_id']])
        model = build(cfg)
        sensors = RobotSensors(model, cfg['handle_site'])
        mapping = sensors.mapping
        meter = ContactMeter(model, 'preview_floor', handle_side='front' if meta['side']=='pull' else 'back')
        q, v, commands = arr('qpos'), arr('qvel'), arr('applied_ctrl')
        phase = np.asarray(meta['phases'])[arr('phase')]
        for group, mask in (('free_approach', phase == 'approach_base'),
                            ('two_finger_open', (phase == 'open') & (arr('both_contact_fraction') > 0))):
            eligible = np.flatnonzero(mask & arr('valid_transition'))
            i = int(eligible[len(eligible)//2])
            d = mj.MjData(model)
            d.qpos[:], d.qvel[:], d.time = q[i-PREFIX_TICKS], v[i-PREFIX_TICKS], arr('t')[i-PREFIX_TICKS]
            mj.mj_forward(model, d)
            for cmd in commands[i-PREFIX_TICKS:i].reshape(-1, 23):
                d.ctrl[mapping.actuator_ids] = cmd
                mj.mj_step(model, d)
                steps += 1
            prefix_dq = float(np.max(np.abs(d.qpos-q[i])))
            prefix_dv = float(np.max(np.abs(d.qvel-v[i])))
            # Preserve the warm solver history, restore the exact measured q/v boundary.
            d.qpos[:], d.qvel[:], d.time = q[i], v[i], arr('t')[i]
            mj.mj_forward(model, d)
            baseline = arr('action_clipped')[i]
            for name, action_index, sensor_index in CHANNELS:
                endpoints = []
                for sign in (-1., 1.):
                    changed = np.array(baseline, dtype=float)
                    changed[action_index] = np.clip(changed[action_index]+sign*PERTURBATION, -1, 1)
                    fork = copy.copy(d)
                    target = (mapping.offset + mapping.scale*changed)*mapping.finger_factor
                    dual = 0
                    for _ in range(10):
                        fork.ctrl[mapping.actuator_ids] = target + fork.qfrc_bias[mapping.dof]*mapping.bias_gain
                        mj.mj_step(model, fork)
                        dual += int(meter.measure(fork).both)
                        steps += 1
                    p = sensors.proprio(fork.qpos, fork.qvel)
                    o = sensors.object_state(fork.qpos, fork.qvel)
                    endpoints.append(dict(action=float(changed[action_index]), response=float(p[sensor_index]),
                                          hinge_rad=float(o[0]), rod_tcp_m=o[2:].tolist(), dual_fraction=dual/10))
                rows.append(dict(episode=meta['episode_id'], mode=group, tick=i, channel=name,
                                 action_index=action_index, sensor_index=sensor_index, native=endpoints,
                                 prefix_qpos_max_abs=prefix_dq, prefix_qvel_max_abs=prefix_dv))
    if not rows:
        raise ValueError('No held-out teacher episodes for native response comparison')
    return dict(native_mujoco=mj.__version__, dt_s=.020, requested_delta_action=PERTURBATION,
                prefix_ticks=PREFIX_TICKS, total_native_substeps=steps, rows=rows)


def compare(physical, wm, root, device):
    import torch
    from learning.multimodal.wm_replay import PhysicalReplay
    from learning.multimodal.world_model import PerceptualDynamics
    data = PhysicalReplay(root, 'validation', device)
    meta = torch.load(wm, map_location=device, weights_only=False)
    model = PerceptualDynamics(meta['width']).to(device)
    model.load_state_dict(meta['model'])
    model.eval()
    by_channel = {}
    with torch.no_grad():
        for row in physical['rows']:
            ep = next(e for e in data.episodes if e['id'] == row['episode'])
            ix = ep['start'] + row['tick']
            # The physical fork consumes the same measured history and teacher action.
            b = data.window(torch.tensor([ix, ix], device=device), 1)
            st = model.initial(b['history'], b['previous_history'], b['vision'][:, 0])
            action = b['a'][:, 0].clone()
            for sign, actual in enumerate(row['native']):
                action[sign, row['action_index']] = actual['action']
            nxt = model.step(st, action, b['prev'][:, 0])
            p = model.sensor(nxt)[:, row['sensor_index']].cpu().tolist()
            obj = nxt.obj.cpu().tolist()
            dual = nxt.contact_logits[:, 2].sigmoid().cpu().tolist()
            row['wm'] = [dict(action=a['action'], response=x, hinge_rad=o[0], rod_tcp_m=o[2:],
                              dual_fraction=c) for a, x, o, c in zip(row['native'], p, obj, dual)]
            dn = row['native'][1]['response'] - row['native'][0]['response']
            dw = p[1] - p[0]
            row['native_response_difference'] = dn
            row['wm_response_difference'] = dw
            score = by_channel.setdefault(row['channel'], dict(rows=0, native_resolved=0, sign_agrees=0))
            score['rows'] += 1
            if abs(dn) > 1e-7:
                score['native_resolved'] += 1
                score['sign_agrees'] += int(dn*dw > 0)
    return {**physical, 'wm':str(wm), 'wm_updates':meta.get('updates', meta.get('wm_updates')),
            'by_channel':by_channel, 'resolution_in_physical_units':1e-7}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', required=True, type=Path)
    p.add_argument('--native', type=Path, required=True)
    p.add_argument('--wm', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--device', default='cuda')
    args = p.parse_args()
    if args.wm:
        if args.out is None:
            p.error('--out is required for the modeled comparison')
        out = args.out
        result = compare(json.loads(args.native.read_text()), args.wm, args.data, args.device)
    else:
        out = args.native
        result = native(args.data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(physical_substeps=result['total_native_substeps'], comparisons=len(result['rows']),
                          by_channel=result.get('by_channel'))), flush=True)


if __name__ == '__main__':
    main()
