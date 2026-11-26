"""Continuous B work blocks with matched data, replayable pair forks and an isolated terminal split."""
from itertools import product
from pathlib import Path
import subprocess
import time

from scripts.multimodal.mm03_b import (SEEDS, TASKS, TRAIN, REPO, REG, TORCH, batch, emit,
                                       freeze_file, read)

MM02 = Path("/root/autodl-tmp/mm02-20261125/round6")
METHODS = ("D23", "H9", "H9-WM")
BASE = METHODS[:2]
DEV = ("tr_nominal", "va_pose")
DISCLOSED = (*DEV, "te_combination", "te_mm02_combo_a", "te_mm02_combo_b")
PARENT = read(REPO / "results/multimodal/mm02_20261125/manifest.json")["terminal_packages"]


def stage(spec):
    out = Path(spec["output"])
    path = out / "spec.json"
    freeze_file(path, spec)
    if not (out / "receipt.json").exists():
        print("B optimization", spec["stage"], str(out), flush=True)
        subprocess.run([str(TORCH), "-u", "-m", "scripts.multimodal.mm03_b_train", str(path)], check=True)
    return read(out / "receipt.json")


def round_dir(root, r):
    return root / "B" / "rounds" / f"r{r:02d}"


def train_dir(root, r, method, seed):
    return ((round_dir(root, r) / method if r else root / "B" / "warm" / method) / f"seed{seed}")


def initial_low(root, seed):
    return root / "A" / "low" / f"seed{seed}" / "block0" / "deploy.pt"


def eval_jobs(part, kind, method, seed, r, ck, scenes, mode="pure"):
    jobs = []
    for scene, (side, goal) in product(scenes, TASKS):
        uid = f"{part.replace('/', '_')}_{method}_{seed}_{scene}_{side}{goal}_{mode}"
        jobs.append(dict(id=uid, mode=mode, method=method, side=side, goal=goal,
                         scene=scene, seed=seed, round=r, checkpoint=str(ck) if ck else None,
                         partition=part, use=kind))
    return jobs


def collect_jobs(method, seed, r, ck):
    part = f"rounds/r{r:02d}/collect"
    jobs = eval_jobs(part, "train", method, seed, r, ck, TRAIN)
    for group, side_i in product(range(6), range(2)):
        side = ("pull", "push")[side_i]
        goal = (15, 25)[(r-1+group+side_i) % 2]
        scene = TRAIN[(r-1+group+side_i) % 3]
        phase = group*2 + ((r-1+group+side_i) % 2)
        uid = f"r{r:02d}_{method}_{seed}_{scene}_{side}{goal}_prefix_g{group}"
        jobs.append(dict(id=uid, mode="prefix", method=method, side=side, goal=goal,
                         scene=scene, seed=seed, round=r, checkpoint=str(ck), partition=part,
                         use="train", group=group, switch_phase=phase))
    return jobs


def previous(root, r, method, seed):
    if r == 1:
        return train_dir(root, 0, "H9" if method == "H9-WM" else method, seed)
    return train_dir(root, r-1, method, seed) / "paired"


def earlier_collections(root, r):
    return sorted(p.parent for p in (root / "B" / "rounds").glob("r*/collect/*/episode/metadata.json")
                  if int(p.parents[3].name[1:]) <= r)


def membership(root, r):
    out = round_dir(root, r) if r else root / "B" / "warm"
    path = out / "members.json"
    if path.exists():
        return path
    prior = read(MM02 / "wm_membership.json")
    all_teachers = read(root / "B" / "teacher_cases.json")
    old_demo = [p for p in prior["old_train"] if read(Path(p) / "metadata.json")["source"] == "P6_held_20ms"
                and read(Path(p) / "metadata.json")["success"]]
    successful = [row["raw_episode"] for row in all_teachers if row["success"]]
    # Unsuccessful full teacher attempts still contribute solved WM transitions.
    if r:
        new = list(map(str, earlier_collections(root, r)))
    else:
        new = [p for p in prior["new_train"] if (Path(p) / "execution_source.npy").exists()
               and read(Path(p) / "metadata.json")["round"] == 6]
    old_wm = prior["old_train"] + prior["train_recovery"]
    all_new_teacher = [row["raw_episode"] for row in all_teachers]
    mp = dict(teachers=old_demo + successful, corrections=new,
              wm=list(dict.fromkeys(old_wm + all_new_teacher + new)), recovery=prior["train_recovery"],
              warm_correction_source="MM02 R6 actual student steps; old rows have no new velocity targets"
              if not r else None, original_legacy_ids=prior["old_train"],
              note="Legacy command-incompatible rows supervise the existing arm/jaw targets on H9. "
                   "Post-switch rows only enter the on-policy correction half. A late C fork shares the "
                   "exact frozen BC schedule. Later physical data join the next open common pool.")
    freeze_file(path, mp)
    return path


def train_spec(root, method, seed, r, role, parent, low, members, output, steps, offset=0, **extra):
    anchor = round_dir(root, r) if r else root / "B" / "warm"
    sched = anchor / "schedules" / f"seed{seed}.npy"
    data_seed = seed + 10007*r
    size = 2560 if r else 4096
    if role == "cost":
        sched = output.parent / "schedule.npy"
        size, data_seed = steps, seed+22608001
    return dict(stage=role, root=str(root), method=method, seed=seed, round=r, parent=str(parent),
                low=str(low), members=str(members), output=str(output), offset=offset, steps=steps,
                schedule_steps=size, schedule=str(sched), data_seed=data_seed, **extra)


def prepare(root, workers):
    members = membership(root, 0)
    while True:
        pending = []
        for seed in SEEDS:
            low = initial_low(root, seed)
            if not low.is_file():
                pending.append(seed)
                continue
            for method in BASE:
                out = train_dir(root, 0, method, seed)
                stage(train_spec(root, method, seed, 0, "warm", PARENT["supervised_aggregate/training"]["source"],
                                 low, members, out, 4096))
                path = out / "development.json"
                if not path.exists():
                    rows = batch(root, eval_jobs("warm/development", "evaluation", method, seed, 0,
                                                 out / "deploy.pt", DEV), workers)
                    emit(path, rows)
                # While other seeds train L16, begin genuine round-one physical collection.
                package = out / "deploy.pt"
                matrix = collect_jobs(method, seed, 1, package)
                if method == "H9":
                    matrix += collect_jobs("H9-WM", seed, 1, package)
                batch(root, matrix, workers)
        if not pending:
            return
        emit(root / "B" / "waiting.json", dict(stage="warm", missing_frozen_low_seeds=pending))
        time.sleep(8)


def rank(rows, r):
    tasks = {(s, g): [] for s, g in TASKS}
    bad = 0
    for row in rows:
        tasks[row["side"], row["goal"]].append(row["ordered_event_count"])
        reason = (row["first_failure"] or {}).get("reason", "")
        bad += int(reason.startswith(("wheel_support_or_tilt", "unexpected_contact:", "arm_joint_limit:")))
    return [sum(x["success"] for x in rows), min(min(tasks[k]) for k in TASKS),
            sum(x["ordered_event_count"] for x in rows), -bad, -r]


def update_selected(root, method, seed, r, package, rows):
    target = root / "B" / "models" / method / f"seed{seed}"
    record = dict(method=method, seed=seed, round=r, full=str(package / "full.pt"),
                  deploy=str(package / "deploy.pt"), receipt=str(package / "receipt.json"),
                  low=read(package / "receipt.json")["low"], rank=rank(rows, r),
                  development=[dict(scene=x["scene"], side=x["side"], goal=x["goal"],
                                    success=x["success"], events=x["ordered_event_count"]) for x in rows],
                  physical_cases=len(rows))
    latest = target / "latest.json"
    if not latest.exists() or read(latest)["round"] <= r:
        emit(latest, record)
    best = target / "best.json"
    if not best.exists() or record["rank"] > read(best)["rank"]:
        emit(best, record)


def low_for(root, r, seed):
    path = round_dir(root,r) / f"low_seed{seed}.json"
    if not path.exists():
        # All streams use the same frozen realization for this seed, including catch-up
        # branches. An A correction alone does not silently swap the deployed base controller.
        prev_path = round_dir(root,r-1) / f"low_seed{seed}.json"
        low = Path(read(prev_path)["low"]) if r > 1 else initial_low(root, seed)
        summary = root / "A" / "completion.json"
        if (r-1) % 4 == 0 and r > 1 and summary.is_file():
            records = read(summary)["seeds"]
            updated = records[str(seed)]
            if updated["best_block"] > 0:
                low = Path(updated["best_deploy"])
        freeze_file(path, dict(low=str(low), seed=seed, bind_round=r))
    return Path(read(path)["low"])


def fit_round(root, r, method, seed, workers, variant="C0"):
    out = train_dir(root, r, method, seed)
    member = membership(root, r)
    low = low_for(root, r, seed)
    parent = previous(root, r, method, seed)
    wm = round_dir(root, r) / "wm" / f"seed{seed}"
    wm_parent = round_dir(root, r-1) / "wm" / f"seed{seed}" / "wm.pt" if r > 1 else Path(PARENT["wm.pt"]["source"])
    fwd_replay = (root / "C" / "selection.json").is_file()
    # Replay entry is fixed when each WM stage starts; late forks reuse that completed model.
    wspec = wm / "spec.json"
    ws = read(wspec) if wspec.exists() else dict(stage="wm", root=str(root), output=str(wm),
        parent=str(wm_parent), members=str(member), seed=seed, round=r,
        data_seed=seed+7212*r, use_selected_C_replay=fwd_replay)
    stage(ws)
    stage(train_spec(root,method,seed,r,"bc",parent / "full.pt",low,member,out / "bc",2048))
    # In the first paired segment both H9 arms must have exactly the same full BC parent.
    # Each actually performs the prescribed BC updates. The already verified common parent
    # is then explicitly used by both 512-step forks (including optimizer moments).
    paired_parent = out / "bc" / "full.pt"
    if method == "H9-WM" and r == 1:
        paired_parent = train_dir(root, r, "H9", seed) / "bc" / "full.pt"
    bspec = dict(stage="bridge", output=str(out / "bridge"), parent=str(paired_parent),
                 seed=seed, round=r, members=str(member), wm=str(wm / "wm.pt"))
    stage(bspec)
    paired = out / "paired"
    stage(train_spec(root,method,seed,r,"paired",paired_parent,low,member,paired,512,offset=2048,
                     variant=variant, bundle=str(out / "bridge" / "trajectory_bundle.pt"),
                     native_workers=max(1, min(3, workers))))
    dev = eval_jobs(f"rounds/r{r:02d}/development", "evaluation", method, seed, r, paired / "deploy.pt", DEV)
    rows = batch(root,dev,workers)
    emit(out / "development.json", rows)
    update_selected(root,method,seed,r,paired,rows)
    if not r % 4:
        reg = eval_jobs(f"rounds/r{r:02d}/regression","evaluation",method,seed,r,paired / "deploy.pt",DISCLOSED)
        emit(out / "regression.json", batch(root,reg,workers))


def fill_round(root, r, workers, include_model, selected):
    matrix = []
    queue = list(BASE) + (["H9-WM"] if include_model else [])
    if r == 1 and not include_model:
        # The clone executes the same real r1 parent in anticipation of model selection.
        queue.append("H9-WM")
    for method, seed in product(queue, SEEDS):
        matrix += collect_jobs(method,seed,r,previous(root,r,method,seed) / "deploy.pt")
    col = batch(root,matrix,workers)
    directory = round_dir(root,r)
    emit(directory / "collection_complete.json", dict(planned_cases=len(matrix), recorded=len(col),
         frame0=sum(x["mode"]=="pure" for x in col), prefixes=sum(x["mode"]=="prefix" for x in col),
         prefix_reached=sum(x["prefix_reached"] is True for x in col),
         substeps=sum(x["physics_steps"] for x in col), episodes=[x["raw_episode"] for x in col]))
    membership(root,r)
    for method, seed in product(METHODS if include_model else BASE, SEEDS):
        fit_round(root,r,method,seed,workers,selected if method=="H9-WM" else "C0")


def catch_up(root, r, workers, variant):
    for index in range(1,r+1):
        for seed in SEEDS:
            out = train_dir(root,index,"H9-WM",seed)
            if (out / "development.json").exists() and (index%4 or (out / "regression.json").exists()):
                continue
            ck = previous(root,index,"H9-WM",seed) / "deploy.pt"
            batch(root,collect_jobs("H9-WM",seed,index,ck),workers)
            fit_round(root,index,"H9-WM",seed,workers,variant)


def matched_progress(root, r, methods):
    details = []
    for method,seed in product(methods,SEEDS):
        pre = train_dir(root, r-4, method if r>4 or method!="H9-WM" else "H9", seed) / "development.json"
        cur = train_dir(root,r,method,seed) / "development.json"
        a,b = [read(path) for path in (pre,cur)]
        key = lambda x: (x["side"],x["goal"],x["scene"])
        old, new = {key(x):x for x in a}, {key(x):x for x in b}
        if set(old)!=set(new) or len(old)!=8:
            raise ValueError("Matched work-block development resets differ")
        lost = [k for k in old if old[k]["success"] and not new[k]["success"]]
        tasks = sorted({k[:2] for k in old if new[k]["ordered_event_count"]>old[k]["ordered_event_count"]})
        improved = sum(x["success"] for x in new.values())>sum(x["success"] for x in old.values())
        details.append(dict(method=method,seed=seed,more_success=improved,lost_successes=lost,
                            improved_tasks=tasks,progress=improved or (not lost and len(tasks)>=2)))
    repair = round_dir(root,r) / "validated_repair.json"
    return dict(round=r,progress=any(x["progress"] for x in details),
                validated_repair=read(repair) if repair.exists() else None, matched=details)


def a_complete(root):
    if (root / "A" / "completion.json").is_file():
        return True
    if (root / "A" / "complete.json").is_file():
        from scripts.multimodal.mm03_a import finalize
        finalize(root)
        return True
    return False


def close(root, r, methods, workers, selection):
    reg = read(REG)
    a = read(root / "A" / "completion.json")
    # Finish cost sensitivity on disclosed scenes before the new combinations are opened.
    for seed in SEEDS:
        chosen = read(root / "B" / "models" / "D23" / f"seed{seed}" / "best.json")
        out = root / "B" / "cost" / f"seed{seed}"
        low_updates = a["seeds"][str(seed)]
        count = low_updates["paid_updates"]
        if count < 12000 or count != sum(b["updates"] for b in low_updates["blocks"]):
            raise ValueError(f"Unexpected retained L16-Budget for seed {seed}: {count}")
        stage(train_spec(root,"D23-cost",seed,r,"cost",chosen["full"],chosen["low"],
                         membership(root,r),out / "train",count))
        jobs = eval_jobs("cost/disclosed","evaluation","D23-cost",seed,r,out / "train" / "deploy.pt",DISCLOSED)
        emit(out / "regression.json",batch(root,jobs,workers))
    records = [read(root / "B" / "models" / method / f"seed{seed}" / "best.json") for method,seed in product(methods,SEEDS)]
    freeze_file(root / "B" / "candidate_freeze.json", dict(round=r, packages=records,
        selection=selection, rule="8 matched development cases; success, minimum across tasks, total events, fewer support/collision/limit failures, earlier checkpoint",
        new_blind_count=16, planned_formal_total=324, methods=list(methods)))
    new = tuple(x["id"] for x in reg["splits"]["new_blind_scenes"])
    jobs = []
    for item in records:
        jobs += eval_jobs("formal","evaluation",item["method"],item["seed"],item["round"],item["deploy"],(*DISCLOSED,*new))
    formal = batch(root,jobs,workers)
    if any(x["mode"]!="pure" or x["teacher_steps"] or x["teacher_substeps"] for x in formal):
        raise ValueError("Formal tasks must execute 100% pure frame-zero policy")
    emit(root / "B" / "formal_cases.json",formal)
    checks = eval_jobs("isolated_teacher","evaluation","command_teacher_v1",0,r,None,new,mode="teacher")
    feasibility = batch(root,checks,workers)
    emit(root / "B" / "isolated_teacher.json",feasibility)
    emit(root / "B" / "completion.json",dict(rounds=r,trained=list(methods),absent=sorted(set(METHODS)-set(methods)),
         planned=324,formal_recorded=len(formal),formal_success=sum(x["success"] for x in formal),
         isolated_teacher_cases=len(feasibility),hardware_motion_commands=0,candidate_freeze=str(root / "B" / "candidate_freeze.json")))


def longitudinal(root, workers):
    root=Path(root)
    if (root/"B"/"completion.json").exists():
        return
    prepare(root,workers)
    r=1
    selection_path=root/"C"/"selection.json"
    while True:
        selection=read(selection_path) if selection_path.exists() else None
        variant=(selection or {}).get("selected_variant") or (selection or {}).get("selected_model_variant")
        if variant:
            catch_up(root,r-1,workers,variant)
        fill_round(root,r,workers,variant is not None,variant)
        if r%4:
            r+=1
            continue
        methods=METHODS if variant else BASE
        decision=matched_progress(root,r,methods)
        emit(round_dir(root,r)/"block.json",decision)
        if r<8:
            r+=1
            continue
        older=read(round_dir(root,r-4)/"block.json")
        if any(x["progress"] or x["validated_repair"] for x in (older,decision)):
            r+=1
            continue
        # Keep the independent D23/H9 chain running while C is still computing.
        # Only a genuine, already reached two-block plateau waits here for the final pairing.
        while not selection_path.exists() or not a_complete(root):
            emit(root/"B"/"waiting.json",dict(stage="terminal_dependencies",completed_round=r,
                 A_complete=(root/"A"/"completion.json").exists(),C_complete=selection_path.exists()))
            time.sleep(15)
        selection=read(selection_path)
        variant=selection.get("selected_variant") or selection.get("selected_model_variant")
        if variant:
            catch_up(root,r,workers,variant)
            methods=METHODS
            past=matched_progress(root,r-4,methods)
            now=matched_progress(root,r,methods)
            emit(round_dir(root,r-4)/"block.json",past)
            emit(round_dir(root,r)/"block.json",now)
            if any(x["progress"] or x["validated_repair"] for x in (past,now)):
                r+=1
                continue
        close(root,r,methods,workers,selection)
        return

