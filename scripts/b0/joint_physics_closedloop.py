"""Rebuild the 200 ms registered validation prefixes and query a frozen policy every 20 ms."""
import argparse
from pathlib import Path

import mujoco
import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions,build_actor,sensor
from learning.b0.contact_warp import ContactPlant
from learning.b0.model import RobotRepresentation,full_state,tensor
from scripts.b0.dynamics_c20_pair import model_and_rep
from scripts.b0.dynamics_closedloop_entries import judge_for
from scripts.b0.dynamics_h32_score import maximum_consecutive
from scripts.b0.dynamics_warp_windows import feed
from scripts.b0.joint_physics_audit import IDENTITIES,OLD,OUT,RAW,read,source,write
from scripts.b0.joint_physics_boundary import DEVICE
from scripts.b0.score_temporal_wm import csv_file
from scripts.b0.training_entry_response import arr,phases,register_solver


@torch.no_grad()
def run(args):
    dt=IDENTITIES[args.identity]
    model,rep=model_and_rep(dt)
    robot=RobotRepresentation(model,DEVICE)
    plant=ContactPlant(model,1,DEVICE,preserve_continuous_bias=True)
    weights=torch.load(args.checkpoint,map_location="cpu",weights_only=False)
    cfg=weights["cfg"]
    actor,_=build_actor(rep,cfg,model,DEVICE)
    actor.load_state_dict(weights["actor"])
    actor.eval()
    if args.node=="shared_u0":
        common=torch.load(OLD/"h32_shared"/"first.pt",map_location="cpu",weights_only=False)["actor"]
        assert all(torch.equal(v,common[k]) for k,v in actor.cpu().state_dict().items())
        actor.to(DEVICE)
    bank=DoorMotions([Path(cfg["reference_directory"])/n for n in cfg["references"]],rep,DEVICE,reference_tail=cfg["reference_tail"])
    rows=[]
    dest=RAW/"closedloop"/args.node/args.identity/f"repeat{args.repeat}"
    names=[(s,p) for s in ("pull","push") for p in ("grasp","hold","release")]
    for side,phase in (names if args.repeat==0 else names[::-1]):
        name=f"{side}_0_validation_grip_{phase}"
        record=read(source(args.identity)/name/"receipt.json")
        row=record["row"]
        assert row["split"]=="validation" and not record.get("rejected")
        dst=dest/name
        dst.mkdir(parents=True,exist_ok=True)
        if (dst/"result.json").exists():
            old=read(dst/"result.json")
            assert old["checkpoint"]==str(args.checkpoint)
            rows.append(old)
            continue
        path=Path(row["path"])
        frame=record["frame"]
        g=record["goal_frame"]
        side_bit=torch.tensor([int(side=="push")],device=DEVICE,dtype=torch.long)
        phase_ids=phases(path)
        q,v=arr(path,"qpos"),arr(path,"qvel")
        action=arr(path,"action_clipped")
        stance=lambda t: torch.as_tensor(phase_ids[t*10:t*10+10],device=DEVICE)[None]
        ten=lambda x: tensor(np.array(x),DEVICE)[None]
        plant.reset(ten(q[frame-10]),ten(v[frame-10]))
        previous=ten(action[frame-11])
        torch.manual_seed(row["seed"])
        proprio=[]
        pre=[]
        for t in range(frame-10,frame+1):
            measured=sensor(robot,full_state(plant.data.qpos[:],plant.data.qvel[:]),previous)
            proprio.append(robot.add_proprio_noise(measured))
            if t<frame:
                previous=ten(action[t])
                ret=plant.step_contact(previous,side_bit,stance(t),record=True)
                pre.append({k:x.cpu().numpy()[0] for k,x in ret["substeps"].items()})
                if int(ret["first_fail_substep"].item()) or not ret["valid_full_interval"].item():
                    raise ValueError(f"Registered prefix rejected {name} {t}")
        snap=register_solver(plant)
        history=torch.stack(proprio[-10:],1)
        prev0=previous.cpu().numpy()
        judge=judge_for(model,record)
        scratch=mujoco.MjData(model)
        steps=[]
        queries=[]
        for j in range(32):
            if judge.passed or judge.failure:
                break
            start=bank.starts[Path(row["reference"]).name]+g
            end=bank.motion_ends[bank.ids[Path(row["reference"]).name]]
            if start+j>=end.item():
                raise ValueError("Registered reference exhausted")
            at=torch.tensor([start+j],device=DEVICE)
            _,goal=bank.goals(rep,at,plant.data.qpos[:,:7],plant.data.qpos[:,31])
            obs=build_actor_obs_td({"motion":goal},history)
            raw=actor.raw(obs)
            cmd=raw.clamp(-1,1)
            q0=plant.data.qpos[0].cpu().numpy().copy()
            v0=plant.data.qvel[0].cpu().numpy().copy()
            ret=plant.step_contact(cmd,side_bit,stance(frame+j),record=True)
            sub={k:x.cpu().numpy()[0] for k,x in ret["substeps"].items()}
            feed_record=sub|dict(qpos=sub["qpos_post"],qvel=sub["qvel_post"],q0=q0,v0=v0)
            before=judge.step
            feed(judge,scratch,feed_record)
            judge_ticks=judge.step-before
            queries.append(dict(raw=raw[0].cpu().numpy(),clipped=cmd[0].cpu().numpy(),q0=q0,v0=v0,
                                goal=goal[0].cpu().numpy(),history=history[0].cpu().numpy(),frame=int(at.item()),
                                judge_ticks=judge_ticks,training_terminal=int(ret["first_fail_substep"].item()),
                                complete=bool(ret["valid_full_interval"].item())))
            steps.append(sub)
            history=torch.cat((history[:,1:],sensor(robot,full_state(plant.data.qpos[:],plant.data.qvel[:]),cmd)[:,None]),1)
        actual={k:np.concatenate([x[k][:a["judge_ticks"]] for x,a in zip(steps,queries)]) for k in steps[0]}
        pub=OUT/"closedloop"/args.node/args.identity/f"repeat{args.repeat}"
        pub.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(dst/"trace.npz",**actual,**{"query_"+k:np.asarray([r[k] for r in queries]) for k in queries[0]},
            **{"prefix_"+k:np.stack([r[k] for r in pre]) for k in pre[0]},prefix_last_action=prev0)
        np.savez_compressed(dst/"start.npz",**snap)
        f=np.linalg.norm(actual["door_robot_force_N"],axis=-1)
        both=(actual["finger_load_N"]>.01).all(-1)
        ticks=len(f); period=plant.clock.policy_steps
        r=dict(node=args.node,identity=args.identity,repeat=args.repeat,checkpoint=str(args.checkpoint),
            side=side,phase=phase,start=name,source_trajectory=str(path),source_frame=frame,split="validation",
            dt=dt,recomputed_prefix_ticks=len(pre)*period,scored_ticks=ticks,integrated_policy_ticks=len(queries)*period,
            duration_s=ticks*dt,actor_queries=len(queries),first_20ms_survived=bool(queries[0]["judge_ticks"]==period and
                (len(queries)>1 or (not judge.failure and not judge.passed))),second_actor_queried=len(queries)>1,
            first_command=queries[0]["clipped"].tolist(),second_command=queries[1]["clipped"].tolist() if len(queries)>1 else None,
            second_action_max_delta=float(abs(queries[1]["clipped"]-queries[0]["clipped"]).max()) if len(queries)>1 else None,
            both_ticks=int(both.sum()),longest_dual_ticks=maximum_consecutive(both),
            consecutive_full_dual_intervals=sum(int(a["judge_ticks"]==period and (s["finger_load_N"]>.01).all()) for s,a in zip(steps,queries)),
            events=judge.events,passed=judge.passed,first_failure=judge.failure,first_door_N=float(f[0]),peak_before_stop_N=float(f.max()),
            first20_peak_before_stop_N=float(f[:period].max()),first20_dual_ticks=int(both[:period].sum()),
            newly_trained_samples=0,raw=str(dst/"trace.npz"))
        write(dst/"result.json",r)
        write(pub/(name+".json"),r)
        rows.append(r)
        print(name,len(queries),ticks,r["both_ticks"],flush=True)
    write(OUT/f"closedloop_{args.node}_{args.identity}_r{args.repeat}.json",dict(rows=rows,
        run="Recomputed full registered 200 ms prefixes. All commands after the prefix are sampled from frozen Actor parameters and normalization on that lane's measured state. Original event judge; no reset in scored segment.",
        scored_ticks=sum(r["scored_ticks"] for r in rows),prefix_ticks=sum(r["recomputed_prefix_ticks"] for r in rows),
        policy_ticks=sum(r["integrated_policy_ticks"] for r in rows),actor_calls=sum(r["actor_queries"] for r in rows)))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("identity",choices=list(IDENTITIES))
    p.add_argument("--repeat",type=int,choices=[0,1],required=True)
    p.add_argument("--checkpoint",type=Path,default=OLD/"h32"/"control"/"checkpoint_000000.pt")
    p.add_argument("--node",default="shared_u0")
    run(p.parse_args())
