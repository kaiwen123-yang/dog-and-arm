"""Re-query the frozen actor on its own physical successors at four fixed validation entries."""
import argparse
import json
import time
from pathlib import Path

import mujoco as mj
import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_events import ContactEvents,FrozenDoorReference
from learning.b0.contact_policy import build_actor,DoorMotions,sensor
from learning.b0.contact_warp import ContactPlant
from learning.b0.model import RobotRepresentation,full_state,tensor
from learning.b0.physics import ActionMap,settings
from scripts.b0.dynamics_c20_pair import model_and_rep
from scripts.b0.dynamics_h32_pilot import DEVICE,OUT,RAW,REG,read,resolved,write
from scripts.b0.dynamics_h32_score import ck,restore_entry,maximum_consecutive
from scripts.b0.dynamics_same_state_metrics import sha
from scripts.b0.dynamics_warp_windows import feed
from scripts.b0.register_contact_dev import SEGMENTS
from scripts.b0.score_temporal_wm import csv_file
from scripts.b0.training_entry_response import phases

CHOSEN=[("shared_u0","control",0),("control_u10","control",10),("experiment_u10","experiment",10)]
CASES=[f"{side}_0_validation_grip_{phase}" for side in ("pull","push") for phase in ("grasp","release")]


def judge_for(m,meta):
    row=meta["row"]
    phase=SEGMENTS[row["segment"]][1]
    ref=FrozenDoorReference.from_episode(row["formal_ref"],m)
    cfg=settings("push" if row["side"]=="push" else "mobile",1)
    j=ContactEvents(m,cfg,row["side"],ref,phases=phase,hold_seconds=3.,
                    start_step=row["formal_start"],score_until_step=ref.phase_bounds[phase[-1]][1]-row["formal_start"])
    j.meter_model=m
    return j


@torch.no_grad()
def run(identity, repeat):
    lock=read(REG)
    assert sha(Path(lock["locked_selection"]))==lock["selection_sha256"]
    cfg=resolved(lock["config"])
    src=Path("results/raw_large/b0/temporal_entries_v1") if identity=="formal_2ms" else Path(cfg["wm_data_recipe"]["sources"]["response"]["raw"])
    dt=.002 if identity=="formal_2ms" else cfg["physics_dt"]
    model,rep=model_and_rep(dt)
    robot=RobotRepresentation(model,DEVICE)
    plant=ContactPlant(model,3,DEVICE,preserve_continuous_bias=True)
    mapping=ActionMap(model)
    interval=plant.clock.policy_steps
    bank=DoorMotions([Path(cfg["reference_directory"])/n for n in cfg["references"]],rep,DEVICE,
                     reference_tail=cfg["reference_tail"])
    # Reverse the lane ordering in the independent second run.
    chosen=CHOSEN if repeat==0 else CHOSEN[::-1]
    actors=[]
    hashes={}
    for tag,arm,u in chosen:
        file=ck(arm,u)
        weights=torch.load(file,map_location="cpu",weights_only=False)
        actor,_=build_actor(rep,weights["cfg"],model,DEVICE)
        actor.load_state_dict(weights["actor"])
        actors.append(actor.eval())
        hashes[tag]=sha(file)
    summary=[]
    raw_folder=RAW/"h32"/"closedloop_entries"/identity/f"repeat{repeat}"
    raw_folder.mkdir(exist_ok=True,parents=True)
    begin=time.monotonic()
    for name in CASES:
        folder=src/name
        target=raw_folder/name
        target.mkdir(exist_ok=True)
        meta=read(folder/"receipt.json")
        row=meta["row"]
        assert row["split"]=="validation" and not meta.get("rejected")
        command_basis=RAW/"h32"/"same_state"/identity/name/"first_commands_and_inputs.npz"
        with np.load(folder/"start.npz") as saved,np.load(command_basis) as previous:
            restore_entry(plant,saved)
            history=tensor(saved["history"],DEVICE).expand(3,-1,-1).clone()
            original_goal=tensor(saved["goal"],DEVICE).expand(3,-1).clone()
            last=tensor(saved["previous"],DEVICE).expand(3,-1).clone()
            first_frame=int(saved["clock"].item())
            first_commands={tag:previous[tag+"_clipped"].copy() for tag,_,_ in chosen}
        expected=bank.starts[Path(row["reference"]).name]+meta["goal_frame"]
        assert int(expected)==first_frame
        sides=torch.full((3,),int(row["side"]=="push"),device=DEVICE,dtype=torch.long)
        phase_table=phases(Path(row["path"]))
        judges=[judge_for(model,meta) for _ in chosen]
        scratch=mj.MjData(model)
        steps=[]
        calls=[]
        all_records={}
        observations=[]
        goals=[]
        cmds=[]
        clipped=[]
        q0=[]
        v0=[]
        stops=[]
        for j in range(32):
            active=np.array([not judge.failure and not judge.passed for judge in judges])
            if not active.any():
                break
            frame=first_frame+j
            if frame>=int(bank.motion_ends[bank.ids[Path(row["reference"]).name]]):
                raise ValueError("Reference ended during the prespecified 640ms window")
            frames=torch.full((3,),frame,device=DEVICE,dtype=torch.long)
            _,motion=bank.goals(rep,frames,plant.data.qpos[:,:7],plant.data.qpos[:,31])
            if j==0:
                # The original batch size can round differently; the recorded goal itself is used at the first call.
                torch.testing.assert_close(motion,original_goal,atol=2e-5,rtol=2e-5)
                motion=original_goal
            raw=torch.full((3,23),float("nan"),device=DEVICE)
            applied=last.clone()
            for i,(tag,_,_) in enumerate(chosen):
                if not active[i]:
                    continue
                obs=build_actor_obs_td({"motion":motion[i:i+1]},history[i:i+1])
                raw[i]=actors[i].raw(obs)[0]
                applied[i]=raw[i].clamp(-1,1)
                if j==0:
                    np.testing.assert_allclose(applied[i].cpu().numpy(),first_commands[tag],atol=2e-6,rtol=1e-6)
            q=plant.data.qpos[:].cpu().numpy().copy()
            v=plant.data.qvel[:].cpu().numpy().copy()
            index=(meta["frame"]+j)*10
            phase=torch.as_tensor(phase_table[index:index+10],device=DEVICE).expand(3,-1)
            ret=plant.step_contact(applied,sides,phase,record=True)
            part={k:x.cpu().numpy() for k,x in ret["substeps"].items()}
            for k,x in part.items():
                all_records.setdefault(k,[]).append(x)
            observed=[]
            for i,judge in enumerate(judges):
                before=judge.step
                if active[i]:
                    record={k:x[i] for k,x in part.items()}
                    record["qpos"]=record["qpos_post"]
                    record["qvel"]=record["qvel_post"]
                    record["q0"]=q[i]
                    record["v0"]=v[i]
                    feed(judge,scratch,record)
                observed.append(judge.step-before)
            q0.append(q);v0.append(v)
            goals.append(motion.cpu().numpy())
            observations.append(history.cpu().numpy())
            calls.append(active)
            cmds.append(raw.cpu().numpy())
            clipped.append(applied.cpu().numpy())
            steps.append(observed)
            stops.append(ret["first_fail_substep"].cpu().numpy())
            # Formal observation has no new synthetic noise. The initial archived (possibly noisy) history
            # is shared exactly, and subsequent history rows are sensors of this lane's actual successor.
            measured=sensor(robot,full_state(plant.data.qpos[:],plant.data.qvel[:]),applied)
            history=torch.cat((history[:,1:],measured[:,None]),1)
            last=applied
        records={k:np.stack(x) for k,x in all_records.items()}
        observed=np.array(steps)
        times=np.arange(interval*len(steps))*dt
        rawfile=target/"closed_loop.npz"
        np.savez_compressed(rawfile,**records,force_site_sample_s=times,qv_and_judge_end_s=times+dt,
            start_sha256=sha(folder/"start.npz"),qpos_before_interval=q0,qvel_before_interval=v0,
            actor_queried=calls,raw_action=cmds,applied_action=clipped,goal=goals,history=observations,
            ref_clock=np.arange(first_frame,first_frame+len(steps)),judge_observed_ticks=observed,
            training_first_failure_tick=stops,labels=np.array([v[0] for v in chosen]))
        for i,(tag,_,_) in enumerate(chosen):
            tick=int(observed[:,i].sum())
            force=np.linalg.norm(records["door_robot_force_N"][:,i],axis=-1).reshape(-1)
            loads=records["finger_load_N"][:,i].reshape(-1,2)
            alive=(loads[:tick]>.01).all(1)
            f=judges[i].failure or {}
            commands=np.array(clipped)[:,i]
            called=np.array(calls)[:,i]
            summary.append(dict(identity=identity,repeat=repeat,start=name,side=row["side"],phase=row["phase"],
                node=tag,physics_dt=dt,first_command_max_error_vs_same=float(abs(commands[0]-first_commands[tag]).max()),
                actor_calls=int(called.sum()),measured_until_s=tick*dt,passed_original_gate=judges[i].passed,
                judge_failure=f.get("reason"),judge_failure_start_s=f.get("interval_start_s"),judge_failure_call_s=f.get("interval_end_s"),
                phase_events=len(judges[i].events),event_details=judges[i].events,peak_before_stop_N=float(force[:tick].max()),
                first20_peak_before_stop_N=float(force[:min(interval,tick)].max()),
                any_dual_before_stop=bool(alive.any()),dual_total_before_stop_s=float(alive.sum()*dt),
                dual_longest_before_stop_s=maximum_consecutive(alive)*dt,first_dual_s=float(np.flatnonzero(alive)[0]*dt) if alive.any() else None,
                first20_dual_s=float(alive[:interval].sum()*dt),fully_observed_20ms_intervals=int((observed[:,i]==interval).sum()),
                full_dual_20ms_intervals=sum(int(n==interval and (records["finger_load_N"][j,i]>.01).all()) for j,n in enumerate(observed[:,i])),
                first_jaw_command_mm=float(1000*(commands[0,22]*mapping.scale[22]+mapping.offset[22])),
                last_jaw_command_mm=float(1000*(commands[called][-1,22]*mapping.scale[22]+mapping.offset[22])),
                max_followup_clipped_command_change=float(abs(commands[called][1:]-commands[0]).max()) if called.sum()>1 else None,
                raw=str(rawfile),post_failure_unscored_ticks=int(len(force)-tick)))
        print(identity,repeat,name,[(x["node"],x["measured_until_s"],x["judge_failure"],x["dual_longest_before_stop_s"]) for x in summary[-3:]],flush=True)
    dest=OUT/"h32"
    label=f"closedloop_{identity}_r{repeat}"
    csv_file(dest/(label+".csv"),summary)
    write(dest/(label+".json"),dict(identity=identity,repeat=repeat,checkpoint_sha256=hashes,
        planned_s=.64,clock=plant.clock.metadata(),entries=CASES,actors=[x[0] for x in chosen],
        policy="Initial registered history/goal/previous and solved data. Thereafter use the applied same-actor action, measured FK sensor and unchanged 20ms reference goal clock. No reference actions or exploratory noise.",
        reporting="Post-failure integration may occur solely to serve another independent lane; ignored by judge, summaries and action-call counts. Initial states are validation entries distinct from formal ten.",
        status="Each run consists of four registered validation entries and three policies; no training, no additional seed.",
        elapsed_s=time.monotonic()-begin,rows=summary))


def summarize():
    import csv
    root=OUT/"h32"
    means=[]
    charges={}
    counts={"no_dual_sample_before_stop":0,"phase_events":0,"complete_dual_intervals":0,"cases":0}
    for identity in ("formal_2ms","training"):
        by_key={}
        for repeat in (0,1):
            record=read(root/f"closedloop_{identity}_r{repeat}.json")
            for r in record["rows"]:
                by_key.setdefault((r["node"],r["start"]),[]).append(r)
        relevant=[r for group in by_key.values() for r in group]
        counts["cases"]+=len(relevant)
        counts["phase_events"]+=sum(r["phase_events"] for r in relevant)
        counts["no_dual_sample_before_stop"]+=sum(not r["any_dual_before_stop"] for r in relevant)
        counts["complete_dual_intervals"]+=sum(r["full_dual_20ms_intervals"] for r in relevant)
        with (root/f"same_state_{identity}.csv").open() as f:
            tail={(r["node"],r["start"]):r for r in csv.DictReader(f) if r["repeat"]=="actor"}
        costs=dict(actor_forward_calls=sum(r["actor_calls"] for r in relevant),
            judged_lane_microsteps=round(sum(r["measured_until_s"]/r["physics_dt"] for r in relevant)),
            post_failure_lane_microsteps_excluded=sum(r["post_failure_unscored_ticks"] for r in relevant),
            max_peak_repeat_delta_N=0.,max_judge_time_repeat_delta_s=0.)
        for (node,start),rs in sorted(by_key.items()):
            assert len(rs)==2 and all(r["first_command_max_error_vs_same"]==0 for r in rs)
            costs["max_peak_repeat_delta_N"]=max(costs["max_peak_repeat_delta_N"],abs(rs[0]["peak_before_stop_N"]-rs[1]["peak_before_stop_N"]))
            costs["max_judge_time_repeat_delta_s"]=max(costs["max_judge_time_repeat_delta_s"],abs(rs[0]["measured_until_s"]-rs[1]["measured_until_s"]))
            shared=tail[node,start]
            means.append(dict(identity=identity,node=node,start=start,
                original_first_command_then_common_reference_tail_until_s=float(shared["before_stop_t_s"]),
                original_common_reference_tail_dual_longest_s=float(shared["before_stop_dual_longest_s"]),
                measured_closedloop_until_s=[r["measured_until_s"] for r in rs],
                measured_closedloop_peak_N=[r["peak_before_stop_N"] for r in rs],
                closedloop_dual_longest_s=[r["dual_longest_before_stop_s"] for r in rs],
                closedloop_first_failure=[r["judge_failure"] for r in rs]))
        charges[identity]=costs
    write(root/"physical_extension_evidence.json",dict(scope="Development evidence at u10; official nominal scoring is independent.",
          same_first_commands_exactly=True,closedloop=counts,budgets=charges,
          actual_comparison=means,selection_rule="Plan 5.3 requires a repeatable physical gain without an opposite-side collapse; assess these endpoints alongside original formal outcomes.",
          reference_tail_total_diagnostic_branches=4*60,closedloop_sources="closedloop_{formal_2ms,training}_r{0,1}.json/csv",
          reference_tail_sources="same_state_{formal_2ms,training}{,_independent_repeat}.csv",
          new_optimizations=0))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("identity",choices=["formal_2ms","training","summarize"])
    p.add_argument("--repeat",type=int,choices=[0,1])
    args=p.parse_args()
    if args.identity=="summarize":
        summarize()
    elif args.repeat is not None:
        run(args.identity,args.repeat)
    else:
        p.error("The physics recheck requires --repeat 0 or 1")
