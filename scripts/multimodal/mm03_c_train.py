"""Frozen-parent C replication, physical development selection and independent compute ledger."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid

import numpy as np
import torch

from learning.multimodal.actor import load_actor
from learning.multimodal.correction_sampling import CorrectionPool
from learning.multimodal.mm02_trajectory import encoder_id
from learning.multimodal.mm03_model import MM03Objective, gradient_step
from scripts.multimodal.mm02_train_actor import restore_optimizer
from scripts.multimodal.mm03_c import MM02, REPO, SEEDS, VARIANTS, read, report
from scripts.multimodal.mm03_c_native import NativePool
from scripts.multimodal.train_actor import atomic_save, bc_objective, peak


@torch.no_grad()
def bc_cache(dataset, actor):
    frames = []
    for i in range(0,len(dataset.images["rgb"]),128):
        frames.append(actor.encode_visual(*(dataset.images[k][i:i+128] for k in ("rgb","depth","depth_valid"))))
    return torch.cat(frames),actor.encode_text(dataset.tasks)


def supervised_loss(actor, dataset, cached, rows):
    rows=torch.as_tensor(rows,dtype=torch.long,device=dataset.device)
    episode=dataset.states["episode"][rows]
    hist=torch.maximum(rows[:,None]+dataset.backward_offsets,dataset.history_start_tensor[episode,None])
    pred=actor.act_features(cached[0][dataset.states["image"][rows]],cached[1][episode],
                            dataset.states["proprio"][hist],dataset.states["previous"][hist],
                            dataset.states["sensor"][rows])
    return bc_objective(actor,pred,dataset.states["action"][rows])


def digest_values(rows):
    return hashlib.sha256(np.ascontiguousarray(rows).tobytes()).hexdigest()


def record_replay(folder,attempt,step,keys,rows,stats,objective):
    """Store compact, episode-local physical observations for common WM replay after comparison."""
    folder.mkdir(parents=True,exist_ok=True)
    name=folder/f"applied{attempt:04d}_step{step:04d}.npz"
    if name.exists():
        # An interruption can leave a completed native batch before its optimizer ledger entry.
        # Preserve it and give the replay of this update a distinct physical execution identity.
        name=folder/f"applied{attempt:04d}_step{step:04d}_{uuid.uuid4().hex}.npz"
    arrays={"keys":np.asarray(keys), "rows":rows.detach().cpu().numpy(),
            "native_substeps":np.int64(stats["native_substeps"]),
            "terminal_metadata":np.asarray(json.dumps(stats["terminals"],allow_nan=False)),
            "p_history":objective.obs["history"][rows].cpu().numpy(),
            "previous_history":objective.obs["previous"][rows].cpu().numpy(),
            "vision0":objective.obs["low"][rows].cpu().numpy(),
            "fresh0":objective.targets["fresh"][rows,0].cpu().numpy(),
            "clock0":objective.obs["sensor"][rows,2].cpu().numpy(),
            "object0":objective.targets["o"][rows,0].cpu().numpy(),
            "contact0":objective.targets["prev_contact"][rows,0].cpu().numpy(),
            "valid":stats["valid"].cpu().numpy()}
    seq=stats["sequences"]
    if seq:
        for key in ("slot","action","p","o","vision","contact","fresh","clock"):
            arrays[key]=np.concatenate([x[key] for x in seq])
        arrays["tick"]=np.concatenate([np.full(len(x["slot"]),x["tick"],np.int16) for x in seq])
        fresh=[x for x in seq if len(x["exposure_slots"])]
        if fresh:
            arrays["exposure_slot"]=np.concatenate([x["exposure_slots"] for x in fresh])
            arrays["exposure_t"]=np.concatenate([x["exposure_times"] for x in fresh])
            arrays["exposure_tick"]=np.concatenate([np.full(len(x["exposure_slots"]),x["tick"]+1,np.int16) for x in fresh])
            arrays["exposure_actor_features"]=np.concatenate([x["measured_features"] for x in fresh])
            for index,column in enumerate(("exposure_rgb","exposure_depth","exposure_depth_valid")):
                arrays[column]=np.stack([image[index] for x in fresh for image in x["exposures"]])
    with name.with_suffix(".tmp").open("wb") as f:
        np.savez(f,**arrays)
    name.with_suffix(".tmp").replace(name)
    return str(name)


def apply_fork(folder, fork, seed, pool, cache, schedule, schedule_meta,
               objective, cap, parent_path, native, dev):
    folder.mkdir(parents=True,exist_ok=True)
    actor,vocab,parent=load_actor(parent_path,dev)
    actor.freeze_encoders()
    objective.verify_actor(actor)
    optimizer,names,migration=restore_optimizer(actor,actor,parent)
    groups=[[p for p in group["params"] if p.requires_grad] for group in optimizer.param_groups]
    config=dict(method="M1Piper-MM03-StabilityHierarchy-DMO-v1",variant=fork,seed=seed,source=str(parent_path),
                encoder_id=encoder_id(actor),bc_schedule=schedule_meta["row_order_sha256"],
                membership=pool.membership_signature,cap=cap,
                parent_training_schema=parent["schema"],steps=512,bc_batch=256,
                imagination_batch=32,encoder_frozen=True)
    statepath=folder/"latest.pt"
    done=folder/"final.pt"
    start=0
    if (folder/"configuration.json").exists() and read(folder/"configuration.json")!=config:
        raise ValueError("Frozen C inputs or optimizer configuration changed")
    report(folder/"configuration.json",config)
    report(folder/"optimizer_inheritance.json",migration)
    src=done if done.exists() else statepath
    if src.exists():
        saved=torch.load(src,map_location=dev,weights_only=False)
        if saved["configuration"]!=config:
            raise ValueError("Stored C parent/schedule/cap changed")
        actor.load_state_dict(saved["actor"])
        optimizer.load_state_dict(saved["optimizer"])
        start=saved["update"]
    torch.manual_seed(seed)
    anchor_generator=torch.Generator(device=dev).manual_seed(seed)
    ordered=torch.randint(len(objective.keys),(512,32),generator=anchor_generator,device=dev)
    anchor_hash=digest_values(ordered.cpu().numpy())
    log=folder/"applications.jsonl"
    existing=[json.loads(s) for s in log.open()] if log.exists() else []
    if len(existing)<start:
        raise ValueError("C optimizer checkpoint is ahead of its physical/gradient ledger")
    if (folder/"receipt.json").exists() and done.exists() and (folder/"deploy.pt").exists():
        return read(folder/"receipt.json")
    begin=time.perf_counter()
    prior_wall=saved["train_wall_s"] if start else 0.
    paid=len(existing)
    with log.open("a",buffering=1) as ledger:
        for i in range(start,512):
            loss_bc=supervised_loss(actor,pool.dataset,cache,schedule[i])
            idx=ordered[i]
            loss_traj=None
            cost=dict(model_queries=0,native_substeps=0,valid_control_steps=0,partial_intervals=[],
                      terminal_cases=0,capped=0)
            if fork!="C0":
                loss_traj,stats=objective.loss_for(actor,idx,fork,cap,native,collect=fork=="CF32")
                cost.update(model_queries=stats["model_queries"],native_substeps=stats["native_substeps"],
                            valid_control_steps=int(stats["valid"].sum()),capped=int(stats["capped"]),
                            partial_intervals=[r for r in stats["terminals"] if r["partial_dt"] is not None],
                            terminal_cases=len(stats["terminals"]))
                if fork=="CF32":
                    keys=[objective.keys[j] for j in idx.cpu().tolist()]
                    cost["shared_native_replay"]=record_replay(folder/"shared_replay",paid+1,i+1,keys,idx,stats,objective)
            if not torch.isfinite(loss_bc) or (loss_traj is not None and not torch.isfinite(loss_traj)):
                raise FloatingPointError(f"{fork} seed {seed} nonfinite objective at attempted update {i+1}")
            try:
                measures=gradient_step(loss_bc,loss_traj,fork,optimizer,groups,[2.]*len(groups))
            except RuntimeError as exc:
                if "non-finite" not in str(exc).lower() and "nonfinite" not in str(exc).lower():
                    raise
                raise FloatingPointError(f"{fork} seed {seed} update {i+1}: {exc}") from exc
            paid+=1
            row=dict(applied=paid,step=i+1,bc_rows_sha=digest_values(schedule[i]),
                     anchor_rows_sha=digest_values(idx.cpu().numpy()) if fork!="C0" else None,**measures,**cost)
            ledger.write(json.dumps(row,allow_nan=False)+"\n")
            if i==0 or (i+1)%(8 if fork=="CF32" else 32)==0:
                payload=dict(schema=parent["schema"],method=config["method"],configuration=config,
                             affine_mode=parent["affine_mode"],actor=actor.state_dict(),vocabulary=vocab.tokens,
                             optimizer=optimizer.state_dict(),optimizer_names=names,update=i+1,
                             train_wall_s=prior_wall+time.perf_counter()-begin,
                             bc_schedule_sha=config["bc_schedule"],anchor_schedule_sha=anchor_hash,
                             next_batch=i+1,torch_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state(dev),
                             membership=parent["membership"],original_train_ids=parent["original_train_ids"],
                             original_parent=str(parent_path),
                             lineage_new_actor_steps=parent["lineage_new_actor_steps"]+i+1)
                atomic_save(done if i+1==512 else statepath,payload)
                report(folder/"progress.json",dict(step=i+1,paid=paid,elapsed=payload["train_wall_s"],**cost))
                if i==0 or (i+1)%64==0:
                    print(f"{fork} seed {seed}: {i+1}/512, BC {measures['bc']:.5g}, model {measures['trajectory']}",flush=True)
    deployed=dict(schema=parent["schema"],method=config["method"],affine_mode=parent["affine_mode"],
                  actor=actor.state_dict(),vocabulary=vocab.tokens,configuration=config,operation="inference",update=512)
    atomic_save(folder/"deploy.pt",deployed)
    check,_,_=load_actor(folder/"deploy.pt",dev)
    if any(not torch.equal(x,check.state_dict()[key]) for key,x in actor.state_dict().items()):
        raise ValueError("Deployment export differs from frozen C training state")
    all_rows=[json.loads(s) for s in log.open()]
    counted=Counter()
    if fork=="CF32":
        indexed={Path(r["shared_native_replay"]) for r in all_rows}
        uncommitted=sorted(set((folder/"shared_replay").glob("*.npz"))-indexed)
        for path in uncommitted:
            with np.load(path,allow_pickle=False) as physical:
                counted["uncommitted_native_substeps"]+=int(physical["native_substeps"]) if "native_substeps" in physical else int(physical["valid"].sum())*10
        counted["uncommitted_physical_batches"]=len(uncommitted)
    for row in all_rows:
        for key in ("model_queries","native_substeps","valid_control_steps","terminal_cases","capped"):
            counted[key]+=row[key]
    receipt=dict(configuration=config,retained=512,paid=len(all_rows),rollback=len(all_rows)-512,
                 bc_rows_paid=256*len(all_rows),anchor_schedule_sha=anchor_hash,actual_cost=dict(counted),
                 full=str(done),deployment=str(folder/"deploy.pt"),train_wall_s=prior_wall+time.perf_counter()-begin,
                 critic_updates=0,wm_updates=0,**peak(dev))
    report(folder/"receipt.json",receipt)
    return receipt


def recovery_rows(actor, objective, native, cap):
    ids=torch.arange(len(objective.keys),device=objective.device)
    with torch.no_grad():
        _,stats=objective.loss_for(actor,ids,"CF32",cap,native)
    fail={it["slot"]:it for it in stats["terminals"]}
    mask=stats["valid"].cpu().numpy()
    losses=stats["per_step"].cpu().numpy()
    rows=[]
    for i,key in enumerate(objective.keys):
        term=fail.get(i,{})
        rows.append(dict(anchor_key=key,snapshot=str(objective.snapshots[i]),
                    actual_full_20ms=int(mask[i].sum()),survived_32=bool(mask[i].all() and not term.get("failure")),
                    first_failure=term.get("failure"),terminal=term,teacher_window_h=32,
                    physical_substeps=int(mask[i].sum())*10+(term.get("substeps",0) if not term.get("scored") else 0),
                    valid_step_mean_capped_error=float(losses[i,mask[i]].mean()) if mask[i].any() else None,
                    discounted_planned_loss=float((losses[i]*(.985**np.arange(32))).sum()/(.985**np.arange(32)).sum())))
    if sum(r["physical_substeps"] for r in rows)!=stats["native_substeps"]:
        raise ValueError("Short recovery native substep ledger disagrees")
    return rows


def full_development(root, fork, seed, out, workers):
    file=out/"development/cases.json"
    if not file.exists():
        subprocess.run([str(REPO/".venv/bin/python"),"-u","-m","scripts.multimodal.mm03_c_eval",
                        str(root),fork,str(seed),str(out/"deploy.pt"),"--workers",str(workers)],check=True,cwd=REPO)
    rows=read(file)
    if len(rows)!=8:
        raise ValueError("C development roster requires eight matched frame-zero cases")
    return rows


def selection(root):
    rows=[]
    for fork in VARIANTS:
        long,short,invalid,seeds=[],[],{},[]
        for seed in SEEDS:
            out=root/"C"/fork/f"seed{seed}"
            if (out/"numerical_failure.json").is_file():
                invalid[str(seed)]=read(out/"numerical_failure.json")
                continue
            full=read(out/"development/cases.json")
            recovered=read(out/"short_recovery.json")
            long.extend(full)
            short.extend(recovered)
            receipt=read(out/"receipt.json")
            seeds.append(dict(seed=seed,updates_paid=receipt["paid"],updates_retained=receipt["retained"],
                              full_success=sum(r["success"] for r in full),full_n=len(full),
                              ordered_events=sum(r["ordered_event_count"] for r in full),
                              short_survived=sum(r["survived_32"] for r in recovered),short_n=len(recovered),
                              evaluation_physics=sum(r["physics_steps"] for r in full)+sum(r["physical_substeps"] for r in recovered),
                              training_cost=receipt["actual_cost"]))
        by_task={}
        for row in long:
            key=(row["side"],int(row["goal"]))
            by_task.setdefault(key,[]).append(row["ordered_event_count"])
        reasons=[(row["first_failure"] or {}).get("reason","") for row in long]
        safety_fail=sum(r.startswith(("wheel_support_or_tilt","arm_joint_limit:")) or
                        any(tag in r for tag in ("robot_self","self_collision","self_contact")) for r in reasons)
        worst=min((min(values) for values in by_task.values()),default=0)
        rank=(sum(row["success"] for row in long),worst,sum(map(sum,by_task.values())),-safety_fail,
              sum(row["survived_32"] for row in short),-VARIANTS.index(fork))
        rows.append(dict(variant=fork,rank=list(rank),full_development_n=len(long),short_recovery_n=len(short),
                         by_seed=seeds,numerically_invalid=invalid,
                         ordered_events_by_task={f"{a}{b}":sum(v) for (a,b),v in by_task.items()},
                         min_ordered_events_by_task={f"{a}{b}":min(v) for (a,b),v in by_task.items()}))
    invalid=invalid_variants(root)
    legal=[row for row in rows if row["variant"]!="C0" and row["variant"] not in invalid and not row["numerically_invalid"]]
    winner=max(legal,key=lambda row:row["rank"])["variant"] if legal else None
    report(root/"C/selection.json",dict(schema="mm03-selection-v2",variant=winner,selected_model_variant=winner,
        rationale="three-seed original-judge full successes, worst-task and total event counts, support/collision/limit failures, short-window survival, registered order",
        ranking=rows,blind_evaluations=0))


def invalid_variants(root):
    invalid=set()
    for fork in VARIANTS[1:]:
        for seed in SEEDS:
            path=root/"C"/fork/f"seed{seed}"/"applications.jsonl"
            if not path.is_file() or not any(json.loads(s)["grad_trajectory"]>0 for s in path.open()):
                invalid.add(fork)
    return invalid


def compare(root, workers, parent_path, bundle, dev):
    parent_actor,vocab,parent=load_actor(parent_path,dev)
    parent_actor.freeze_encoders()
    output=root/"C"
    training=MM03Objective(bundle,dev,vocab,1701)
    training.verify_actor(parent_actor)
    cfg=output/"calibration.json"
    if cfg.exists():
        cal=read(cfg)
        if cal["encoder"]!=encoder_id(parent_actor) or cal["anchor_keys"]!=list(training.keys[:256]):
            raise ValueError("Frozen calibration identity differs from active parent/anchors")
        cap=cal["cap"]
    else:
        cap,details=training.calibrate(parent_actor)
        report(cfg,dict(cap=cap,encoder=encoder_id(parent_actor),**details))
    validation_dirs=[]
    for stage in range(1,7):
        validation_dirs.extend(row["raw_episode"] for row in read(MM02/f"round{stage}/recovery_validation/cases.json"))
    val=MM03Objective(bundle,dev,vocab,1701,split="validation",directories=validation_dirs,max_anchors=32)
    if len(val.keys)!=32 or set(val.keys)&set(training.keys):
        raise ValueError("Expected 32 disjoint legal development anchors")
    val.verify_actor(parent_actor)
    report(output/"development_anchors.json",dict(keys=val.keys,paths=list(map(str,val.snapshots)),split="validation"))
    pool=CorrectionPool(Path("/root/autodl-tmp/mm01-20261125/data"),parent["original_train_ids"],
                        read(MM02/"round6/actor_members.json"),vocab,dev)
    cache=bc_cache(pool.dataset,parent_actor)
    # No image/text encoder can change in these comparisons; release the large raw image tensors.
    pool.dataset.images.clear()
    schedules={seed:pool.schedule(output/"schedules"/f"seed{seed}.npy",seed,512) for seed in SEEDS}
    native=NativePool(workers)
    try:
        if not (output/"directional_response.json").exists():
            from scripts.multimodal.mm03_c_direction import directional
            report(output/"directional_response.json",directional(parent_actor,training,native,cap))
        for fork in VARIANTS:
            for seed in SEEDS:
                out=output/fork/f"seed{seed}"
                report(output/"current.json",dict(stage="training",variant=fork,seed=seed))
                schedule,meta=schedules[seed]
                if (out/"numerical_failure.json").exists():
                    continue
                try:
                    apply_fork(out,fork,seed,pool,cache,schedule,meta,training,cap,parent_path,native,dev)
                except FloatingPointError as exc:
                    log=out/"applications.jsonl"
                    paid=sum(1 for _ in log.open()) if log.is_file() else 0
                    report(out/"numerical_failure.json",dict(variant=fork,seed=seed,reason=str(exc),
                           paid_updates=paid,checkpoint=str(out/"latest.pt") if (out/"latest.pt").is_file() else None,
                           development_cases_not_run=8,recovery_cases_not_run=32))
                    continue
                report(output/"current.json",dict(stage="physical_development",variant=fork,seed=seed))
                full_development(root,fork,seed,out,workers)
                if not (out/"short_recovery.json").exists():
                    actor,_,_=load_actor(out/"deploy.pt",dev)
                    actor.freeze_encoders()
                    val.verify_actor(actor)
                    report(out/"short_recovery.json",recovery_rows(actor,val,native,cap))
        selection(root)
        report(output/"current.json",dict(stage="completed",selected=read(output/"selection.json")["variant"]))
    finally:
        native.close()
