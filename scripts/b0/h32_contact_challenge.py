"""Warp grip challenge: perturb held controls then return to feedback before hard termination."""
import argparse
import os
from pathlib import Path
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td
from learning.b0.contact_model import contact_state
from learning.b0.contact_training import ContactRun
from learning.b0.contact_warp import PHASE_ID
from scripts.b0.h32_recovery import write


@torch.no_grad()
def collect(run,folder,seed, strata=None):
    rng=np.random.default_rng(seed)
    torch.manual_seed(seed)
    n=run.n
    device=run.device
    select=[]
    for allowed in run.eligible:
        groups = strata or [('open','hold')]
        for index, names in enumerate(groups):
            legal = torch.isin(run.phases[allowed,0], torch.tensor([PHASE_ID[p] for p in names],device=device))
            ids = allowed[legal]
            count = (n//2 + len(groups)-1-index)//len(groups)
            select.append(ids[torch.randint(len(ids),(count,),device=device)])
    frames=torch.cat(select)
    side=run.sides[frames]
    plant=run.plant
    plant.reset(run.bank.qpos[frames-10],run.bank.qvel[frames-10])
    hist=[]
    alive=torch.ones(n,device=device,dtype=torch.bool)
    for k in range(-10,0):
        hist.append(run.sense(plant.data.qpos[:],plant.data.qvel[:],run.actions[frames+k-1]))
        r=plant.step_contact(run.actions[frames+k],side,run.phases[frames+k])
        alive &= r["valid_full_interval"] & (r["first_fail_substep"]==0)
    prev=run.actions[frames-1]
    hist=torch.stack(hist[1:]+[run.sense(plant.data.qpos[:],plant.data.qvel[:],prev)],1)
    prefix=int(alive.sum())
    impulse=torch.zeros((n,23),device=device)
    jaw=rng.uniform(0,.014,n)
    jaw[::4]=0
    impulse[:,-1]=torch.tensor(jaw,device=device)/plant.scale[-1]
    arm=rng.normal(size=(n,6))
    arm/=np.maximum(np.linalg.norm(arm,axis=1,keepdims=True),1e-8)
    arm*=rng.uniform(.0,.025,(n,1))
    arm[1::4]=0
    impulse[:,16:22]=torch.tensor(arm,device=device)/plant.scale[16:22]
    length=torch.as_tensor(rng.choice([1,3,5,10],n),device=device)
    records={}
    def add(name,t):
        records.setdefault(name,[]).append(t.detach().cpu().numpy().copy())
    had_gap=torch.zeros_like(alive)
    restored=torch.zeros_like(alive)
    for k in range(40):
        q=plant.data.qpos[:].clone()
        v=plant.data.qvel[:].clone()
        _,goal=run.bank.goals(run.rep,frames,q[:,:7],q[:,31])
        obs=build_actor_obs_td({"motion":goal},hist)
        cmd=(run.actor.raw(obs)+impulse*(k<length[:,None])).clamp(-1,1)
        e=plant.step_contact(cmd,side,run.phases[frames],record=True)
        q1=plant.data.qpos[:].clone()
        v1=plant.data.qvel[:].clone()
        valid=alive & e["valid_full_interval"]
        done=e["first_fail_substep"]>0
        sub=e["substeps"]
        dual=(sub["finger_load_N"]>plant.cfg["contact_threshold_n"]).all(-1)
        grip=torch.isin(run.phases[frames],torch.tensor([PHASE_ID["open"],PHASE_ID["hold"]],device=device)).all(-1)
        # Require loss in an earlier post-perturbation interval, then 20ms continuously dual after return.
        restored |= valid & ~done & grip & (k>=length) & had_gap & dual.all(-1)
        had_gap |= valid & grip & ~dual.all(-1)
        fields=dict(qpos=q,qvel=v,next_qpos=q1,next_qvel=v1,prev_action=prev,clipped=cmd,
            first_fail_substep=e["first_fail_substep"],frame=frames,reason=e["reason"],valid=valid,
            sub_finger_load_N=sub["finger_load_N"],sub_grip_error_m=sub["grip_error_m"],sub_door_robot_force_N=sub["door_robot_force_N"])
        for key,value in fields.items():
            add(key,value)
        alive=valid & ~done
        hist=torch.cat([hist[:,1:],run.sense(q1,v1,cmd)[:,None]],1)
        prev=cmd
        frames=frames+1
    folder.mkdir()
    for key,values in records.items():
        np.save(folder/(key+".npy"),np.stack(values))
    np.save(folder/"duration.npy",length.cpu().numpy())
    np.save(folder/"arm_rad.npy",arm)
    np.save(folder/"jaw_width_m.npy",jaw)
    return dict(prefix_accepted=prefix,valid=int(np.stack(records["valid"]).sum()),
               hard_terminal=int((np.stack(records["valid"]) & (np.stack(records["first_fail_substep"])>0)).sum()),
               interrupted_dual=int(had_gap.sum()),restored_before_terminal=int(restored.sum()))


def main(a):
    anchor=torch.load(a.anchor,map_location="cpu",weights_only=False)
    cfg=dict(anchor["cfg"],cohort_steps=40,worlds=64,actor_batch=64,wm_batch=64,reference_directory=str(a.references))
    cfg.pop("physical_action_prior",None)
    paths=[a.references/x for x in cfg["references"]]
    run=ContactRun(cfg,paths,paths,anchor,anchor,"cuda:0")
    run.actor.eval()
    out=Path("results/b0")/a.run
    raw=Path("results/raw_large/b0")/a.run
    out.mkdir(exist_ok=False)
    raw.mkdir(exist_ok=False)
    folds=[("train",71200+i) for i in range(8)]+[("calibration",71300+i) for i in range(2)]+[("validation",71400+i) for i in range(3)]
    strata = None
    if a.multimode:
        strata = [('approach_arm',), ('grasp',), ('open',), ('hold',), ('release',), ('retreat_arm',)]
        folds = [('train', 84100+i) for i in range(8)] + [('validation', 84200+i) for i in range(3)]
    write(out/"registration.json",dict(anchor=str(a.anchor),reference_directory=str(a.references),allocation=folds,
        worlds=64,steps=40,strata=strata or [("open","hold")],design="Each lane: independent RSI in the listed strata, 100 real prefix substeps, 1/3/5/10 x 20ms perturbed learned feedback then return to unperturbed feedback. Total jaw width additions Uniform[0,14] mm; arm vector random direction, norm Uniform[0,25] mrad, every fourth lane zero arm or zero jaw. Validity stops after first hard terminal. All attempts retained; no case references."))
    rows=[]
    for split,seed in folds:
        name=f"{split}_{seed}"
        folder=raw/name
        metrics=collect(run,folder,seed,strata)
        rows.append(dict(split=split,group=name,seed=seed,path=str(folder),**metrics))
    write(out/"cohorts.json",rows)
    print(rows,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",required=True)
    p.add_argument("--references",type=Path,default=Path("results/raw_large/b0/full_warp_hold_park_r1"))
    p.add_argument("--anchor",type=Path,default=Path("results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt"))
    p.add_argument("--multimode",action="store_true")
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", ".."):
        p.error("Select a fresh directory")
    main(a)
