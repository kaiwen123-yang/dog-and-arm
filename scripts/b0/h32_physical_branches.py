"""Matched real Warp RSI branches and same-action 1/7/32-step WM validation."""
import argparse
import csv
import json
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
from supermimic.models import Dynamics
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_model import ContactRepresentation, contact_context, contact_state
from learning.b0.contact_policy import DoorMotions, build_actor, sensor
from learning.b0.contact_replay import ContactEpisode, MODES
from learning.b0.contact_warp import ContactPlant, PHASE_ID, REASONS
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import ActionMap, make_model
from scripts.b0.fit_contact_model import score
from scripts.b0.h32_recovery import write


def table(file, rows):
    with file.open("x") as f:
        w = csv.DictWriter(f, fieldnames=rows[0], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


@torch.no_grad()
def main(a):
    device="cuda:0"
    out=Path("results/b0")/a.run
    raw=Path("results/raw_large/b0")/a.run
    out.mkdir(exist_ok=False)
    raw.mkdir(exist_ok=False)
    paths=[a.references/x for x in ("pull_60_train","push_25_train")]
    weights=torch.load(a.checkpoint,weights_only=False,map_location="cpu")
    model=make_model()
    rep=ContactRepresentation(model,device)
    robot=RobotRepresentation(model,device)
    bank=DoorMotions(paths,rep,device)
    actor,_=build_actor(rep,weights["cfg"],model,device)
    actor.load_state_dict(weights["actor"])
    actor.eval()
    mapping=ActionMap(model)
    dyn=Dynamics(rep,23,5,tensor(mapping.scale,device),tensor(mapping.offset,device),
                 tuple(weights["cfg"]["wm_hidden"])).to(device)
    dyn.load_state_dict(weights["dyn"])
    dyn.eval()
    starts,side_bits,biases=[],[],[]
    names,phase_arrays,all_actions=[],[],[]
    for i,path in enumerate(paths):
        meta=bank.metas[path.name]
        n=int(bank.motion_ends[i]-bank.motion_starts[i])-1
        phases=np.array([PHASE_ID[p] for p in meta["phases"]])[np.load(path/"substeps/phase.npy")[:10*n]].reshape(n,10)
        phase_arrays.append(np.concatenate([phases,phases[-1:]]))
        actions=np.load(path/"action_clipped.npy")[:n]
        all_actions.append(np.concatenate([actions,actions[-1:]]))
        for label in ("pregrasp","grasp","open","hold","release","retreat_arm"):
            seq=np.flatnonzero((phases==PHASE_ID[label]).all(-1))
            # Pregrasp/release/retreat entry, first grasp approach, and the middle of sustained opening/hold.
            tick=int(seq[len(seq)//2] if label in ("open","hold") else seq[0])
            for bias in (0., -a.jaw_mm,a.jaw_mm):
                starts.append(bank.starts[path.name]+tick)
                names.append(f"{meta['task']}_{label}_{bias:+g}mm")
                side_bits.append(i)
                biases.append(bias)
    N=len(starts)
    frames=torch.tensor(starts,device=device)
    plant=ContactPlant(model,N,device)
    side=torch.tensor(side_bits,device=device)
    phase=torch.tensor(np.concatenate(phase_arrays),device=device)
    action=tensor(np.concatenate(all_actions),device)
    biases=tensor(biases,device)/(1000.*mapping.scale[-1])
    ctx=torch.stack([contact_context(model,s,device) for s in ("pull","push")])[side]
    plant.reset(bank.qpos[frames-10],bank.qvel[frames-10])
    def state():
        return contact_state(plant.data.qpos[:].clone(),plant.data.qvel[:].clone())
    def sense(prev):
        return sensor(robot,full_state(plant.data.qpos[:],plant.data.qvel[:]),prev)
    history=[]
    legal=torch.ones(N,device=device,dtype=torch.bool)
    for k in range(-10,0):
        history.append(sense(action[frames+k-1]))
        e=plant.step_contact(action[frames+k],side,phase[frames+k],record=(k==-1))
        legal &= e["valid_full_interval"] & (e["first_fail_substep"]==0)
    prev=action[frames-1]
    hist=torch.stack(history[1:]+[sense(prev)],1)
    alive=legal.clone()
    first=[]
    events=[]
    episodes=[]
    states=[state()]
    controls=[]
    modes=[]
    valid_intervals=[]
    previously_contact=(e["substeps"]["finger_load_N"]>plant.cfg["contact_threshold_n"]).any(dim=(1,2)).cpu().numpy()
    for step in range(a.steps):
        s=states[-1]
        _,goal=bank.goals(rep,frames,s[:,:7])
        obs=build_actor_obs_td({"motion":goal},hist)
        cmd=actor.raw(obs).clone()
        if step==0:
            cmd[:,-1]+=biases
        cmd=cmd.clamp(-1,1)
        evidence=plant.step_contact(cmd,side,phase[frames],record=True)
        next_s=state()
        valid=alive & evidence["valid_full_interval"]
        done=evidence["first_fail_substep"]>0
        sub=evidence["substeps"]
        gripped=sub["finger_load_N"]>plant.cfg["contact_threshold_n"]
        grip=(phase[frames]==PHASE_ID["open"]) | (phase[frames]==PHASE_ID["hold"])
        released=(phase[frames]==PHASE_ID["release"]) | (phase[frames]==PHASE_ID["retreat_arm"])
        now=gripped.any(dim=(1,2)).cpu().numpy()
        mode=np.full(N,"free",dtype="<U16")
        mode[now]="other_contact"
        mode[gripped.all(dim=(1,2)).cpu().numpy()]="two_finger"
        mode[(grip & ~gripped.all(-1)).any(-1).cpu().numpy()]="loss_or_slip"
        mode[released.any(-1).cpu().numpy()]="release"
        mode[now & ~previously_contact]="first_contact"
        previously_contact |= now
        modes.append(mode)
        q=s[:,:7]
        r=rep.represent(s)
        aux,pred=dyn(r,cmd,q,ctx)
        actual=rep.represent(next_s)
        ref=bank.body_state(frames+1)
        target=bank.qpos[frames+1,-1]
        def reward(aux,state):
            return rep.compute_wm_reward_from_reference(state,aux,rep.joint_state(state),cmd,prev,*ref)
        root=aux[:,3:7]
        anchor_q=ref[1][:,0]
        h=(aux[:,2]-ref[0][:,0,2]).abs()/.1
        tilt=(2*(root[:,1:3].square().sum(-1)-anchor_q[:,1:3].square().sum(-1))).abs()/.12
        pterm=torch.sigmoid((torch.maximum(h,tilt)-1)/.05)
        scores=torch.stack((reward(aux,pred),reward(next_s[:,:7],actual),pterm,
                            torch.linalg.vector_norm(sub["door_robot_force_N"],dim=-1).max(1).values,
                            1000*sub["grip_error_m"].max(1).values,torch.rad2deg(next_s[:,61]),
                            torch.rad2deg(pred[:,58]),torch.rad2deg(target)),1).cpu().numpy()
        for ix in valid.nonzero().flatten().tolist():
            row=scores[ix]
            failure=int(evidence["first_fail_substep"][ix])
            events.append(dict(episode=names[ix], t=step+1, mode=mode[ix], real_first_fail_2ms=failure,
                  reason=REASONS[int(evidence["reason"][ix])], predicted_tracking=float(row[0]),real_tracking=float(row[1]),
                  predicted_term=float(row[2]),max_force_N=float(row[3]),max_tcp_rod_mm=float(row[4]),
                  real_door_deg=float(row[5]),predicted_1step_door_deg=float(row[6]),reference_door_deg=float(row[7])))
        if step==0:
            first=(cmd*plant.scale+plant.offset).detach().cpu().tolist()
        states.append(next_s)
        controls.append(cmd)
        valid_intervals.append(valid.cpu().numpy())
        alive=valid & ~done
        prev=cmd
        hist=torch.cat([hist[:,1:],sense(prev)[:,None]],1)
        frames+=1
        if not alive.any():
            break
    S=torch.stack(states,1)
    A=torch.stack(controls,1)
    V=np.stack(valid_intervals).T
    M=np.stack(modes).T
    for n,value in [("state",S.cpu().numpy()),("clipped",A.cpu().numpy()),("valid",V),("mode",M)]:
        np.save(raw/(n+".npy"),value)
    for i,name in enumerate(names):
        length=int(V[i].sum())
        if length:
            if not V[i,:length].all() or V[i,length:].any():
                raise ValueError("Noncontiguous real branch")
            eps=ContactEpisode(raw,name,"validation",("pull","push")[side_bits[i]],S[i,:length+1],A[i,:length],ctx[i],
                               V[i,:length],M[i,:length])
            episodes.append(eps)
    table(out/"physical_intervals.csv",events)
    table(out/"mode_validation.csv",score(rep,dyn,episodes,model))
    write(out/"branches.json",dict(checkpoint=str(a.checkpoint), references=str(a.references),
          design="Independent validation RSI branches, never sampled for fitting. Ten real held prefix commands; optional +/- jaw total width perturbation only at first 20ms; subsequent feedback from each lane. Training physical audit stops validity at first terminal and keeps its measured successor. No reset-crossing windows.",
          raw=str(raw), lanes=[dict(id=name, initial_reference_frame=starts[i],prefix_valid=bool(legal[i]),
          valid_transitions=int(V[i].sum()),first_physical_target=first[i]) for i,name in enumerate(names)]))
    print(f"{len(episodes)} valid branches, {len(events)} measured physical intervals",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--references",type=Path,default=Path("results/raw_large/b0/full_warp_hold_park_r1"))
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--jaw-mm",type=float,default=.5)
    p.add_argument("--steps",type=int,default=40)
    args=p.parse_args()
    if Path(args.run).name!=args.run or args.run in ("", ".", "..") or args.steps<32:
        p.error("Fresh run name and >=32 contiguous steps required")
    main(args)
