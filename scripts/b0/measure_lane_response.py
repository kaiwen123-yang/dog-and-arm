"""Frozen stable-grip entry on Warp. Perturb only the first held command."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.models import Dynamics
from learning.b0.contact_model import ContactRepresentation, contact_context, contact_state
from learning.b0.contact_warp import ContactPlant, PHASE_ID
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, make_model


@torch.no_grad()
def measure(run, update, wm_files):
    device='cuda:0'
    model=make_model()
    rep=ContactRepresentation(model,device)
    mapping=ActionMap(model)
    predictors=[]
    for file in wm_files:
        ck=torch.load(file,map_location='cpu',weights_only=False)
        hidden=ck['hidden'] if 'hidden' in ck else ck['cfg']['wm_hidden']
        dyn=Dynamics(rep,23,5,tensor(mapping.scale,device),tensor(mapping.offset,device),tuple(hidden)).to(device)
        dyn.load_state_dict(ck['dyn'])
        predictors.append(dyn.eval())
    rows=[]
    for side,protocol in [('pull','v1'),('push','hold_margin_v2')]:
        formal=Path('results/b0')/f'{run}_u{update}_warp_{protocol}'/side/'stable_grip/nominal/result.json'
        case=json.loads(formal.read_text())
        ref=Path('results/raw_large/b0/contact_held_r1')/case['episode']
        t,shift=divmod(case['start_substep'],10)
        if shift: raise ValueError('Non-aligned registered start')
        get=lambda k: np.load(ref/(k+'.npy'),mmap_mode='r')
        actions=tensor(np.array(get('action_clipped')[t-10:t+32]),device)
        obs_action=np.load(Path(case['raw_directory'])/'clipped_action.npy')[0]
        # Use the current actual Actor and measured held reference as two first-command centers.
        branches=[]
        for center,base in [('reference',actions[10]),('policy',tensor(obs_action,device))]:
            branches.extend([(center,'center',0.,base),(center,'repeat',0.,base)])
            for index,deltas in [(17,[.001,.01]),(22,[.00025,.001])]:
                for delta in deltas:
                    for sign in [-1,1]:
                        cmd=base.clone()
                        cmd[index]+=sign*delta/mapping.scale[index]
                        if cmd.abs().max()>1: continue
                        branches.append((center,mapping.names[index],sign*delta,cmd))
        n=len(branches)
        plant=ContactPlant(model,n,device)
        side_bit=torch.full((n,),int(side=='push'),device=device,dtype=torch.long)
        phase_names=json.loads((ref/'metadata.json').read_text())['phases']
        subph=np.array([PHASE_ID[p] for p in phase_names])[get('substeps/phase')[10*(t-10):10*(t+32)]].reshape(42,10)
        phase=torch.as_tensor(subph,device=device)
        q0=tensor(np.array(get('qpos')[t-10]),device).expand(n,-1)
        v0=tensor(np.array(get('qvel')[t-10]),device).expand(n,-1)
        plant.reset(q0,v0)
        for j in range(10):
            ev=plant.step_contact(actions[j].expand(n,-1),side_bit,phase[j].expand(n,-1))
            if (ev['first_fail_substep']>0).any(): raise ValueError('Failed physical prefix')
        # Start all diagnostic branches from lane zero's realized physical prefix.
        # The other independent prefix integrations can differ on a batched contact solve.
        import warp as wp
        for name in ('qpos','qvel','qacc_warmstart','ctrl','time'):
            values=wp.to_torch(getattr(plant.sim.wp_data,name))
            values.copy_(values[0:1].clone().expand_as(values))
        if model.na:
            values=wp.to_torch(plant.sim.wp_data.act)
            values.copy_(values[0:1].clone().expand_as(values))
        for values in (plant.load_ticks,plant.lost_ticks,plant.slip_ticks,plant.sat_ticks):
            values.copy_(values[0:1].clone().expand_as(values))
        plant.sim.forward()
        state=contact_state(plant.data.qpos[:].clone(),plant.data.qvel[:].clone())
        start_spread=float((state-state[0]).abs().max())
        assert start_spread == 0.
        forecasts=[(state[:,:7],rep.represent(state)) for _ in predictors]
        context=contact_context(model,side,device).expand(n,-1)
        first=torch.zeros(n,dtype=torch.long,device=device)
        for j in range(32):
            cmd=torch.stack([br[3] for br in branches]) if j==0 else actions[10+j].expand(n,-1)
            ev=plant.step_contact(cmd,side_bit,phase[10+j].expand(n,-1),measure_peak_force=True)
            tick=ev['first_fail_substep']
            first=torch.where((first==0)&(tick>0),10*j+tick,first)
            if not ev['valid_full_interval'].all(): raise ValueError('Invalid physical branch')
            forecasts=[dyn(r,cmd,a,context) for dyn,(a,r) in zip(predictors,forecasts)]
            if j+1 not in (1,7,32): continue
            actual=contact_state(plant.data.qpos[:],plant.data.qvel[:])
            outputs=[(actual[:,:7],rep.represent(actual)),*forecasts]
            def geometry(a,r):
                q=rep.reconstruct_full_state(a,r)
                return torch.cat((q[:,61:62],rep.tcp_pose(a,q[:,7:31])[0],q[:,29:30]-q[:,30:31]),1).cpu().tolist()
            values=[geometry(a,r) for a,r in outputs]
            for b,(center,channel,delta,_) in enumerate(branches):
                rows.append(dict(side=side,source=str(formal),entry_frame=t,initial_state_max_spread=start_spread,
                    center=center,channel=channel,delta_physical=delta,h=j+1,
                    first_failure_tick=int(first[b]),interval_peak_force_n=float(ev['peak_force_n'][b]),
                    warp=values[0][b],wm=[v[b] for v in values[1:]]))
    return dict(wm=[str(f) for f in wm_files],outputs=['door_rad','tcp_x_m','tcp_y_m','tcp_z_m','opening_m'],
                protocol='Registered 100-substep physical prefix. Vary first 20ms only; subsequent measured reference commands shared. Integrate after failure for response diagnostics only.',rows=rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True)
    p.add_argument('--update',required=True,type=int)
    p.add_argument('--wm',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    result=measure(a.run,a.update,a.wm)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
