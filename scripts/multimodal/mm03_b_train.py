"""Execute one reproducible MM03 high-level optimization, WM refresh or bridge binding."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import random
import time

import numpy as np
import torch

from learning.multimodal.actor import load_actor
from learning.multimodal.mm03_task import SCHEMA, load_task_actor, migrate, migrate_optimizer, optimizer_for
from learning.multimodal.mm03_task_data import SharedRows
from scripts.multimodal.mm03_b import emit, read
from scripts.multimodal.train_actor import atomic_save, peak

DEVICE = torch.device("cuda:0")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def global_rng():
    return dict(python=random.getstate(), numpy=np.random.get_state(),
                torch=torch.get_rng_state(), cuda=torch.cuda.get_rng_state(DEVICE))


def restore_rng(state):
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"].cpu())
    torch.cuda.set_rng_state(state["cuda"].cpu(), DEVICE)


def refresh_wm(s):
    from learning.multimodal.world_model import PerceptualDynamics
    from learning.multimodal.wm_replay import PhysicalReplay
    from scripts.multimodal.train_wm import physical_loss
    from scripts.multimodal.mm03_h7_graph import H7Backward
    out = Path(s["output"])
    parent = torch.load(s["parent"], map_location=DEVICE, weights_only=False)
    mp = read(s["members"])
    # Keep the original R6 training evidence; each refresh includes new physical
    # training episodes selected from the common pool. No development/test data.
    members = list(dict.fromkeys(mp["wm"]))
    model = PerceptualDynamics(parent["width"]).to(DEVICE)
    model.load_state_dict(parent["model"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.0001)
    optimizer.load_state_dict(parent["optimizer"])
    rng = torch.Generator(device=DEVICE).manual_seed(s["data_seed"])
    replay = PhysicalReplay(None, "train", DEVICE, episode_dirs=members)
    out.mkdir(parents=True, exist_ok=True)
    # The first comparison's current-student native paths become common training data
    # only after C freezes its winner. The registered 128 windows still total 128.
    forward = None
    forward_rng = np.random.default_rng(s["data_seed"] + 13517)
    if s.get("use_selected_C_replay"):
        from learning.multimodal.mm03_model_replay import SharedForwardReplay
        forward = SharedForwardReplay(s["root"], DEVICE,extra_ledgers=mp.get("previous_cf_ledgers", []))
    forward_per_batch = 32 if forward is not None and forward.count else 0
    ck = out / "wm.pt"
    step0 = 0
    if ck.exists():
        resume = torch.load(ck, map_location=DEVICE, weights_only=False)
        if resume["task_spec"] != s:
            raise ValueError("WM resume specification changed")
        model.load_state_dict(resume["model"])
        optimizer.load_state_dict(resume["optimizer"])
        rng.set_state(resume["sampler_rng"].cpu())
        step0 = resume["round_updates"]
        if forward_per_batch:
            forward_rng.bit_generator.state = resume["cf_rng"]
            if resume["cf_available_windows"] != forward.count:
                raise ValueError("Common post-selection CF replay changed across recovery")
    journal = out / "applied_steps.txt"
    paid0 = sum(1 for _ in journal.open()) if journal.exists() else 0
    started = time.monotonic()
    if paid0 < step0:
        raise ValueError("WM missing applied step ledger")
    # Fix evaluation starts once. These held-out H7 physical windows are scored
    # before/after refresh and never supplied to the optimizer.
    validation = read(Path("/root/autodl-tmp/mm02-20261125/round6/wm_membership.json"))["validation_demo"]
    holdout = PhysicalReplay(None, "validation", DEVICE, episode_dirs=validation)
    starts, _ = holdout.starts(7)
    hold_ids = starts[torch.linspace(0, len(starts)-1, min(256, len(starts)), device=DEVICE).long()]
    def validation_loss():
        with torch.no_grad():
            return float(physical_loss(model, holdout.window(hold_ids, 7)))
    prior_value = out / "before_refresh.json"
    if not prior_value.exists():
        if step0:
            raise ValueError("A resumed WM stage is missing its parent validation score")
        emit(prior_value, dict(h7_loss=validation_loss(), physical_windows=len(hold_ids), sources=validation))
    backward = H7Backward(model)
    with journal.open("a", buffering=1) as f:
        for step in range(step0 + 1, 1001):
            win = replay.window(replay.draw_starts(7, 128-forward_per_batch, rng, True), 7)
            if forward_per_batch:
                cf = forward.sample(forward_per_batch, forward_rng)
                win = {key: torch.cat((win[key], val), 0) for key,val in cf.items()}
            loss = backward.backward(win)
            if step==step0+3:
                emit(out/f"h7_capture_{step0}_{os.getpid()}.json",
                     dict(training_step=step, check=backward.check, accepted=not backward.disabled,
                          extra_gradient_evaluations=backward.extra_gradient_evaluations,
                          additional_optimizer_updates=0))
            grad = torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
            optimizer.step()
            print(step, file=f)
            if step == 1 or step % 25 == 0:
                state = dict(schema="MM03-actual-action-h7-v1", task_spec=s, width=model.width,
                     parent=s["parent"], round=s["round"], round_updates=step, updates=parent["updates"]+step,
                     model=model.state_dict(), optimizer=optimizer.state_dict(), sampler_rng=rng.get_state(),
                     rng=global_rng(), members=members, horizon=7, batch=128,
                     cf_rng=forward_rng.bit_generator.state,
                     cf_available_windows=forward.count if forward is not None else 0)
                atomic_save(ck, state)
                emit(out / "progress.json", dict(stage="wm", retained=step, paid=paid0+step-step0,
                     loss=float(loss.detach()), grad=float(grad), **peak(DEVICE)))
    emit(out / "receipt.json", dict(stage="wm", retained=1000, paid=paid0+1000-step0,
         rollback=paid0-step0, source=s["parent"], members=len(members), children=s["round"], wm=str(ck),
         batch=128, horizon=7, members_file=s["members"], wall_s_last_run=time.monotonic()-started,
         validation_h7_before=read(prior_value)["h7_loss"], validation_h7_after=validation_loss(),
        h7_graph_check=backward.check,graph_replays_last_run=backward.replays,
        graph_updates_last_run=0 if backward.disabled else backward.replays,
        extra_capture_gradient_evaluations_last_run=backward.extra_gradient_evaluations,
        cf_h7_available=forward.count if forward is not None else 0,
         cf_h7_retained=1000*forward_per_batch, cf_h7_paid=(paid0+1000-step0)*forward_per_batch))


def bridge(s):
    from scripts.multimodal.mm03_c import bind_bridge
    out = Path(s["output"])
    actor, vocab, _ = load_task_actor(s["parent"], DEVICE)
    actor.requires_grad_(False)
    mp = read(s["members"])
    bundle = bind_bridge(actor, vocab, s["wm"], mp["wm"], mp["recovery"], out,
                         s["round"], s["parent"], DEVICE)
    report = read(out / "bridge.json")
    emit(out / "receipt.json", dict(stage="bridge", retained=600, paid=report["paid"],
         binding=report["encoder_id"], bundle=str(bundle), wall_s_last_run=report["last_run_wall_s"]))


def measure_low_derivatives(actor,batch):
    """Check the frozen physical action path on the actual paired BC sensors."""
    h = batch["proprio_history"].detach().requires_grad_()
    prev = batch["previous_history"].detach().requires_grad_()
    visual = actor.encode_visual(batch["rgb"], batch["depth"], batch["depth_valid"])
    text = actor.encode_text(batch["tokens"])
    high,_ = actor.high_features(visual,text,h,prev,batch["sensor"])
    command = high[:,:2]
    low = actor.low(h,prev,command)
    direction = torch.linspace(-.7,1.,low.shape[-1],device=low.device)
    sensitivity = (low*direction).sum()
    derivatives = torch.autograd.grad(sensitivity,(command,h,prev))
    return dict(policy="same frozen learned L16",rows=len(h), state_history=10,
        frozen_parameter_count=sum(p.numel() for p in actor.low.parameters() if not p.requires_grad),
        trainable_low_parameters=sum(p.numel() for p in actor.low.parameters() if p.requires_grad),
        command_gradient_l2=float(derivatives[0].norm()),proprio_history_gradient_l2=float(derivatives[1].norm()),
        previous_actual_history_gradient_l2=float(derivatives[2].norm()), diagnostic_only=True)


def check_first_h9_fork(s, parent_path):
    if s["method"]!="H9-WM" or s["round"]!=1 or s["stage"]!="paired":
        return
    duplicate_path = Path(s["output"]).parent / "bc" / "full.pt"
    ref = torch.load(parent_path,map_location="cpu",weights_only=False)
    other = torch.load(duplicate_path,map_location="cpu",weights_only=False)
    if ref["row_order"] != other["row_order"] or ref["low_sha256"] != other["low_sha256"]:
        raise ValueError("First H9 comparison requires the same physical rows and same frozen L16")
    # Compare the deployed functions in the canonical L16 parameter/buffer layout
    # even across old embedded packages missing the two version/absolute-range buffers.
    left = load_task_actor(parent_path,"cpu")[0].state_dict()
    right = load_task_actor(duplicate_path,"cpu")[0].state_dict()
    actual = [float((left[k].double()-right[k].double()).abs().max()) for k in left]
    if ref["optimizer_names"] != other["optimizer_names"]:
        raise ValueError("H9 optimizer names changed across the duplicated BC stage")
    adam = [float((v-other["optimizer"]["state"][pid][k]).abs().max())
            for pid,state in ref["optimizer"]["state"].items() for k,v in state.items()
            if torch.is_tensor(v)]
    same = max(actual + adam)==0.
    emit(Path(s["output"]) / "paired_parent_check.json",dict(common_parent=str(parent_path),
         ignored_duplicate_path=str(duplicate_path), duplicate_bc_updates_paid=other["update"],
         duplicate_represented_in_common_parent=other["update"] if same else 0,
         distinct_duplicate_updates_discarded=0 if same else other["update"],
         actor_max_abs=max(actual), adam_max_abs=max(adam), identical=same,
         paired_starts_exactly_same_file=True, row_order=ref["row_order"], frozen_low=ref["low_sha256"]))


def train(s, data_cache=None):
    from learning.multimodal.mm03_model import MM03Objective, gradient_step
    out = Path(s["output"])
    out.mkdir(parents=True, exist_ok=True)
    parent_path = Path(s["parent"])
    check_first_h9_fork(s,parent_path)
    arch = "D23" if s["method"].startswith("D23") else "H9"
    seed = s["seed"]
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if s["stage"] == "warm":
        old, vocab, parent = load_actor(parent_path, DEVICE)
        if parent["configuration"]["branch"] != "supervised_aggregate" or parent["configuration"]["round"] != 6:
            raise ValueError("The warm fork requires its complete MM02 R6 supervised checkpoint")
        for name in ("optimizer", "optimizer_names", "rng", "sampler_state", "original_train_ids"):
            if name not in parent:
                raise KeyError(f"Incomplete MM02 package, missing {name}")
        actor = migrate(old, parent, vocab, s["low"], arch, DEVICE)
        optimizer, names, lineage = migrate_optimizer(actor, parent)
        emit(out / "migration.json", dict(**lineage, training_rng_fork=seed,
             old_sampler=parent["sampler_state"], inherited_actor_updates=parent["lineage_new_actor_steps"],
             inherited_common_updates=parent["inherited_original_common_steps"], new_low=s["low"],
             normalized_and_affine_reused=True, low_requires_grad=False))
        del old
    else:
        actor, vocab, parent = load_task_actor(parent_path, DEVICE)
        if arch != actor.mode:
            raise ValueError(f"Unexpected parent architecture in {parent_path}")
        optimizer, names = optimizer_for(actor)
        if names != parent["optimizer_names"]:
            raise ValueError("High-level Adam names changed")
        optimizer.load_state_dict(parent["optimizer"])
        if s["low"] != parent["low_path"]:
            from learning.multimodal.mm03_low import LowPolicy
            actor.bind_frozen_low(LowPolicy.load(s["low"], DEVICE).state_dict())
    actor.set_encoder_grad(s["stage"] != "paired")
    actor.low.requires_grad_(False).eval()
    data_start = time.perf_counter()
    member = read(s["members"])
    key = (s["members"],sha(s["members"]),tuple(vocab.tokens))
    reused = data_cache is not None and data_cache.get("key")==key
    if reused:
        pool = data_cache["pool"]
    else:
        scopes = (("d23cost",) if s["stage"]=="cost" else
                  (f'r{s["round"]:02d}',f'catchup{s["round"]:02d}'))
        pool = SharedRows(member,vocab,DEVICE,run_root=s["root"],member_file=s["members"],scopes=scopes)
        if data_cache is not None:
            data_cache.clear()
            data_cache.update(key=key,pool=pool)
    data_setup_s = time.perf_counter()-data_start
    emit(out/"row_residency.json",dict(**pool.residency,reused=reused,setup_seconds=data_setup_s))
    schedule_path = Path(s["schedule"])
    schedule_meta = schedule_path.with_suffix(".json")
    if schedule_meta.exists():
        prior_order = read(schedule_meta)
        if (prior_order["steps"], prior_order["seed"]) == (s["data_seed"], s["schedule_steps"]) and (
                s["data_seed"] != s["schedule_steps"]):
            # Attempt 002 rejected the reversed arguments before the first optimizer step.
            # Preserve both original files and refuse an in-place rewrite of a consumed order.
            for cfg in schedule_path.parent.parent.glob("**/spec.json"):
                if read(cfg).get("schedule") == str(schedule_path) and (cfg.parent / "applied.jsonl").exists():
                    raise ValueError(f"Previously applied order needs a separately documented fork: {cfg}")
            for original in (schedule_path, schedule_meta):
                if original.exists():
                    original.rename(original.with_name(original.name + ".unused-attempt002"))
    schedule, order = pool.schedule(schedule_path, updates=s["schedule_steps"], seed=s["data_seed"])
    offset, steps = s["offset"], s["steps"]
    part = schedule[offset:offset+steps]
    if len(part) != steps:
        raise ValueError("Requested more BC rows than frozen in this common order")
    ck, final = out / "last.pt", out / "full.pt"
    step0 = 0
    obj = native = None
    native_allocation = None
    cap = None
    variant = s.get("variant", "C0")
    if variant != "C0":
        if s["stage"] != "paired" or s["method"] != "H9-WM":
            raise ValueError("Model objective requested for an unpaired experiment")
        measure_file = out / "frozen_low_input_derivatives.json"
        if not measure_file.is_file():
            emit(measure_file,measure_low_derivatives(actor,pool.batch(part[0,:32])))
        obj = MM03Objective(s["bundle"], DEVICE, vocab, seed+937*s["round"])
        obj.verify_actor(actor)
        at_start = obj.targets["prev_contact"][:,0,:2].bool()
        in_window = obj.targets["contact"][:,:32,:2].bool()
        anchor_coverage = dict(source="R6 qualified complete native teacher recoveries",
             starts=len(obj.keys), phase_counts=dict(Counter(ep["meta"]["anchor_phase"] for ep in obj.replay.episodes)),
             starts_with_either_finger=int(at_start.any(-1).sum()),starts_with_both_fingers=int(at_start.all(-1).sum()),
             windows_with_either_finger=int(in_window.any((-1,-2)).sum()),
             windows_with_both_fingers=int(in_window.all(-1).any(-1).sum()),
             source_contact_threshold_N=.01,training_split_only=True)
        emit(out / "trajectory_anchor_coverage.json",anchor_coverage)
        cap_file = out / "fixed_cap.json"
        shared_cap = Path(s["root"]) / "B" / "models" / "H9-WM" / f'seed{seed}' / "trajectory_cap.json"
        if shared_cap.exists():
            calibration = read(shared_cap)
        else:
            if s["round"] != 1:
                raise ValueError("Missing the original matched H9-parent trajectory calibration")
            cap, evidence = obj.calibrate(actor)
            calibration = dict(cap=cap, actor_before_updates=str(parent_path),seed=seed,**evidence)
            emit(shared_cap, calibration)
        cap = calibration["cap"]
        emit(cap_file,dict(**calibration,retained_across_rounds=True))
        if variant == "CF32":
            from scripts.multimodal.mm03_c_native import NativePool
            allocation_path = out / "native_pool_allocation.json"
            if allocation_path.exists():
                native_allocation = read(allocation_path)
            elif "native_worker_source" in s:
                native_allocation = dict(workers=s["native_workers"],source=s["native_worker_source"])
            else:
                # Legacy coordinators recorded only their original 3-worker proposal.
                # Freeze a separate run receipt before the first native update.
                file = Path(s["root"]) / "resources" / "worker_targets.json"
                targets = read(file) if file.is_file() else {}
                n = targets.get("B_CF",targets.get("workers",{}).get("B_CF",3))
                if n==0:
                    from scripts.multimodal.mm03_resources import update
                    n=update(Path(s["root"])).get("B_CF") or 3
                native_allocation = dict(workers=n,source="B_CF before first native update on legacy specification",
                                         initial_proposal=s["native_workers"],worker_target_file=str(file))
            n = native_allocation["workers"]
            if type(n) is not int or not 1<=n<=25:
                raise ValueError(f"Invalid frozen native worker count {n}")
            emit(allocation_path,native_allocation)
            native = NativePool(n)
            with (out / "native_pool_processes.jsonl").open("a") as f:
                print(json.dumps(dict(workers=n,optimizer_pid=os.getpid(),native_pids=[w.pid for w in native.workers],
                                      checkpoint=str(parent_path))),file=f)
    totals = dict(model_updates=0, model_queries=0, native_substeps=0, legal_model_slots=0,
                  command_label_draws=0, bc_rows=0)
    prior_wall = 0.
    if final.exists() or ck.exists():
        r = torch.load(final if final.exists() else ck, map_location=DEVICE, weights_only=False)
        if r["spec"] != s or r["row_order"] != order["batch_rows_sha256"]:
            raise ValueError("High-level resume changed a frozen dependency")
        actor.restore_task_state(r["actor"])
        optimizer.load_state_dict(r["optimizer"])
        step0, totals, prior_wall = r["update"], r["totals"], r["wall_s"]
        restore_rng(r["rng"])
        if obj is not None:
            obj.rng.set_state(r["objective_rng"].cpu())
    journal = out / "applied.jsonl"
    attempts = sum(1 for _ in journal.open()) if journal.exists() else 0
    if attempts < step0:
        raise ValueError("High-level update ledger fell behind checkpoint")
    groups = [[p for p in group["params"] if p.requires_grad] for group in optimizer.param_groups]
    started = time.monotonic()
    try:
        with journal.open("a", buffering=1) as log:
            for step in range(step0+1, steps+1):
                batch = pool.batch(part[step-1])
                bc = actor.bc_loss(batch,common_only=s["method"]=="D23-cost")
                traj, stats = None, None
                if obj is not None:
                    indices = obj.sample()
                    traj, stats = obj.loss_for(actor,indices,variant,cap,native=native,collect=variant=="CF32")
                    if variant=="CF32":
                        from scripts.multimodal.mm03_c_train import record_replay
                        keys = [obj.keys[j] for j in indices.cpu().tolist()]
                        saved_native = record_replay(out / "shared_replay",attempts+step-step0,
                                                     step,keys,indices,stats,obj)
                    if not torch.isfinite(traj):
                        raise FloatingPointError("Nonfinite trajectory objective")
                if not torch.isfinite(bc):
                    raise FloatingPointError("Nonfinite BC objective")
                if s["stage"] == "paired":
                    g = gradient_step(bc, traj, variant, optimizer, groups, [2.] * len(groups))
                else:
                    optimizer.zero_grad(set_to_none=True)
                    bc.backward()
                    norm = [float(torch.nn.utils.clip_grad_norm_(g, 2., error_if_nonfinite=True)) for g in groups if g]
                    optimizer.step()
                    g = dict(bc=float(bc.detach()), preclip_by_group=norm)
                n_real = 0 if stats is None else int(stats["native_substeps"])
                n_query = 0 if stats is None else int(stats["model_queries"])
                legal = 0 if stats is None else int(stats["valid"].sum())
                totals["model_updates"] += int(legal > 0)
                totals["model_queries"] += n_query
                totals["native_substeps"] += n_real
                totals["legal_model_slots"] += legal
                totals["bc_rows"] += len(batch["action"])
                totals["command_label_draws"] += int(batch["command_valid"].sum())
                print(json.dumps(dict(update=step, native_substeps=n_real, model_queries=n_query, legal=legal,
                                      capped=0 if stats is None else int(stats["capped"]),
                                      terminal_cases=0 if stats is None else len(stats["terminals"]),
                                      shared_native_replay=saved_native if variant=="CF32" else None,
                                      command_draws=int(batch["command_valid"].sum()), **g), allow_nan=False), file=log)
                if step == 1 or step % 64 == 0 or step == steps:
                    elapsed = prior_wall + time.monotonic() - started
                    state = dict(schema=SCHEMA, architecture=arch, method=s["method"], affine_mode=actor.affine_mode,
                        actor=actor.state_dict(), vocabulary=vocab.tokens, optimizer=optimizer.state_dict(),
                        optimizer_names=names, spec=s, low_path=s["low"], low_sha256=sha(s["low"]),
                        rng=global_rng(), row_order=order["batch_rows_sha256"], next_schedule_row=offset+step,
                        sampler=order["end_generator_state"], update=step, wall_s=elapsed, totals=totals,
                        objective_rng=obj.rng.get_state() if obj is not None else None)
                    atomic_save(final if step == steps else ck, state)
                    emit(out / "progress.json", dict(stage=s["stage"], method=s["method"], seed=seed,
                         step=step, steps=steps, paid=attempts+step-step0, loss=g["bc"], **totals, **peak(DEVICE)))
                    if step == 1 or step % 512 == 0:
                        print(f'{s["method"]} seed{seed} {s["stage"]} r{s["round"]} {step}/{steps} BC={g["bc"]:.5g}', flush=True)
    finally:
        if native is not None:
            native.close()
    payload = torch.load(final, map_location="cpu", weights_only=False)
    deploy = out / "deploy.pt"
    atomic_save(deploy, {k: payload[k] for k in ("schema", "architecture", "affine_mode", "actor",
                                                "vocabulary", "low_path", "low_sha256", "method")})
    paid_totals = dict(model_queries=0, native_substeps=0, legal=0)
    indexed_native = set()
    for line in journal.read_text().splitlines():
        rec = json.loads(line)
        for k in paid_totals:
            paid_totals[k] += rec[k]
        if rec.get("shared_native_replay"):
            indexed_native.add(Path(rec["shared_native_replay"]))
    uncommitted = set((out / "shared_replay").glob("*.npz"))-indexed_native
    extra_physics = 0
    for path in uncommitted:
        with np.load(path, allow_pickle=False) as data:
            extra_physics += int(data["native_substeps"])
    paid_totals["uncommitted_physics_substeps"] = extra_physics
    paid_totals["uncommitted_physical_batches"] = len(uncommitted)
    comparison_cost = None
    if s["method"]=="D23-cost":
        trained_low = read(Path(s["root"])/"A"/"completion.json")["seeds"][str(seed)]
        selected_block = next((b["block"] for b in trained_low["blocks"]
                               if Path(b["deployment"]).resolve()==Path(s["low"]).resolve()),None)
        comparison_cost = dict(matched_all_low_paid_updates=trained_low["paid_updates"],
             selected_parent_low=s["low"], selected_parent_low_block=selected_block,
             updates_in_selected_low_lineage=sum(b["updates"] for b in trained_low["blocks"]
                 if selected_block is not None and b["block"]<=selected_block),
             A_best_block=trained_low["best_block"], A_latest_block=trained_low["latest_block"],
             common_eligible_only=True)
    emit(out / "receipt.json", dict(stage=s["stage"], method=s["method"], round=s["round"], seed=seed,
         cost_sensitivity=comparison_cost,retained=steps, paid=attempts+steps-step0, rollback=attempts-step0, paid_model_cost=paid_totals,
         shared_row_cache_reused=reused,shared_row_setup_s=data_setup_s,
         row_tensor_device=pool.residency["device"],row_tensor_bytes=pool.residency["actual_row_tensor_bytes"],
         retained_cost=payload["totals"], native_pool_allocation=native_allocation,
         trajectory_anchor_coverage=anchor_coverage if obj is not None else None,
         full=str(final), deploy=str(deploy), parent=str(parent_path),
         low=s["low"], parent_sha256=sha(parent_path), full_sha256=sha(final), deploy_sha256=sha(deploy),
         row_order=order["batch_rows_sha256"], schedule_offset=offset,
         wall_s=payload["wall_s"], all_parameters=sum(p.numel() for p in actor.parameters()),
         high_parameters=sum(p.numel() for n,p in actor.named_parameters() if not n.startswith("low.")), **peak(DEVICE)))


def run_spec(path,data_cache):
    from scripts.multimodal.mm03_b_parallel import native_pair_slot
    s = read(path)
    if "root" not in s:
        # The first frozen bridge specifications locate their run by their
        # absolute B output directory. They remain valid on a normal resume.
        stage_path = Path(s["output"]).resolve()
        b_root = next((p for p in stage_path.parents if p.name=="B" and
                       (p.parent / "launch_config.json").is_file()),None)
        if s["stage"]!="bridge" or b_root is None:
            raise ValueError(f"Cannot identify the MM03 run for {stage_path}")
        s["root"] = str(b_root.parent)
    run_root = Path(s["root"])
    status_file = run_root / "status" / "B.json"
    if status_file.is_file():
        unit = read(status_file)
        ack = run_root / "B" / f'coordinator_refresh_attempt{unit["attempt"]}_ack.json'
        if unit.get("pid")==os.getppid() and ack.is_file():
            identity = read(ack)
            if str(identity["parent_stamp"])==str(unit["pid_stamp"]):
                print("Prior stage completed the requested coordinator refresh; new stage deferred",flush=True)
                raise SystemExit(75)
    from scripts.multimodal.mm03_b_rounds import collection_ledgers,index_warm_candidates,preserve_initial_collection
    preserve_initial_collection(run_root,s["round"])
    if (s["stage"]=="wm" and s["seed"]==1701) or (
            s["stage"]=="bc" and s.get("method")=="H9-WM") or (
            s["stage"]=="cost" and s["seed"]==1701):
        collection_ledgers(run_root,terminal=s["stage"]=="cost")
    index_warm_candidates(run_root)
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.cuda.set_device(DEVICE)
    torch.cuda.reset_peak_memory_stats(DEVICE)
    out = Path(s["output"])
    if not (out/"receipt.json").is_file():
        with native_pair_slot(s), (out/"executions.jsonl").open("a",buffering=1) as log:
            started = time.time()
            print(json.dumps(dict(event="started",time=started,pid=os.getpid(),seed=s["seed"],stage=s["stage"])),file=log)
            try:
                if s["stage"] == "wm":
                    refresh_wm(s)
                elif s["stage"] == "bridge":
                    bridge(s)
                else:
                    train(s,data_cache)
            finally:
                import resource
                print(json.dumps(dict(event="ended",time=time.time(),started=started,pid=os.getpid(),
                    seed=s["seed"],stage=s["stage"],completed=(out/"receipt.json").is_file(),
                    rss_peak_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,**peak(DEVICE))),file=log)
    # Competing seed workers can reach the same refresh request together. Only the
    # first committed phase acknowledges it; other active phases finish intact.
    request = run_root/"B"/"coordinator_refresh.json"
    if request.is_file():
        import fcntl
        with (run_root/"B"/"coordinator_refresh.lock").open("a") as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            if not request.exists():
                return
            req = read(request)
            stamp = Path(f"/proc/{os.getppid()}/stat").read_text().split(") ",1)[1].split()[19]
            if req["parent_pid"] == os.getppid() and str(req["parent_stamp"]) == stamp:
                receipt = out/"receipt.json"
                if not receipt.is_file():
                    raise ValueError("Refresh requires a completed and committed stage receipt")
                emit(request.with_name(f'coordinator_refresh_attempt{req["attempt"]}_ack.json'),
                     dict(**req,finished_receipt=str(receipt),retained=read(receipt)["retained"],
                          paid=read(receipt)["paid"],command="mm03_launch retry --unit B"))
                request.rename(request.with_name(f'coordinator_refresh_attempt{req["attempt"]}.consumed'))
                print("B coordinator reached the requested code refresh boundary; committed",receipt,flush=True)
                raise SystemExit(75)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("specs",type=Path,nargs="+")
    args = parser.parse_args()
    specs = [read(p) for p in args.specs]
    if len(set(s["seed"] for s in specs))!=1:
        raise ValueError("A grouped optimizer process must have one fine-tuning seed")
    cache = {}
    for path in args.specs:
        run_spec(path,cache)
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()

