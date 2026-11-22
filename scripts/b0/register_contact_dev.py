"""Register supported physical contact-segment RSI conditions before policy evaluation."""
import argparse
import json
from pathlib import Path
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from learning.b0.contact_events import FrozenDoorReference
from learning.b0.evaluate import case_initial_qpos
from learning.b0.physics import ActionMap, ContactMeter, build, settings

# Nominal uses exactly zero perturbation, outside the 20 development rows.
SEGMENTS = {
    'approach_grasp': (0, ('approach_arm','grasp')),
    'stable_grip': (0, ('hold',)),
    'open_5': (5, ('open','hold')),
    'open_15': (15, ('open','hold')),
    'release_retreat': (5, ('release','retreat_arm','post_release_hold')),
}
PREFIX_STEPS = 100
SEED = 20261122
RANGES = dict(dx_m=.0005, dy_m=.0005, dyaw_deg=.025)


def prefix_history(model, cfg, path, side, start, perturbation, arrays=None, integrator=None):
    """Physically rebuild 10 real prior policy frames; return live data for evaluation.

    'start' is the aligned absolute substep at which the policy takes control.
    Prefix frames contain actual initial states and previously applied actions,
    in chronological order. The returned final state is the first policy input.
    """
    if start < PREFIX_STEPS+10 or start % 10 != 0:
        raise ValueError('RSI boundary must admit ten complete prior held actions')
    if arrays is None:
        arrays = prefix_source(path)
    states, velocities, targets, actions = arrays
    d = mj.MjData(model)
    mapping = ActionMap(model)
    meter = ContactMeter(model, 'preview_floor','front' if side=='pull' else 'back',
                         cfg['contact_threshold_n'],cfg['wheel_threshold_n'])
    lo = start-PREFIX_STEPS
    # Compliant target penetration already occurs in the accepted held teacher.
    # Perturbations may not deepen it beyond the unperturbed source at this index.
    nominal_geometry=mj.MjData(model)
    nominal_geometry.qpos[:]=states[lo]
    nominal_geometry.qvel[:]=velocities[lo]
    mj.mj_forward(model,nominal_geometry)
    finger_bodies=set(meter.fingers)
    nominal_depth=0.
    for c in nominal_geometry.contact:
        g1,g2=map(int,c.geom)
        if (g1==meter.rod and model.geom_bodyid[g2] in finger_bodies) or (g2==meter.rod and model.geom_bodyid[g1] in finger_bodies):
            nominal_depth=max(nominal_depth,float(-c.dist))
    d.qpos[:] = case_initial_qpos(model,states[lo],perturbation)
    d.qvel[:] = velocities[lo]
    mj.mj_forward(model,d)
    # Geometric admission at the prior-state perturbation, including contacts
    # without positive solved force. Compliant target-finger contact is allowed.
    illegal = set()
    initial_penetration = 0.
    for c in d.contact:
        if c.dist >= 0:
            continue
        g1,g2 = map(int,c.geom)
        if not meter.robot[g1]:
            g1,g2 = g2,g1
        if not meter.robot[g1]:
            continue
        if g2 == meter.floor and model.geom_bodyid[g1] in meter.wheels:
            continue
        if meter.is_door[g2] and meter._door_pair(g1,g2)[1] is not None:
            initial_penetration = max(initial_penetration,float(-c.dist))
        else:
            illegal.add(f'{meter.names[g1]}/{meter.names[g2]}')
    warm_q, warm_v, warm_last = [], [], []
    bad = set(illegal)
    for j in range(lo, start):
        if j % 10 == 0:
            warm_q.append(d.qpos.copy())
            warm_v.append(d.qvel.copy())
            warm_last.append(actions[j//10-1].copy())
            servo = targets[j//10] * mapping.finger_factor
        if integrator is None:
            d.ctrl[mapping.actuator_ids] = servo + d.qfrc_bias[mapping.dof] * mapping.bias_gain
            mj.mj_step(model,d)
        else:
            if j == lo:
                integrator.reset(d)
            integrator.step(d, servo)

        contacts = meter.measure(d)
        bad.update(contacts.unexpected)
    actual = np.linalg.norm(d.site_xpos[model.site('p4_grasp').id] -
                            d.site_xpos[model.site(cfg['handle_site']).id])
    jaw = d.joint('piper_gripper_joint1').qpos[0] - d.joint('piper_gripper_joint2').qpos[0]
    metrics=dict(unexpected=sorted(bad),both=bool(contacts.both),width_m=float(jaw),grasp_error_m=float(actual),
                 supported=bool(contacts.supported.all()),finger_n=contacts.finger_normal.tolist(),
                 door_force_sum_n=float(contacts.force_norm_sum),
                 prefix_start_target_penetration_m=initial_penetration, nominal_prefix_start_target_penetration_m=nominal_depth,
                 solver_warning=bool(any(w.number for w in d.warning)),
                 finite=bool(np.isfinite(d.qpos).all() and np.isfinite(d.qvel).all()))
    return d, (np.asarray(warm_q),np.asarray(warm_v),np.asarray(warm_last),actions[start//10-1].copy()), metrics


def prefix_source(path):
    return tuple(np.load(path / name,mmap_mode='r') for name in
                 ('substeps/qpos.npy','substeps/qvel.npy','physical_target.npy','action_clipped.npy'))


def valid_initial(metrics, segment, cfg):
    if metrics['unexpected'] or metrics['solver_warning'] or not metrics['finite'] or not metrics['supported']:
        return False
    if segment == 'approach_grasp':
        return metrics['door_force_sum_n'] <= cfg['contact_threshold_n'] and metrics['prefix_start_target_penetration_m']==0
    low,high = cfg['grasp_width_range_m']
    return (metrics['both'] and low <= metrics['width_m'] <= high and
            metrics['grasp_error_m'] <= cfg['grasp_error_m'] and metrics['prefix_start_target_penetration_m'] <= metrics['nominal_prefix_start_target_penetration_m']+1e-9)


def register(directory, output):
    result=dict(version='contact_dev_v1',physics=f'native MuJoCo {mj.__version__}',seed=SEED,
                perturbation_uniform_symmetric=RANGES, source=str(directory),
                perturbation_applied_at='200 ms before fixed aligned segment start, then integrate ten recorded held actions',
                prefix_history='10 actual qpos/qvel and previous clipped action observations; prefix excluded from event times',
                nominal_in_twenty=False, identity='development only; each segment/side screened separately',
                criteria='At prefix start allow wheel/ground and target-finger only; target penetration no deeper than the unperturbed source at the same prefix step (1 nm numerical tolerance). All 100 subsequent solved intervals free of unexpected force, endpoint four loaded wheels. Approach requires no door contact; all other segments require both real fingers, 12-35 mm jaw, <=5 mm TCP distance.',
                cases={})
    rng=np.random.default_rng(SEED)
    for side in ('pull','push'):
        cfg=settings('mobile' if side=='pull' else 'push',1)
        m=build(cfg)
        for segment,(goal,phases) in SEGMENTS.items():
            name = f'{side}_{goal}_train' + ('_grip' if goal == 0 else '')
            path=directory / name
            reference=FrozenDoorReference.from_episode(path,m)
            start=reference.phase_bounds[phases[0]][0] // 10 * 10
            arrays=prefix_source(path)
            group=f'{side}/{segment}'
            rows=dict(episode=path.name,phases=list(phases),start_substep=start,target_deg=goal,
                      hold_seconds=3.,accepted=[],excluded=[])
            zero={k:0. for k in RANGES}
            _,_,observed=prefix_history(m,cfg,path,side,start,zero,arrays)
            rows['nominal']=dict(id='nominal',perturbation=zero,geometry=observed,
                                 valid=valid_initial(observed,segment,cfg))
            if not rows['nominal']['valid']:
                raise ValueError(f'{group} nominal initial state failed: {observed}')
            attempt=0
            while len(rows['accepted']) < 20 and attempt < 2000:
                attempt+=1
                perturbation={k:float(rng.uniform(-r,r)) for k,r in RANGES.items()}
                _,_,observed=prefix_history(m,cfg,path,side,start,perturbation,arrays)
                row=dict(draw=attempt,perturbation=perturbation,geometry=observed)
                if valid_initial(observed,segment,cfg):
                    rows['accepted'].append(dict(id=f"D{len(rows['accepted'])+1:02}",**row))
                else:
                    rows['excluded'].append(row)
            result['cases'][group]=rows
            print(group,start,len(rows['accepted']),len(rows['excluded']),flush=True)
            if len(rows['accepted'])<20:
                raise ValueError(f'{group} could not register 20 legal initial states')
    with output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    register(args.directory,args.output)
