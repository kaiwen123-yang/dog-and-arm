"""Run frozen B0 free-motion trials on the pinned GPU training physics backend."""
import argparse
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def failure_event(plant, world):
    import torch
    audit = plant.contact_audit
    data = plant.data
    arm = data.qpos[world, plant.arm_q]
    margin = torch.minimum(arm - plant.arm_limits[:, 0], plant.arm_limits[:, 1] - arm)
    w, x, y, z = data.qpos[world, 3:7].detach().cpu().numpy()
    roll = np.arctan2(2*(w*x+y*z), 1-2*(x*x+y*y))
    pitch = np.arcsin(np.clip(2*(w*y-z*x), -1., 1.))
    measurements = dict(min_arm_margin_rad=margin.min().item(), max_abs_tilt_deg=float(np.rad2deg(
                        max(abs(roll), abs(pitch)))), wheel_loads_n=audit.wheel_loads_n[world].cpu().tolist(),
                        contiguous_unloaded_steps=int(audit.unloaded_steps[world]),
                        unexpected_normal_n=float(audit.peak_other_normal_n[world]),
                        door_force_norm_sum_n=float(audit.door_force_norm_sum_n[world]),
                        max_saturation_time_s=plant.saturation_time[world].max().item(),
                        overflow_bits=int(audit.overflow_bits[world]), nefc=int(data.nefc[world]))
    reasons = []
    if measurements['min_arm_margin_rad'] < 0:
        reasons.append('arm_joint_limit')
    if (measurements['unexpected_normal_n'] > audit.contact_limit or
            measurements['door_force_norm_sum_n'] > audit.contact_limit):
        reasons.append('unexpected_contact')
    if measurements['max_abs_tilt_deg'] >= 5:
        reasons.append('tilt')
    if measurements['contiguous_unloaded_steps'] >= audit.max_unloaded_steps:
        reasons.append('wheel_unloaded')
    if measurements['max_saturation_time_s'] >= .25:
        reasons.append('saturation')
    if measurements['overflow_bits'] & audit.buffer_mask or measurements['nefc'] > plant.sim.wp_data.njmax:
        reasons.append('solver_capacity')
    if not (torch.isfinite(data.qvel[world]).all() and torch.isfinite(data.qpos[world]).all()):
        reasons.append('nonfinite_state')
    # Preserve numerical failures in JSON without fabricating a finite reading.
    for key, value in measurements.items():
        if isinstance(value, list):
            measurements[key] = [v if np.isfinite(v) else None for v in value]
        elif not np.isfinite(value):
            measurements[key] = None
    return dict(reason='|'.join(reasons) if reasons else 'solver_audit', **measurements)


def trial_batch(run, plant, reference_name, cases, output_dir, measures):
    import torch
    from learning.b0.evaluate import case_initial_qpos, score_tracking
    from learning.b0.model import full_state, tensor
    episode = run.refs[reference_name]
    steps = len(episode['t']) - 1
    start = int(run.starts[run.motion.motion_names.index(reference_name)])
    count = len(cases)
    init = np.stack([case_initial_qpos(run.model, episode['qpos'][0], case) for case in cases])
    velocity = np.repeat(episode['qvel'][0:1], count, axis=0)
    plant.reset(tensor(init, run.device), tensor(velocity, run.device))
    done = torch.zeros(count, dtype=torch.bool, device=run.device)
    reasons = [None] * count
    terminal_step = [None] * count
    events = [None] * count
    q_world = [[q.copy()] for q in plant.data.qpos[:].cpu().numpy()]
    v_world = [[v.copy()] for v in plant.data.qvel[:].cpu().numpy()]
    times = [[0.] for _ in cases]
    actions = [[] for _ in cases]
    dt = float(run.model.opt.timestep)
    previous = run.motion.prev[start].expand(count, -1).clone()
    history = None
    first_action_difference = None
    for k in range(steps):
        actual_state = full_state(plant.data.qpos[:], plant.data.qvel[:])
        sensor = run.sensor(actual_state, previous)[:, None]
        history = (sensor.expand(-1, 10, -1) if history is None else
                   torch.cat([history[:, 1:], sensor], dim=1))
        clock = torch.full((count,), start+k, dtype=torch.int64, device=run.device)
        policy = run.actor(run.actor_obs(actual_state, clock, history)).clamp(-1, 1)
        command = torch.where(done[:, None], previous, policy)
        if k == 0:
            single = run.policy_factory(reference_name, episode)
            single_action = single(q_world[0][0], v_world[0][0], 0)
            first_action_difference = np.max(np.abs(command[0].cpu().numpy() - single_action)).item()
        command_np = command.cpu().numpy()
        for i in range(count):
            if terminal_step[i] is None:
                actions[i].append(command_np[i].copy())
        def record(substep, invalid):
            just_failed = torch.where(invalid & ~done)[0]
            if len(just_failed) == 0:
                return
            abs_step = 10*k + substep
            for i in just_failed.cpu().tolist():
                event = failure_event(plant, i)
                reasons[i], terminal_step[i], events[i] = event['reason'], abs_step, event
                q_world[i].append(plant.data.qpos[i].cpu().numpy().copy())
                v_world[i].append(plant.data.qvel[i].cpu().numpy().copy())
                times[i].append(abs_step*dt)
            done[just_failed] = True
        plant.step(command, on_substep=record)
        q, v = plant.data.qpos[:].cpu().numpy(), plant.data.qvel[:].cpu().numpy()
        for i in range(count):
            if terminal_step[i] is None:
                q_world[i].append(q[i].copy())
                v_world[i].append(v[i].copy())
                times[i].append((k+1)*10*dt)
        previous = command
        if done.all():
            break
    rows = []
    for i, case in enumerate(cases):
        q, v = np.asarray(q_world[i]), np.asarray(v_world[i])
        obs = dict(qpos=q, qvel=v, tcp_world=measures.tcp_world(q), t=np.asarray(times[i]))
        count_steps = steps*10 if terminal_step[i] is None else terminal_step[i]
        row = score_tracking(run.model, obs, episode, physics_steps=count_steps, failure_reason=reasons[i],
                             measures=measures)
        row.update(reference_id=reference_name, case=case['id'], seed=run.seed, checkpoint=run.checkpoint,
                   solver_first_failure=events[i])
        stem = f"{reference_name}_{case['id']}"
        dump(output_dir / f'{stem}.json', row)
        raw = run.raw / 'physical' / stem
        raw.mkdir(parents=True, exist_ok=False)
        for key, value in obs.items():
            np.save(raw / f'{key}.npy', value)
        np.save(raw / 'action_clipped.npy', np.asarray(actions[i]))
        rows.append(row)
    return rows, first_action_difference


def evaluate(args):
    import mujoco as mj
    import torch
    from importlib.metadata import version
    from learning.b0.evaluate import ErrorMeasures, PROTOCOL, write_case_summary
    from learning.b0.research_env import ResearchPlant
    from learning.b0.training import FreeRun
    if Path(args.run).name != args.run or args.run in ('', '.', '..'):
        raise ValueError('run must be a new directory name')
    ckpt = torch.load(args.checkpoint, map_location='cuda:0', weights_only=True)
    torch.set_float32_matmul_precision('high')
    run = FreeRun(ckpt['cfg'], args.run, ckpt['seed'])
    run.warmstart()
    run.actor.load_state_dict(ckpt['actor'])
    run.actor.eval()
    run.updates = int(ckpt['updates'])
    run.checkpoint = str(args.checkpoint)
    del ckpt
    output_dir = ROOT / 'results/b0' / args.run
    physical = output_dir / 'physical'
    physical.mkdir(parents=True, exist_ok=False)
    cases = ([dict(id='nominal', dx_m=0., dy_m=0., dyaw_deg=0.)] if args.nominal
             else PROTOCOL['cases'])
    plant = ResearchPlant(run.model, len(cases), run.device)
    measures = ErrorMeasures(run.model)
    rows, difference = [], {}
    with torch.no_grad():
        for ref in run.refs:
            trials, delta = trial_batch(run, plant, ref, cases, physical, measures)
            rows.extend(trials)
            difference[ref] = delta
    write_case_summary(rows, physical, run.refs, cases)
    dump(output_dir / 'evaluation.json', dict(backend='mjlab_research.Simulation (MuJoCo-Warp)',
         mujoco=mj.__version__, mujoco_warp=version('mujoco-warp'), gpu=torch.cuda.get_device_name(),
         actor_updates=run.updates, seed=run.seed, checkpoint=run.checkpoint, manifest=PROTOCOL['version'],
         protocol='Every 2 ms substep audited, state and all triggers retained at first failure. Failed worlds stay in the batch with held last control; later states never enter case score. No reset within trial.',
         policy='batched deterministic frozen Actor, no exploration noise', batch=len(cases),
         first_world_max_initial_action_difference_vs_single=difference, raw=str(run.raw.relative_to(ROOT))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--checkpoint', required=True, type=Path)
    parser.add_argument('--nominal', action='store_true', help='Use only three unperturbed diagnostic cases')
    args = parser.parse_args()
    os.environ.setdefault('TORCH_COMPILE_DISABLE', '1')
    evaluate(args)
