"""Reconstruct the existing development poses on measured four-second hold references."""
import argparse
import hashlib
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from learning.b0.contact_events import FrozenDoorReference
from learning.b0.physics import build, settings
from scripts.b0.register_contact_dev import prefix_history, prefix_source, valid_initial


def check_recording(original, extended, model, expected_extra_steps):
    old = FrozenDoorReference.from_episode(original, model)
    new = FrozenDoorReference.from_episode(extended, model)
    start, end = old.phase_bounds['hold']
    if new.phase_bounds['hold'] != (start, end + expected_extra_steps):
        raise ValueError(f'{extended}: unexpected measured hold duration')
    for path, count in [('substeps/qpos',end+1), ('substeps/qvel',end+1),
                        ('substeps/physical_target',end), ('substeps/ctrl',end),
                        ('substeps/finger_load_N',end), ('action_clipped',(end+9)//10)]:
        a, b = (np.load(root/(path+'.npy'),mmap_mode='r')[:count] for root in (original, extended))
        if not np.array_equal(a,b):
            raise ValueError(f'{extended}: {path} changed before the v1 hold endpoint')
    return new, dict(original_hold_start=start, original_hold_end=end, measured_hold_end=end+expected_extra_steps,
                     old_prefix_identical=True, actual_extra_physics_steps=expected_extra_steps)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text())
    frozen=Path(plan['previous_manifest'])
    if mj.__version__!='3.3.0' or hashlib.sha256(frozen.read_bytes()).hexdigest()!=plan['previous_manifest_sha256']:
        raise ValueError('Original native backend or registered manifest differs from the plan')
    previous=json.loads(frozen.read_text())
    results=dict(version='contact_dev_hold_margin_v2', registration_plan=str(args.plan),
                 registered_from=str(frozen), source=plan['source'], nominal_in_twenty=False,
                 physical_backend=f'native MuJoCo {mj.__version__}', cases={})
    for name in plan['cases']:
        side,segment=name.split('/')
        group=previous['cases'][name]
        cfg=settings('push' if side=='push' else 'mobile',1)
        model=build(cfg)
        ref_path=Path(plan['source'])/group['episode']
        original=Path(plan['previous_source'])/group['episode']
        if json.loads((ref_path/'config.json').read_text())['grip_hold_s']!=plan['teacher_continuous_hold_s']:
            raise ValueError(f'{ref_path}: measured hold differs from plan')
        ref, audit=check_recording(original,ref_path,model,plan['extra_physical_steps'])
        start=ref.phase_bounds[group['phases'][0]][0]//10*10
        if start!=group['start_substep'] or len(group['accepted'])!=20:
            raise ValueError(f'{name}: start or comparison cases differ')
        arrays=prefix_source(ref_path)
        new={k:group[k] for k in ('episode','phases','start_substep','target_deg','hold_seconds')}
        if new['hold_seconds']!=plan['judge_continuous_hold_s']:
            raise ValueError('Policy criterion differs from the plan')
        new.update(measured=audit,accepted=[])
        for case in [group['nominal'],*group['accepted']]:
            _,_,observed=prefix_history(model,cfg,ref_path,side,start,case['perturbation'],arrays)
            if not valid_initial(observed,segment,cfg):
                raise ValueError(f"{name}/{case['id']} is invalid on the newly measured source: {observed}")
            row=dict(id=case['id'],perturbation=case['perturbation'],geometry=observed,valid=True)
            if 'draw' in case:
                row['draw']=case['draw']
                new['accepted'].append(row)
            else:
                new['nominal']=row
        results['cases'][name]=new
    with args.output.open('x') as stream:
        json.dump(results,stream,indent=2,allow_nan=False)
        stream.write('\n')


if __name__=='__main__':
    main()
