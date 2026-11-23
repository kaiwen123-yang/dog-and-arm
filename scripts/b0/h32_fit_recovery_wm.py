"""Fit a full-task WM on teacher and fresh, episode-disjoint online Warp windows."""
import argparse
import csv
import json
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from supermimic.models import Dynamics
from supermimic.learners.wm_learner import WorldModelLearner

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg, contact_state, contact_context
from learning.b0.contact_policy import DoorMotions
from learning.b0.contact_replay import ContactEpisode, ContactWindows, MODES
from learning.b0.contact_warp import PHASE_ID, REASONS
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, WHEELS, make_model
from scripts.b0.fit_contact_model import prediction_errors
from scripts.b0.h32_recovery import write


def load_cohorts(rows,paths,bank,model,device):
    phases=[]
    for p in paths:
        idx=bank.ids[p.name]
        n=int(bank.motion_ends[idx]-bank.motion_starts[idx])-1
        labels=np.asarray([PHASE_ID[x] for x in bank.metas[p.name]["phases"]])
        ids=labels[np.load(p/"substeps/phase.npy")[:10*n]].reshape(n,10)
        phases.append(np.concatenate([ids,ids[-1:]]))
    ph=np.concatenate(phases)
    episodes=[]
    details=[]
    for item in rows:
        folder=Path(item["path"])
        def arr(name):
            return np.load(folder/(name+".npy"),mmap_mode="r")
        valid=arr("valid")
        starts,ends=arr("frame")[0],bank.motion_ends.cpu().numpy()
        side_idx=np.searchsorted(ends,starts,side="right")
        # ContactMeter and ContactPlant use the registered force threshold.
        from learning.b0.physics import settings
        fg=arr("sub_finger_load_N") > settings("mobile",1)["contact_threshold_n"]
        ids=ph[arr("frame")]
        gripping=np.isin(ids,[PHASE_ID["open"],PHASE_ID["hold"]])
        releasing=np.isin(ids,[PHASE_ID["release"],PHASE_ID["retreat_arm"]])
        terminal=arr("first_fail_substep")
        modes=np.full(valid.shape,"free",dtype="<U16")
        modes[fg.any(axis=(-2,-1))]="other_contact"
        modes[fg.all(axis=(-2,-1))]="two_finger"
        modes[(gripping & ~fg.all(-1)).any(-1)]="loss_or_slip"
        modes[releasing.any(-1)]="release"
        touched=fg.any(axis=(-2,-1))
        # A measured onset requires a preceding non-contact interval in this branch.
        onset=touched[1:] & ~touched[:-1]
        prior=np.logical_or.accumulate(touched,axis=0)[:-1]
        modes[1:][onset & ~prior & ~gripping[1:].any(-1)]="first_contact"
        modes[1:][onset & (prior | gripping[1:].any(-1))]="recontact"
        q,v,a,q1,v1=[arr(k) for k in ("qpos","qvel","clipped","next_qpos","next_qvel")]
        reason=arr("reason")
        for lane in range(valid.shape[1]):
            n=int(valid[:,lane].sum())
            if n==0:
                continue
            if not valid[:n,lane].all() or valid[n:,lane].any() or (terminal[:n-1,lane]>0).any():
                raise ValueError(f"Noncontiguous real lane in {folder}")
            side=("pull","push")[side_idx[lane]]
            qs=np.concatenate([q[:n,lane],q1[n-1:n,lane]])
            vs=np.concatenate([v[:n,lane],v1[n-1:n,lane]])
            if not np.array_equal(qs[1:],q1[:n,lane]) or not np.array_equal(vs[1:],v1[:n,lane]):
                raise ValueError("Non-contiguous boundary")
            group=f"{item['group']}/lane_{lane:02d}"
            ep=ContactEpisode(folder,group,item["split"],side,contact_state(tensor(qs,device),tensor(vs,device)),
                              tensor(np.array(a[:n,lane]),device),contact_context(model,side,device),
                              np.ones(n,dtype=bool),modes[:n,lane])
            episodes.append(ep)
            details.append(dict(group=group,frames=np.array(arr("frame")[:n,lane]),terminated=terminal[:n,lane].copy()>0,
                                reason=reason[:n,lane].copy(),prev=np.array(arr("prev_action")[:n,lane]),
                                phase=ids[:n,lane,0].copy(),peak_force=np.linalg.norm(arr("sub_door_robot_force_N")[:n,lane],axis=-1).max(-1),
                                geom=arr("sub_grip_error_m")[:n,lane].max(-1), dual=fg[:n,lane].all(-1).mean(-1)))
    return episodes,details


def csv_out(path,rows):
    with path.open("x") as f:
        writer=csv.DictWriter(f,rows[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


@torch.no_grad()
def validate(rep,dyn,model,episodes,out,window_cap=512):
    device=episodes[0].state.device
    wheel=torch.tensor([31+model.joint(n).dofadr.item() for n in WHEELS],device=device)
    rows=[]
    for h in (1,7,32):
        for side in ("pull","push"):
            source=[e for e in episodes if e.side==side]
            offset=np.cumsum([0]+[len(e.state) for e in source])[:-1]
            states=torch.cat([e.state for e in source])
            actions=torch.cat([torch.cat((e.action,e.action[-1:])) for e in source])
            context=torch.cat([e.context.expand(len(e.state),-1) for e in source])
            for mode in (*MODES,"recontact"):
                idx=np.concatenate([i+e.starts(h)[e.modes[e.starts(h)]==mode] for i,e in zip(offset,source)])
                size=len(idx)
                if size>window_cap:
                    idx=np.random.default_rng(301).choice(idx,window_cap,replace=False)
                if not len(idx):
                    rows.append(dict(side=side,h=h,mode=mode,predictor="none",metric="none",available=0,scored=0,nonfinite=0,rmse=None,p95=None))
                    continue
                values={}
                for ix_np in np.array_split(idx,max(1,int(np.ceil(len(idx)/96)))):
                    ix=torch.as_tensor(ix_np,device=device)
                    aa=states[ix,:7]
                    rr=rep.represent(states[ix])
                    hold=(aa,rr)
                    vel=hold
                    zero=rr.new_zeros(len(ix),rep.prediction_dim)
                    for k in range(h):
                        aa,rr=dyn(rr,actions[ix+k],aa,context[ix])
                        vel=rep.apply_prediction(*vel,zero,rep.dt)
                    for label,(aux,r) in (("wm",(aa,rr)),("hold",hold),("constant_velocity",vel)):
                        for metric,x in prediction_errors(rep,aux,r,states[ix+h],wheel).items():
                            values.setdefault((label,metric),[]).append(x.cpu().numpy())
                for (label,metric),slices in values.items():
                    x=np.concatenate(slices)
                    finite=x[np.isfinite(x)].astype(float)
                    rows.append(dict(side=side,h=h,mode=mode,predictor=label,metric=metric,available=size,scored=len(x),nonfinite=int(len(x)-len(finite)),
                        rmse=np.sqrt(np.mean(finite**2)) if len(finite) else None,p95=np.percentile(finite,95) if len(finite) else None))
    csv_out(out,rows)


def main(a):
    device="cuda:0"
    torch.manual_seed(640)
    np.random.seed(640)
    torch.set_float32_matmul_precision("high")
    raw=json.loads((a.data/"cohorts.json").read_text())
    cfg_read=json.loads((a.data/"registration.json").read_text())
    original=torch.load(cfg_read["anchor"],map_location="cpu",weights_only=False)
    model=make_model()
    rep=ContactRepresentation(model,device)
    mapping=ActionMap(model)
    dyn=Dynamics(rep,23,5,tensor(mapping.scale,device),tensor(mapping.offset,device),
                 tuple(original["cfg"]["wm_hidden"])).to(device)
    dyn.load_state_dict(original["dyn"])
    paths=[Path(cfg_read["reference_directory"])/x for x in original["cfg"]["references"]]
    bank=DoorMotions(paths,rep,device)
    episodes,details=load_cohorts(raw,paths,bank,model,device)
    teacher=[ContactEpisode.read(p,device) for p in paths]
    old_root=Path("results/raw_large/b0/full_held_warp_r1")
    old=[ContactEpisode.read(old_root/n,device) for n in ("pull_60_validation","push_25_validation")]
    val=[e for e in episodes if e.split=="validation"]
    online=[e for e in episodes if e.split=="train"]
    out=Path("results/b0")/a.run
    out.mkdir(exist_ok=False)
    write(out/"data.json",dict(anchor=cfg_read["anchor"],raw_sources=str(a.data),training_groups=[e.group for e in online],
          validation_groups=[e.group for e in val],old_validation=[str(e.path) for e in old],
          batch=a.batch,minibatches=a.minibatches,seed=640,
          recipe="50% full fixed Warp teachers and 50% measured policy lanes per minibatch. 2xH1,6xH7,2xH32 per ten. Pinned GenCoord loss and optimizers; no additional TCP penalty."))
    validate(rep,dyn,model,val,out/"policy_before.csv")
    validate(rep,dyn,model,old,out/"old_before.csv")
    windows={(n,k):ContactWindows(eps,n) for n in (1,7,32) for k,eps in [("online",online),("teacher",teacher)]}
    learners={n:WorldModelLearner(dyn,rep,ContactWorldModelCfg(batch_size=a.batch,horizon=n+1,num_batches=1),device) for n in (1,7,32)}
    for l in learners.values():
        l.optimizers=learners[7].optimizers
    for e in [*online,*teacher]:
        valid=torch.as_tensor(e.valid,device=device)
        learners[7].update_normalization(e.state[:-1][valid],e.action[valid])
    with (out/"training.jsonl").open("x",buffering=1) as log:
        for i in range(a.minibatches):
            horizon=(1,1,7,7,7,7,7,7,32,32)[i%10]
            batch=torch.cat([windows[horizon,"online"].sample(a.batch//2),windows[horizon,"teacher"].sample(a.batch-a.batch//2)])
            stats=learners[horizon].update([batch])
            log.write(json.dumps(dict(step=i+1,horizon=horizon,loss=float(stats["Loss/state"])),allow_nan=False)+"\n")
    dyn.eval()
    validate(rep,dyn,model,val,out/"policy_after.csv")
    validate(rep,dyn,model,old,out/"old_after.csv")
    torch.save(dict(schema=original["schema"],dyn=dyn.state_dict(),optimizers=[o.state_dict() for o in learners[7].optimizers],
               seed=640,source=cfg_read["anchor"],updates=a.minibatches,cpu_rng=torch.get_rng_state(),gpu_rng=torch.cuda.get_rng_state(),
               numpy_rng=np.random.get_state()),out/"full_task_wm.pt")
    print(out, "complete",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--run",required=True)
    p.add_argument("--minibatches",type=int,default=100)
    p.add_argument("--batch",type=int,default=64)
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", "..") or a.minibatches<1 or a.batch<2:
        p.error("Select a fresh run directory and positive budget")
    main(a)
