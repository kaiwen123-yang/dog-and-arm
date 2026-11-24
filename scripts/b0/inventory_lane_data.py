"""Inventory held-command data by physical lane, split, side and reference phase."""
import argparse
import json
from pathlib import Path

import numpy as np


def inventory(directories, native):
    buckets = {}
    def add(source, group, split, side, phase, action, loads, forces, valid):
        for label in np.unique(phase):
            mask = (phase == label) & valid
            if not mask.any():
                continue
            key=(source,split,side,str(label))
            row=buckets.setdefault(key,dict(episodes=0,h1=0,h7=0,h32=0,dual_h1=0,
                min_finger_n=[float('inf')]*2,max_finger_n=[0.]*2,peak_net_door_n=0.,
                action_min=[float('inf')]*23,action_max=[-float('inf')]*23))
            row['episodes']+=1
            row['dual_h1']+=int((loads[mask]>.01).all(axis=(1,2)).sum())
            for h in (1,7,32):
                if len(valid)>=h:
                    legal=np.lib.stride_tricks.sliding_window_view(valid,h).all(axis=-1)
                    row['h'+str(h)]+=int((legal & mask[:len(legal)]).sum())
            for field,values,op in [('min_finger_n',loads[mask].min(axis=(0,1)),np.minimum),
                         ('max_finger_n',loads[mask].max(axis=(0,1)),np.maximum),
                         ('action_min',action[mask].min(axis=0),np.minimum),('action_max',action[mask].max(axis=0),np.maximum)]:
                row[field]=op(row[field],values).tolist()
            row['peak_net_door_n']=max(row['peak_net_door_n'],float(np.linalg.norm(forces[mask],axis=-1).max()))
    def get(path,field):
        return np.load(path/(field+'.npy'),mmap_mode='r')
    eligibility=[]
    for path in sorted(native.iterdir()):
        meta=json.loads((path/'metadata.json').read_text())
        valid=get(path,'valid_full_interval')
        n=len(valid) if valid.all() else int(np.flatnonzero(~valid)[0])
        phase=np.asarray(meta['phases'])[get(path,'substeps/phase')[:10*n:10]]
        add(native.name,path.name,meta['wm_split'],meta['task'],phase,get(path,'action_clipped')[:n],
            get(path,'substeps/finger_load_N')[:10*n].reshape(n,10,2),
            get(path,'substeps/door_robot_force_N')[:10*n].reshape(n,10,3),valid[:n])
        if path.name in ('pull_0_train_grip','push_0_train_grip','pull_5_train','push_5_train','pull_15_train','push_15_train'):
            use=np.isin(phase,['approach_arm','grasp','open','hold','release','retreat_arm','post_release_hold'])
            ii=np.arange(n)
            eligibility.append(dict(reference=path.name,total=n,phase_allowed=int(use.sum()),
               prefix_excluded=int((use&(ii<11)).sum()),tail_excluded=int((use&(ii>=n-73)).sum()),
               eligible=int((use&(ii>=11)&(ii<n-73)).sum())))
    for directory in directories:
        reg=json.loads((directory/'registration.json').read_text())
        src=json.loads((Path(reg['anchor']).parent/'actual_config.json').read_text())['cfg']
        phase_bank,side_bank=[],[]
        for name in src['references']:
            path=Path(reg['reference_directory'])/name
            meta=json.loads((path/'metadata.json').read_text())
            n=int(get(path,'valid_full_interval').sum())
            ph=np.asarray(meta['phases'])[get(path,'substeps/phase')[:10*n:10]]
            phase_bank.extend([*ph,ph[-1]])
            side_bank.extend([meta['task']]*(n+1))
        for row in json.loads((directory/'cohorts.json').read_text()):
            path=Path(row['path'])
            valid=get(path,'valid')
            frames=get(path,'frame')
            ph=np.asarray(phase_bank)[frames]
            side=np.asarray(side_bank)[frames[0]]
            action,fg,force=[get(path,s) for s in ('clipped','sub_finger_load_N','sub_door_robot_force_N')]
            for j in range(valid.shape[1]):
                add(directory.name,(row['seed'],j),row['split'],side[j],ph[:,j],action[:,j],fg[:,j],force[:,j],valid[:,j])
    return dict(definition='Counts by starting phase; H7/H32 require complete windows in one lane. Dual means both fingers above 0.01N throughout all ten substeps.',
                eligible_standard=eligibility,rows=[dict(source=s,split=k,side=x,phase=p,**r) for (s,k,x,p),r in buckets.items()])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native',type=Path,required=True)
    p.add_argument('--cohorts',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(inventory(a.cohorts,a.native),indent=2,allow_nan=False)+'\n')
