"""Frozen online-policy 256-lane development block. No optimizer calls or training feedback."""
import argparse
import csv
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
from learning.b0.physics import WHEELS
from scripts.b0.official_flow import NEW_SEGMENT, OUT, RAW, PARENT_RAW, build, io, stats
from scripts.b0.fit_contact_model import prediction_errors

SEEDS = {u:825001 for u in (5000,10000,15000)} if NEW_SEGMENT else {1000:821001,3000:823001,5000:825001}


@torch.no_grad()
def collect(u):
    base = PARENT_RAW if u==1000 else RAW
    small = OUT/'current_policy'/f'u{u:06}'
    raw = RAW/'current_policy'/f'u{u:06}'
    if (small/'scores.json').exists() or (raw/'lanes_000001.npz').exists():
        raise FileExistsError('Independent development block already sampled')
    raw.mkdir(exist_ok=True,parents=True)
    p = base/f'checkpoint_{u:06}.pt'
    package = torch.load(p,weights_only=False,map_location='cpu')
    saved = torch.load(base/f'resume_{u:06}'/'state.pt',weights_only=False,map_location='cpu',mmap=True)
    io.write(small/'registration.json',dict(checkpoint=str(p),seed=SEEDS[u],lanes=256,ticks=64,
        max_intervals=16384,scope='independent development only',freeze_all_normalizers=True, sampler_source=str(base/f'resume_{u:06}/state.pt'),
        actual_event_phase=None, rng_scope='independent process', common_initial_states_asserted=False))
    run,_ = build(package['cfg'] | {'worlds':256})
    for name in ('dyn','actor','critic'):
        getattr(run,name).load_state_dict(package[name])
    for name in ('value','count','effort','probabilities'):
        setattr(run.sampler,name,saved['sampler'][name].to(run.device).clone())
    del saved
    old = stats(run)
    run.compact_directory=raw
    np.random.seed(SEEDS[u])
    torch.manual_seed(SEEDS[u])
    with patch.object(run.actor,'update_normalization',return_value=None),patch.object(run.learners[7],'update_normalization',return_value=None):
        for _ in range(64):
            run.collect()
    assert stats(run)==old and io.optimizer_steps(run)==dict(wm=0,actor=0,critic=0)
    tick=torch.arange(64,device=run.device).expand(256,64)
    lanes=torch.arange(256,device=run.device)[:,None].expand_as(tick)
    data=run.replay.get(lanes,tick,('state','next_state','action','sim_ctx','episode','valid','terminated','truncated','motion_time'))
    quantities={}
    for key in ('prefix','finger_min','rejected_prefix'):
        vals=[]
        for file in sorted(raw.glob('lanes_*.npz')):
            with np.load(file) as arrays:
                vals.append(arrays[key][0])
        quantities[key]=torch.tensor(np.stack(vals,axis=1),device=run.device)
    dual=(quantities['finger_min']>run.plant.cfg['contact_threshold_n']).all(-1)
    legal=data['valid']
    assert run.simulated==16384 and int(legal.sum())==run.total
    torch.save(dict(arrays={k:v.cpu() for k,v in data.items()},true_dual=dual.cpu()),raw/'development.pt')
    run.dyn.eval()
    rows=[]
    stratified=[]
    if NEW_SEGMENT:
        from learning.b0.contact_warp import PHASES
        ep=data['episode'].cpu().numpy()
        age=np.zeros_like(ep)
        for t in range(1,64):
            age[:,t]=np.where(ep[:,t]==ep[:,t-1], age[:,t-1]+1, 0)
        frame=data['motion_time']
        refid=torch.searchsorted(run.bank.motion_ends,frame.contiguous(),right=True).cpu().numpy()
        refphase=run.phases[frame,0].cpu().numpy()
        paths=package['cfg']['reference_paths']
    wheel=torch.tensor([31+run.model.joint(n).dofadr.item() for n in WHEELS],device=run.device)
    for h in (1,7,32):
        end=65-h
        select=legal.unfold(1,h,1).all(-1) & (data['episode'][:,:end]==data['episode'][:,h-1:])
        ix=select.nonzero()
        metrics=[]
        for i,t in (batch.T for batch in ix.split(512) if len(batch)):
            x=data['state'][i,t]
            aux,r=run.rep.extract_aux_state(x),run.rep.represent(x)
            for j in range(h):
                aux,r=run.dyn(r,data['action'][i,t+j],aux,data['sim_ctx'][i,t])
            metrics.append(prediction_errors(run.rep,aux,r,data['next_state'][i,t+h-1],wheel)['tcp_mm'])
        values=torch.cat(metrics) if metrics else torch.empty(0,device=run.device)
        il,it=ix.T
        if NEW_SEGMENT and len(ix):
            a,b=il.cpu().numpy(),it.cpu().numpy()
            ids=np.stack([data['sim_ctx'][il,it,0].long().cpu().numpy(),refid[a,b],refphase[a,b],age[a,b]],axis=1)
            groups, inverse=np.unique(ids,axis=0,return_inverse=True)
            y=values.cpu().numpy()
            start_dual=dual[il,it].cpu().numpy()
            entire=dual.unfold(1,h,1)[il,it].all(-1).cpu().numpy()
            for j,(side_id,clip,ph,age_ticks) in enumerate(groups):
                in_group=inverse==j
                for label,mask in [('all',in_group),('dual_start',in_group & start_dual),
                                   ('dual_entire',in_group & entire)]:
                    val=y[mask]
                    stratified.append(dict(h=h,side=('pull','push')[side_id],reference_id=Path(paths[clip]).name,
                        reference_phase=PHASES[ph],actual_event_phase='NA',start_episode_age_ticks=int(age_ticks),
                        physical_contact_stratum=label,n=len(val),tcp_p95_mm=float(np.percentile(val,95)) if len(val) else None))
        for side in (0,1):
            mask=data['sim_ctx'][il,it,0]==side
            for label,flag in [('all',mask),('two_finger_start',mask & dual[il,it]),
                               ('two_finger_entire_window',mask & dual.unfold(1,h,1)[il,it].all(-1))]:
                v=values[flag].cpu().numpy()
                rows.append(dict(h=h,side=('pull','push')[side],stratum=label,n=len(v),
                    tcp_p95_mm=float(np.percentile(v,95)) if len(v) else None))
    if stratified:
        with (small/'strata.csv').open('w',newline='') as stream:
            w=csv.DictWriter(stream,fieldnames=list(stratified[0]),lineterminator='\n')
            w.writeheader()
            w.writerows(stratified)
    io.write(small/'scores.json',dict(seed=SEEDS[u],policy_intervals=16384,prefix=int(quantities['prefix'].sum()),
        rejected_prefix_endpoints=int(quantities['rejected_prefix'].sum()),valid=run.total,
        terminal_valid=int((legal & data['terminated']).sum()),two_finger_valid=int((legal & dual).sum()),
        optimizer_steps=io.optimizer_steps(run),rows=rows,source=str(raw/'development.pt')))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('node',type=int,choices=SEEDS)
    collect(p.parse_args().node)
