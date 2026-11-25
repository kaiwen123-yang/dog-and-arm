"""Rebuild the first unshifted inputs on the steady evaluation path and evaluate each distinct Actor input once."""
from pathlib import Path
import numpy as np
import torch
from learning.b0.contact_policy import sensor, build_actor, build_actor_obs_td
from scripts.b0.pregrasp_alias import (
    CKPT, DEVICE, RAW, REF, OUT, DoorMotions, RobotRepresentation, actor_goal_schema,
    case_at, full_state, make_model, read, tensor, write)



@torch.inference_mode()
def run():
    parent=torch.load(CKPT,map_location=DEVICE,weights_only=False)
    rep=RobotRepresentation(make_model(),DEVICE)
    cfg=parent['cfg']
    bank=DoorMotions([REF/'pull_60_train',REF/'push_25_train'],rep,DEVICE,
                     actor_schema=actor_goal_schema(cfg),reference_tail=cfg['reference_tail'])
    frame=588
    _,raw,_,ref,_=case_at(10000,'warp','pull')
    q,v,a=(np.load(raw/(name+'.npy'),mmap_mode='r') for name in ('qpos','qvel','clipped_action'))
    source=q[frame-9:frame+1].copy()
    v=tensor(v[frame-9:frame+1],DEVICE)
    previous=tensor(a[frame-10:frame],DEVICE)
    t=torch.tensor([bank.starts[ref.name]+frame],device=DEVICE)
    probe={}
    for label,dx in (('cold_unshifted',0),('second_xplus',.05),('steady_unshifted',0)):
        h=source.copy()
        h[:,0]+=dx
        qh=tensor(h,DEVICE)
        hist=sensor(rep,full_state(qh,v),previous)[None]
        _,goal=bank.goals(rep,t,qh[-1:,:7],qh[-1:,31])
        probe[label]=(hist.cpu().numpy(),goal.cpu().numpy())
    p=RAW/'alias_pull_588.npz'
    data=dict(np.load(p))
    for src,tag in (('cold_unshifted','base'),('second_xplus','x+')):
        for x,key in zip(probe[src],('raw_history','raw_goal')):
            np.testing.assert_array_equal(x,data[tag+'_'+key])
    # Even without forwarding either command, the first run's strict zero assertion
    # must fail at x+: its reconstructed raw history and goal already differ.
    assert not np.array_equal(probe['cold_unshifted'][1],probe['second_xplus'][1])
    doc=read(OUT/'input_alias.json')
    for label in ('x+','x-','y+','y-'):
        for x,key in zip(probe['steady_unshifted'],('raw_history','raw_goal')):
            np.testing.assert_array_equal(x,data[label+'_'+key])
    doc['initial_failed_pass']=dict(query_count=2,failed_at='pull 588 x+',reason='Exact zero against cold first evaluation. Source-input-only fresh process reproduces both tensors bit-for-bit and proves first failing raw-input assertion independent of motor output.',counterexample_raw_goal_max_abs=float(np.max(abs(probe['cold_unshifted'][1]-probe['second_xplus'][1]))))
    if doc.get('direct_query_count_total')==27:
        return
    actor,_=build_actor(rep,cfg,make_model(),DEVICE)
    actor.load_state_dict(parent['actor'],strict=True)
    actor.eval()
    def infer_inputs(inputs):
        hist,goal=(tensor(x,DEVICE) for x in inputs)
        obs=build_actor_obs_td({'motion':goal},hist)
        return actor.raw(obs).cpu().numpy()
    base= infer_inputs(probe['cold_unshifted'])
    xy= infer_inputs(probe['steady_unshifted'])
    assert np.max(np.abs(base-data['base_command_raw']))<2e-5
    for row in doc['rows']:
        if row['side']!='pull' or row['frame']!=588:
            continue
        label=row['variant']
        if label=='base' or label in ('x+','x-','y+','y-'):
            cmd=base if label=='base' else xy
            if label=='base':
                row['max_abs_raw_command_vs_archived']=float(np.max(abs(base-data['base_command_raw'])))
            row['action_source']='direct query on saved raw tensors' if label in ('base','x+') else 'identical raw tensors; shared direct x+ output'
            data[label+'_command_raw']=cmd
            data[label+'_command_clipped']=cmd.clip(-1,1)
        cmd=data[label+'_command_raw']
        row['max_abs_delta']['command_raw']=float(np.max(abs(cmd-base)))
        row['max_abs_delta']['command_clipped']=float(np.max(abs(cmd.clip(-1,1)-base.clip(-1,1))))
    np.savez_compressed(p,**data)
    doc['direct_query_count_total']=27
    doc.pop('previous_interrupted_first_anchor_query_count_range',None)
    doc.pop('total_direct_queries_range',None)
    doc['first_anchor_recheck']=dict(first_two_input_arrays_reproduced=True,
        steady_unshifted_vs_each_xy_raw_input_exact=True,extra_unique_input_forwards=2,
        interpretation='Task inputs exactly equal in steady computation, cold-vs-steady differences are also reproduced with zero translation. Two new forwards on the two distinct raw input pairs. Three redundant XY queries reuse the exact same query result.')
    write('input_alias.json',doc)


if __name__=='__main__':
    run()
