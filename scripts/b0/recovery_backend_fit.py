"""Fit six arm decoder rows on clock-aligned physical teacher labels for both support regimes."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions, build_actor, sensor
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import ActionMap, make_model
from scripts.b0.recovery_backend_probe import DEFAULT_SOURCE

ARM = slice(16,22)
NAMES = ('pull_60_train','push_25_train')
CONTACT_PHASES = ('pregrasp','approach_arm','grasp','open','hold','release','retreat_arm','post_release_hold')


def clock_signals(episode, count):
    meta = json.loads((episode/'metadata.json').read_text())
    if (not meta['success'] or meta['wm_split'] != 'train' or not meta['held_action_replay']
            or not meta['full_task'] or not np.load(episode/'valid_full_interval.npy')[:count].all()):
        raise ValueError('Expected successful complete 20 ms physical teacher train frames')
    ticks = np.load(episode/'physics_step.npy', mmap_mode='r')[:count]
    if not np.array_equal(ticks, np.arange(count)*10):
        raise ValueError('Clock alignment requires regular, complete source frames')
    phase = np.array(meta['phases'])[np.load(episode/'phase.npy',mmap_mode='r')[:count]]
    pos, rot = [np.load(episode/'substeps'/fname,mmap_mode='r')[ticks] for fname in
                ('tcp_goal_world_m.npy','tool_goal_world_R.npy')]
    return phase, pos, rot


@torch.no_grad()
def features(episode,frames,bank,rep,actor):
    frame_ids = torch.tensor(frames, dtype=torch.long)
    q,v,a = [tensor(np.load(episode/(f+'.npy'),mmap_mode='r').copy(),'cpu')
             for f in ('qpos','qvel','last_action')]
    obs = sensor(rep,full_state(q,v),a)
    data, raw = [], []
    def capture(_layer, args):
        data.append(args[0].double())
    hook = actor.decoder[-1].register_forward_pre_hook(capture)
    try:
        for ix in frame_ids.split(256):
            history = obs[(ix[:,None]+torch.arange(-9,1)).clamp_min(0)]
            _, goal = bank.goals(rep,ix+bank.starts[episode.name],q[ix,:7])
            raw.append(actor.raw(build_actor_obs_td({'motion':goal},history))[:,ARM].double())
    finally:
        hook.remove()
    X = torch.cat(data)
    X = torch.cat((X, torch.ones(len(X),1,dtype=X.dtype)),dim=1)
    y = tensor(np.load(episode/'action_clipped.npy',mmap_mode='r')[frames,ARM].copy(),'cpu').double()
    return X, torch.cat(raw), y


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--warp-reference',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--native-teacher',type=Path,default=Path('results/raw_large/b0/full_native_margin_r1'))
    p.add_argument('--run',required=True)
    args=p.parse_args()
    if Path(args.run).name != args.run:
        p.error('Choose a fresh run name')
    out=Path('results/b0')/args.run
    out.mkdir(parents=True,exist_ok=False)
    ck=torch.load(args.checkpoint,map_location='cpu',weights_only=False)
    m=make_model()
    rep=RobotRepresentation(m,'cpu')
    bank=DoorMotions([args.warp_reference/n for n in NAMES],rep,'cpu')
    actor,_=build_actor(rep,ck['cfg'],m,'cpu')
    actor.load_state_dict(ck['actor'],strict=True)
    actor.eval()
    units=actor.standard_action[ARM].detach().double()
    phys=torch.tensor(ActionMap(m).scale[ARM],dtype=torch.double)
    spec=dict(variant='six_arm_rows_clock_matched_teacher',source=str(args.checkpoint),
              fixed_reference=str(args.warp_reference),native_teacher=str(args.native_teacher),
              status='supervision only; zero additional H32. No evaluation episode is a label.',
              frozen='All network parameters and normalizers except last six arm output rows and their biases; unchanged WM/Critic.',
              objective='Per-side equally weighted mean native label squared error at same-clock agreed target poses plus equal mean squared change from frozen Warp Actor at all Warp teacher states; ridge 1e-4 on decoder correction. Analytic solve, no checkpoint selection.',
              filter='same absolute frame/phase, manipulated phases, teacher world TCP goal distance <= 2 mm and angular distance <= 1 degree. All source actions real applied 20ms commands.',
              sources={},metrics={},ridge=1e-4)
    (out/'protocol.json').write_text(json.dumps(spec,indent=2)+'\n')
    sets=[]
    for name in NAMES:
        warp,native=args.warp_reference/name,args.native_teacher/name
        wlen=int(np.load(warp/'valid_full_interval.npy').sum())
        n=min(wlen,int(np.load(native/'valid_full_interval.npy').sum()))
        wp,wt,wR=clock_signals(warp,n)
        np_,nt,nR=clock_signals(native,n)
        dx=np.linalg.norm(wt-nt,axis=1)
        dr=np.rad2deg(np.arccos(np.clip(((wR*nR).sum((1,2))-1)/2,-1,1)))
        keep=(wp==np_)&np.isin(wp,CONTACT_PHASES)&(dx<=.002)&(dr<=1.)
        spec['sources'][name]=dict(warp_frames=wlen,native_overlap=n,native_accepted=int(keep.sum()),
            native_by_phase={s:int((keep&(wp==s)).sum()) for s in CONTACT_PHASES},
            native_open_goal_distance_median_m=float(np.median(dx[(wp==np_)&(wp=='open')])))
        X,pred,y=features(native,np.flatnonzero(keep),bank,rep,actor)
        sets.append((name+'_native',X,pred,y))
        X,pred,_=features(warp,np.arange(wlen),bank,rep,actor)
        sets.append((name+'_warp_anchor',X,pred,pred))
    dim=sets[0][1].shape[1]
    mat=torch.eye(dim,dtype=torch.double)*spec['ridge']
    rhs=torch.zeros(dim,6,dtype=torch.double)
    for _,X,pred,y in sets:
        mat+=X.T@X/len(X)
        rhs+=X.T@((y-pred)/units)/len(X)
    delta=torch.linalg.solve(mat,rhs)
    with torch.no_grad():
        actor.decoder[-1].weight[ARM]+=delta[:-1].T.float()
        actor.decoder[-1].bias[ARM]+=delta[-1].float()
    for label,X,pred,y in sets:
        post=pred+(X@delta)*units
        spec['metrics'][label]=dict(count=len(X),rmse_before_rad=float((((pred-y)*phys)**2).mean().sqrt()),
                                    rmse_after_rad=float((((post-y)*phys)**2).mean().sqrt()),
                                    max_action_change_rad=float(((post-pred)*phys).abs().max()))
    spec['learned_scalars']=dim*6
    spec['physical_units']='RMS over the six physical servo angle labels, train diagnostics only'
    ck['actor']=actor.state_dict()
    ck['cross_backend_supervision']=spec
    # Optimizers/RNG for continued training were never restored or updated by this diagnostic.
    torch.save(ck,out/'checkpoint_000000.pt')
    (out/'fit.json').write_text(json.dumps(spec,indent=2,allow_nan=False)+'\n')
    print(json.dumps(spec,allow_nan=False))


if __name__=='__main__':
    main()
