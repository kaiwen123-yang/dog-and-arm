"""Original nominal gate plus paired physical and validation measurements for the H32 pilots."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
import warp as wp
from supermimic.tasks.task_spec import build_actor_obs_td
from learning.b0.contact_policy import build_actor
from learning.b0.contact_warp import ContactPlant, PHASES
from learning.b0.model import tensor
from learning.b0.physics import ActionMap
from scripts.b0.dynamics_c20_pair import model_and_rep
from scripts.b0.dynamics_same_state_metrics import (
    ENTRY_IDS, controls_csv, first_interval, input_fields, register as register_same, sha, summarize_pair,
)
from scripts.b0.dynamics_h32_pilot import ARMS, DEVICE, OUT, RAW, REG, SHARED, read, resolved, write
from scripts.b0.score_temporal_wm import csv_file, load_wm, score_long, validation_episodes
from scripts.b0.training_entry_response import integrate_branches, phases


def nodes():
    return [("shared_u0","control",0), *[(f"{arm}_u{n}",arm,n) for arm in ARMS for n in (1,10)]]


def ck(arm,n):
    return RAW/"h32"/arm/f"checkpoint_{n:06}.pt"


def check_u0():
    archived = Path("results/b0/response_s0_v1/checkpoint_000000.pt")
    base=torch.load(archived,map_location="cpu",weights_only=False)
    shared=torch.load(SHARED/"first.pt",map_location="cpu",weights_only=False)
    checks={k:torch.equal(shared["actor"][k],v) for k,v in base["actor"].items()}
    cfg=resolved(read(OUT/"shared_collection.json")["config"])
    if set(base["actor"])!=set(shared["actor"]) or not all(checks.values()):
        raise ValueError("u0 actor or normalizer differs from the archived standard policy")
    if any(cfg.get(k)!=base["cfg"].get(k) for k in ("actor_parameterization","reference_tail","references","policy_dt","actor_checkpoint")):
        raise ValueError("u0 policy source/reference differs")
    write(OUT/"h32"/"u0_identity.json",dict(archived=str(archived),source_first=str(SHARED/"first.pt"),
        matches_all_parameters_and_buffers=checks,formal_new_run_count=10,shared_by=ARMS,formal_physics_dt=.002,
        formal_reference_tail="official_clip_last",branch_equality="load_common asserts bit equality for every initialized branch"))
    return archived


def formal(tag):
    name,arm,n=next(k for k in nodes() if k[0]==tag)
    checkpoint=check_u0() if n==0 else ck(arm,n)
    rows=[]
    for protocol in ("v1","hold_margin_v2"):
        run = name+"_"+protocol
        out = OUT/"formal"/run
        p=out/"evaluation.json"
        if not p.is_file():
            cmd = [sys.executable,"-u","scripts/b0/eval_contact_segments.py","--backend","warp",
                "--checkpoint",str(checkpoint),"--run",run,"--round",str(OUT.relative_to("results/b0")/"formal"),
                str(RAW.relative_to("results/raw_large/b0")/"formal"),"--manifest",f"config/b0/contact_dev_{protocol}.json",
                "--formal-contact","--paper-score"]
            if out.is_dir():
                cmd.append("--resume")
            subprocess.run(cmd,check=True)
        result=read(p)
        if Path(result["checkpoint"])!=checkpoint or result["backend"]!="warp":
            raise ValueError("Formal evidence/checkpoint mismatch")
        for f in sorted(out.glob("*/*/nominal/result.json")):
            case=read(f)
            ret=read(f.with_name("return.json"))
            fail=case["first_failure"] or {}
            rows.append(dict(node=name,side=case["side"],segment=case["segment"],protocol=protocol,passed=case["passed"],
                failure=fail.get("reason"),failure_tick=fail.get("first_failure_substep"),
                force_time_s=fail.get("interval_start_s"),failure_decision_s=fail.get("interval_end_s"),
                failure_force_n=fail.get("door_net_force_n"),phase=fail.get("phase"),peak_force_n=case["measured_peak_net_force_n"],
                events=len(case["events"]),completed_phases=[v.get("phase") for v in case["events"]],
                effort_return=ret["normalized_fixed_effort"],planned_s=ret["planned_duration_s"],
                executed_steps=ret["executed_substeps"],absorbed_steps=ret["absorbed_substeps"],
                prefix_steps=case["prefix_physics_steps"],source=str(f)))
    if len({(r["side"],r["segment"]) for r in rows})!=len(rows) or len(rows)!=10:
        raise ValueError("Expected the ten originally registered cases")
    csv_file(OUT/"h32"/(tag+"_formal.csv"),rows)
    write(OUT/"h32"/(tag+"_formal.json"),dict(cases=10,passed=sum(r["passed"] for r in rows),
        events=sum(r["events"] for r in rows),at_first_2ms_overforce=sum(r["failure_tick"]==1 and r["failure"]=="door_force_limit" for r in rows),
        mean_fragment_return=float(np.mean([r["effort_return"] for r in rows])),dt=.002,rows=rows))


def restore_entry(plant,saved):
    n = plant.count
    def cast(name):
        return torch.as_tensor(saved[name],device=DEVICE)
    plant.reset(cast("qpos").expand(n,-1),cast("qvel").expand(n,-1))
    names=["qpos","qvel","qacc_warmstart","ctrl","time","load_ticks","lost_ticks","slip_ticks","sat_ticks"]
    if plant.model.na:
        names.append("act")
    for k in names:
        buf=getattr(plant,k) if k.endswith("_ticks") else wp.to_torch(getattr(plant.sim.wp_data,k))
        buf.copy_(cast(k).expand_as(buf))
    plant.sim.forward()
    for k in ("qacc_warmstart","qfrc_bias","servo_bias"):
        if k in saved:
            buf=plant.servo_bias if k=="servo_bias" else wp.to_torch(getattr(plant.sim.wp_data,k))
            buf.copy_(cast(k).expand_as(buf))
    if plant.servo_bias is not None and "servo_bias" not in saved:
        raise ValueError("Fine registered external lagged bias is absent")
    for key in names+["qfrc_bias"]+(["servo_bias"] if plant.servo_bias is not None else []):
        if key=="servo_bias":
            buf=plant.servo_bias
        elif key.endswith("_ticks"):
            buf=getattr(plant,key)
        else:
            buf=wp.to_torch(getattr(plant.sim.wp_data,key))
        if not torch.equal(buf,cast(key).expand_as(buf)):
            raise ValueError(f"Registered input {key} differs between lanes or from its source")


def initial_dual_ticks(values):
    first=np.flatnonzero(~values)
    return int(first[0]) if len(first) else len(values)


def maximum_consecutive(values):
    edges=np.flatnonzero(np.diff(np.r_[False,values,False].astype(int)))
    return int((edges[1::2]-edges[::2]).max(initial=0))


def summarize_entry(row,folder,dt):
    rec=read(folder/"receipt.json")
    output=[]
    with np.load(folder/"substeps.npz") as sub,np.load(folder/"dynamics.npz") as d:
        nsteps=sub["qpos_post"].shape[2]
        for b,(tag,kind,_,_) in enumerate(rec["labels"]):
            forces=np.linalg.norm(sub["door_robot_force_N"][:,b],axis=-1).reshape(-1)
            fg=sub["finger_load_N"][:,b].reshape(-1,2)
            dual=(fg>.01).all(-1)
            failure=rec["judges"][b]["failure"] or {}
            stop=int(failure.get("first_failure_substep",len(forces)))
            during=dual[:stop]
            grip_at_truth=float((sub["qpos_post"][0,b,-1,29]-sub["qpos_post"][0,b,-1,30])*1000)
            phys=d["physical"][b]
            mask=d["fail"][:,b]>0
            j=int(mask.argmax()) if mask.any() else None
            output.append(dict(start=row["id"],side=row["side"],phase=row["phase"],node=tag,repeat=kind,
                physics_dt=dt,j2_command_rad=float(phys[17]),jaw_command_mm=float(1000*phys[22]),
                achieved_opening_20ms_mm=grip_at_truth,first_door_force_n=float(forces[0]),
                peak_force_before_judge_stop_n=float(forces[:stop].max()),peak_first_interval_n=float(forces[:nsteps].max()),
                first_finger_left_n=float(fg[0,0]),first_finger_right_n=float(fg[0,1]),
                before_stop_both_any=bool(during.any()),before_stop_both_ticks=int(during.sum()),
                before_stop_dual_prefix_s=dt*initial_dual_ticks(during),
                before_stop_dual_longest_s=dt*maximum_consecutive(during),before_stop_t_s=dt*stop,
                first20ms_both_all=bool(dual[:nsteps].all()),legal_first20ms=bool(d["valid"][0,b]),
                training_failure_s=(j*nsteps+int(d["fail"][j,b]))*dt if j is not None else None,
                judge_failure=failure.get("reason"),judge_time_s=failure.get("interval_end_s"),
                force_start_s=failure.get("interval_start_s"),events=len(rec["judges"][b]["events"]),
                continued_after_stop_s=(len(forces)-stop)*dt,diagnostic_peak_full_tail_n=float(forces.max()),
                raw_directory=str(folder)))
    return output


@torch.no_grad()
def same_state(identity, retest=False, available=False):
    lock=read(REG)
    if sha(Path(lock["locked_selection"]))!=lock["selection_sha256"]:
        raise ValueError("Development WM selection changed after lock")
    cfg=resolved(lock["config"])
    register_same()
    if identity=="formal_2ms":
        dt=.002
        cases=Path("results/b0/standard_temporal_20261124/registration.json")
        source=Path("results/raw_large/b0/temporal_entries_v1")
    else:
        dt=cfg["physics_dt"]
        entry=cfg["wm_data_recipe"]["sources"]["response"]
        cases=Path(entry["registration"])
        source=Path(entry["raw"])
    model,rep=model_and_rep(dt)
    mapping=ActionMap(model)
    actors={}
    weights={}
    fingerprints={}
    # A complete pair is the normal path. Partial runs can preserve accessible packages
    # after a proven integrity/numerical stop and never overwrite the full comparison.
    selected=[(tag,arm,u) for tag,arm,u in nodes() if ck(arm,u).is_file() or not available]
    if not selected or selected[0][0]!="shared_u0":
        raise RuntimeError("Missing shared u0")
    if ck("experiment",0).exists():
        left=torch.load(ck("control",0),map_location="cpu",weights_only=False)["actor"]
        right=torch.load(ck("experiment",0),map_location="cpu",weights_only=False)["actor"]
        assert left.keys()==right.keys() and all(torch.equal(left[k],right[k]) for k in left)
    for tag,arm,u in selected:
        file=ck(arm,u)
        data=torch.load(file,map_location="cpu",weights_only=False)
        actor,_=build_actor(rep,data["cfg"],model,DEVICE)
        actor.load_state_dict(data["actor"])
        actors[tag]=actor.eval()
        weights[tag]=file
        fingerprints[tag]=sha(file)
    n=len(actors)*2
    suffix=("_partial_"+str(len(selected))) if available else ""
    if retest:
        suffix+="_independent_repeat"
    label=identity+suffix
    plant=ContactPlant(model,n,DEVICE,preserve_continuous_bias=True)
    output=RAW/"h32"/"same_state"/label
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    command_rows=[]
    entries=[r for r in read(cases)["starts"] if r["split"]=="validation"]
    assert {r["id"] for r in entries}==set(ENTRY_IDS)
    rejected=[]
    for r in entries:
        name=r["id"]
        basis=source/name
        original=read(basis/"receipt.json")
        if original.get("rejected"):
            rejected.append(name)
            continue
        target=output/name
        target.mkdir(exist_ok=True)
        basis_receipt=dict(start_sha256=sha(basis/"start.npz"),checkpoints=fingerprints,
            clock=plant.clock.metadata(),source=str(basis),judge="unchanged event state machine, sampled after solve",
            times="solve force/site at i*h; integrated q/v and judge call at (i+1)*h. Raw substeps.npz covers every microstep, including any tail after the first failure.")
        with np.load(basis/"start.npz") as z:
            if not (target/"receipt.json").exists():
                t0=time.monotonic()
                restore_entry(plant,z)
                obs=build_actor_obs_td({"motion":tensor(z["goal"],DEVICE)},tensor(z["history"],DEVICE))
                labels=[]
                commands=[]
                saved_inputs=input_fields(z)
                ticks=np.arange(32*plant.clock.policy_steps,dtype="float64")
                saved_inputs.update(force_site_sample_s=ticks*dt,qv_endpoint_s=(ticks+1)*dt,
                                    judge_observation_s=(ticks+1)*dt)
                for tag,actor in actors.items():
                    value=actor.raw(obs)[0]
                    if tag=="shared_u0":
                        torch.testing.assert_close(value,tensor(z["u0"],DEVICE),rtol=1e-6,atol=1e-6)
                    applied=value.clamp(-1,1)
                    physical=(applied*plant.scale+plant.offset)
                    saved_inputs.update({tag+"_raw":value.cpu().numpy(),tag+"_clipped":applied.cpu().numpy(),
                        tag+"_physical":physical.cpu().numpy(),tag+"_servo_target":(physical*plant.finger_factor).cpu().numpy()})
                    for role in ("actor","repeat"):
                        labels.append([tag,role,0,0.])
                        commands.append(applied)
                reference=tensor(z["reference"],DEVICE)
                source_state={k:z[k] for k in ("qpos","qvel")}
                np.savez_compressed(target/"first_commands_and_inputs.npz",**saved_inputs)
                write(target/"basis.json",basis_receipt)
                bits=torch.full((n,),int(r["side"]=="push"),device=DEVICE,dtype=torch.long)
                integrate_branches(target,r,original["offset"],original["frame"],original["goal_frame"],plant,bits,
                    source_state,torch.stack(commands),reference,labels,phases(Path(r["path"])),rep,mapping,original["attempts"],t0)
            elif read(target/"basis.json")!=basis_receipt:
                raise ValueError(f"Mismatch in cached development inputs or checkpoint: {target}")
            local_rows=summarize_entry(r,target,dt)
            intervals=first_interval(target,original,z,rep,model,dt)
            for result,interval in zip(local_rows,intervals,strict=True):
                result.update(interval)
            rows.extend(local_rows)
            command_rows.extend(controls_csv(local_rows,target,mapping,identity,weights,basis))
    csv_file(OUT/"h32"/("same_state_"+label+".csv"),rows)
    csv_file(OUT/"h32"/("same_state_commands_"+label+".csv"),command_rows)
    diffs=summarize_pair(identity,rows)
    if diffs:
        csv_file(OUT/"h32"/("same_state_differences_"+label+".csv"),diffs)
    write(OUT/"h32"/("same_state_"+label+".json"),dict(branches=len(rows),entries=len(entries)-len(rejected),
        rejected=rejected,fixed_inputs=str(source),dt=dt,variants=list(actors),direct_same_command_repeats=True,
        checkpoint_sha256=fingerprints,registration_sha256=sha(OUT/"h32"/"same_state_registration.json"),
        comparison="same measured observation, clock, physical q/v, warmstart, servo cache, independent command; 31 subsequent common reference actions",
        first_interval_s=.02,tail_s=.62,gate_identity="development only",new_training_updates=0,
        score_meaning="Complete first interval uses actual 20ms endpoint including after any failure. Absorbed first-interval diagnostic caps at the real first judge stop, divides by the same planned .02*5. Separate from original full-task score."))


@torch.no_grad()
def long_scores():
    cfg=resolved(read(REG)["config"])
    model,rep=model_and_rep(cfg["physics_dt"])
    sources=cfg["wm_data_recipe"]["sources"]
    episodes={name:validation_episodes(str(Path(sources[name]["directory"]).resolve()),model,rep,DEVICE)
              for name in ("grip","multimode")}
    for tag,arm,n in [(f"{a}_u{u}",a,u) for a in ARMS for u in (0,1,10)]:
        dst=OUT/"h32"/("validation_"+tag+".csv")
        if dst.exists():
            continue
        dyn,ident=load_wm(ck(arm,n),model,rep,DEVICE)
        if ident!="C20":
            raise ValueError("Expected C20 validation")
        rows=[]
        for name,data in episodes.items():
            rows.extend(score_long(name,data,model,rep,dyn,DEVICE))
        csv_file(dst,rows)


def online(arm):
    from scripts.b0.index_lane_round import block_counts
    cfg=resolved(read(REG)["config"])
    dt=cfg["physics_dt"]
    steps=round(.02/dt)
    groups={}
    total=dict(complete_valid=0,simulated=0,prefix_intervals=0,prefix_rejected=0,post_failure_substeps=0)
    for p in [*sorted(SHARED.glob("lanes_*.npz")),*sorted((RAW/"h32"/arm).glob("lanes_*.npz"))]:
        with np.load(p) as d:
            valid=d["valid"]; pref=d["prefix"]; fail=d["fail"]
            total["complete_valid"]+=int(valid.sum())
            total["simulated"]+=valid.size
            total["prefix_intervals"]+=int(pref.sum())
            total["prefix_rejected"]+=int(d["rejected_prefix"].sum())
            total["post_failure_substeps"]+=int(np.where(~pref & (fail>0),steps-fail,0).sum())
            for i,side in enumerate(("pull","push")):
                for phase in np.unique(d["phase"]):
                    mask=valid & (d["side"]==i) & (d["phase"]==phase)
                    if not mask.any():continue
                    a=groups.setdefault((side,PHASES[int(phase)]),dict(count=0,complete_two_finger=0,peak_force_n=0.,
                        earliest_failure_after_tick_start_s=None,terminal_intervals=0,positive_dual_prefix=0,dual_prefix_ticks=0))
                    a["count"]+=int(mask.sum())
                    a["complete_two_finger"]+=int((mask & (d["finger_min"]>.01).all(-1)).sum())
                    a["positive_dual_prefix"]+=int((mask & (d["dual_prefix"]>0)).sum())
                    a["dual_prefix_ticks"]+=int(d["dual_prefix"][mask].sum())
                    a["peak_force_n"]=max(a["peak_force_n"],float(d["peak_force"][mask].max()))
                    failures=fail[mask & (fail>0)]
                    if failures.size:
                        prior=a["earliest_failure_after_tick_start_s"]
                        a["earliest_failure_after_tick_start_s"]=min(float(failures.min())*dt,prior or .02)
                        a["terminal_intervals"]+=len(failures)
    actual=read(OUT/"h32"/arm/"outcome.json")
    if (total["complete_valid"],total["simulated"])!=(actual["valid"],actual["simulated"]):
        raise ValueError("Missing or duplicated physics blocks")
    write(OUT/"h32"/arm/"online_physics.json",dict(physics_dt=dt,**total,
        phase_source="reference clock of each legal start; original task event results are in the physical judges",
        groups=[dict(side=s,phase=p,**d) for (s,p),d in groups.items()]))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="stage",required=True)
    sub.add_parser("formal").add_argument("tag",choices=[n[0] for n in nodes()])
    matched=sub.add_parser("same")
    matched.add_argument("identity",choices=("formal_2ms","training"))
    matched.add_argument("--retest",action="store_true")
    matched.add_argument("--available",action="store_true")
    sub.add_parser("long")
    sub.add_parser("online").add_argument("arm",choices=ARMS)
    args=p.parse_args()
    if args.stage=="formal":formal(args.tag)
    elif args.stage=="same":same_state(args.identity,args.retest,args.available)
    elif args.stage=="long":long_scores()
    else:online(args.arm)
