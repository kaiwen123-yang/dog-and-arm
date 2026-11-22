"""Measure which transferred action block causes the first-step grasp force spike."""
import argparse
import json
from pathlib import Path
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from learning.b0.contact_events import FrozenDoorReference, ContactEvents
from learning.b0.physics import ActionMap, build, settings
from scripts.b0.register_contact_dev import prefix_history

# Each counterfactual changes only these B0-03 output channels from the
# physically replayed 20 ms source target. No counterfactual is a policy score.
BLOCKS = dict(teacher=(), actor_all=tuple(range(23)), actor_arm=tuple(range(16,22)),
              actor_jaw=(22,), actor_legs_wheels=tuple(range(16)),
              actor_except_arm=(*range(16),22))


def trial(side,path,case_path):
    cfg=settings('mobile' if side=='pull' else 'push',1)
    result=json.loads((case_path/'result.json').read_text())
    ref_id=result['episode']
    episode=path / ref_id
    start=result['start_substep']
    cfg['target_angle_deg']=5
    m=build(cfg)
    a=ActionMap(m)
    ref=FrozenDoorReference.from_episode(episode,m)
    actor0=np.load(Path(result['raw_directory'])/'clipped_action.npy')[0]
    teacher0=np.load(episode/'action_clipped.npy')[start//10]
    rows=[]
    for name,indices in BLOCKS.items():
        action=teacher0.copy()
        ids=list(indices)
        action[ids]=actor0[ids]
        d,_,_=prefix_history(m,cfg,episode,side,start,result['perturbation'])
        judge=ContactEvents(m,cfg,side,ref,phases=['open','hold'],hold_seconds=3.,start_step=start)
        target=(a.offset+a.scale*action)*a.finger_factor
        net=[]
        for _ in range(10):
            q0,v0=d.qpos.copy(),d.qvel.copy()
            d.ctrl[a.actuator_ids]=target + d.qfrc_bias[a.dof]*a.bias_gain
            mj.mj_step(m,d)
            c=judge.meter.measure(d)
            net.append(float(np.linalg.norm(c.door_force)))
            if judge.observe(d,c,q0,v0):
                break
        rows.append(dict(intervention=name,actor_channels=ids,first_net_door_force_n=net[0],
                         peak_net_door_force_n=max(net),substeps=len(net),failure=judge.failure))
    return dict(side=side,absolute_start_substep=start,reference=ref_id,rows=rows,
                first_actor_minus_teacher_physical_target=((actor0-teacher0)*a.scale).tolist(),
                channel_names=a.names)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('evaluation',type=Path)
    p.add_argument('--references',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if not args.output.parent.is_dir():
        args.output.parent.mkdir(parents=True)
    audit=dict(mujoco=mj.__version__,evaluation=str(args.evaluation),
               protocol='native first 20 ms, stop on first hard event; source action versus independently swapped frozen Actor blocks',
               trials=[trial(side,args.references,args.evaluation/side/'open_5/nominal') for side in ('pull','push')])
    with args.output.open('x') as f:
        json.dump(audit,f,indent=2,allow_nan=False)
        f.write('\n')
    for side in audit['trials']:
        for r in side['rows']:
            print(side['side'],r['intervention'],round(r['first_net_door_force_n'],3),r['substeps'],
                  r['failure']['reason'] if r['failure'] else 'no hard event')
