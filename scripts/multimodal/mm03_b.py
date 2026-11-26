"""Run and resume MM03 task collection, training, candidate freeze and original scoring."""
import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from itertools import product
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

import numpy as np

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "results/planning/multimodal_mm03_20261126/registration.json"
NATIVE = REPO / ".venv/bin/python"
TORCH = REPO / ".conda/envs/arm-and-dog/bin/python"
SEEDS = (1701, 1702, 1703)
TRAIN = ("tr_nominal", "tr_offset", "tr_load")
TASKS = tuple(product(("pull", "push"), (15, 25)))
PERTURBATION_SEEDS = tuple(range(26112600, 26112608))


def read(path):
    return json.loads(Path(path).read_text())


def emit(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.part")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    os.replace(tmp, path)


def freeze_file(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Frozen membership or specification changed: {path}")
    else:
        emit(path, value)


def teacher_jobs():
    scenes = {scene["id"]: scene["perturbation"] for scene in
              read(REPO / "config/multimodal/scenes.json")["scenes"]}
    jobs = []
    for seed, scene, (side, goal) in product(PERTURBATION_SEEDS, TRAIN, TASKS):
        perturb = dict(scenes[scene])
        if seed != PERTURBATION_SEEDS[0]:
            rng = np.random.default_rng(seed)
            for dimension, amplitude in (("dx", .004), ("dy", .003), ("yaw", .25)):
                perturb[dimension] = round(perturb.get(dimension, 0.) + rng.uniform(-amplitude, amplitude), 9)
        jobs.append(dict(id=f"teacher_{seed}_{scene}_{side}{goal}", partition="teachers", scene=scene,
                         side=side, goal=goal, method="command_teacher_v1", mode="teacher", use="train",
                         round=0, seed=seed, train_perturbation=perturb, checkpoint=None))
    return jobs


def batch(root, jobs, workers, *, cf_free_phase=False):
    from scripts.multimodal.mm03_b_physics import episode
    jobs = list(jobs)
    if not jobs:
        return []
    partition = jobs[0]["partition"]
    if partition.startswith("rounds/") and partition.endswith("/collect"):
        by_model = {}
        for item in jobs:
            by_model.setdefault((item["method"],item["seed"]),[]).append(item)
        for (method,seed), cases in by_model.items():
            if len(cases)!=24:
                continue  # A caller may resume or inspect a subset of an already queued matrix.
            if sum(job["mode"]=="pure" for job in cases)!=12:
                raise ValueError("The full registered matrix requires 12 frame-zero and 12 prefix jobs")
            target = Path(root)/"B"/Path(partition).parent/"collection_plan"/f"{method}_seed{seed}.json"
            freeze_file(target,dict(method=method,seed=seed,round=cases[0]["round"],cases=cases,
                prefix_rule="two sides x six groups; rotate side/round/group for angle, scene and intra-group cut",
                clone_before_WM=(method=="H9-WM" and cases[0]["round"]==1)))
    target_file = Path(root) / "resources" / "worker_targets.json"
    initial_workers = workers
    done = set()
    results = {}
    for job in jobs:
        path = root / "B" / job["partition"] / job["id"] / "result.json"
        if path.is_file():
            results[job["id"]] = read(path)
            done.add(job["id"])
    from scripts.multimodal.mm03_dispatch import physical_queue
    queue, predicted = physical_queue(root,[j for j in jobs if j["id"] not in done])
    if not queue:
        return [results[j["id"]] for j in jobs]
    from scripts.multimodal.mm03_elastic import ordinary_admission
    from scripts.multimodal.mm03_b_parallel import ordinary_capacity
    with (ordinary_admission(root,partition,len(queue),initial_workers) as base_workers,
          ordinary_capacity(root,base_workers,len(queue),cf_free_phase) as workers):
        seq = iter(queue)
        start_epoch = time.time()
        start = time.monotonic()
        steps = 0
        fresh = 0
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("forkserver")) as pool:
            pending = {}
            def refill():
                for job in seq:
                    fut = pool.submit(episode, (str(root), job))
                    pending[fut] = job
                    if len(pending) >= 2 * workers:
                        break
            refill()
            while pending:
                finished, _ = wait(pending, return_when=FIRST_COMPLETED)
                for fut in finished:
                    job = pending.pop(fut)
                    row = fut.result()
                    results[job["id"]] = row
                    fresh += 1
                    steps += row["physics_steps"]
                elapsed = time.monotonic() - start
                emit(root / "B" / "physical_progress.json", dict(partition=jobs[0]["partition"],
                     cases_done=len(results), planned=len(jobs), workers=workers, launch_workers=initial_workers,
                     worker_target_source=str(target_file) if target_file.exists() else "launch configuration",
                     wall_s=elapsed, completed_here=fresh, steps_here=steps, steps_s=steps/max(elapsed, 1e-6),
                     resumed_cases=len(done), processes=list(pool._processes)))
                refill()
        duration = time.monotonic()-start
        timing = dict(partition=partition, workers=workers, ordinary_base=base_workers,
                      borrowed_cf_capacity=max(0,workers-base_workers), predicted_cases=predicted,
                      start_epoch=start_epoch, elapsed_s=duration, physical_substeps=steps, cases=fresh,
                      substeps_per_s=steps/duration, dispatch_order=[j["id"] for j in queue],
                      worker_case_wall_s=sum(results[j["id"]]["wall_s"] for j in queue))
        folder = root/"B"/"native_batch_timings"
        emit(folder/f"{time.time_ns()}.json",timing)
    return [results[j["id"]] for j in jobs]


def refresh_coordinator(root):
    """Request a one-time code reload at a recorded optimizer-stage boundary."""
    root = Path(root).resolve()
    state = read(root / "status" / "B.json")
    if state["state"] != "running":
        raise ValueError("Only an active B coordinator can receive a refresh request")
    pid = state["pid"]
    stamp = Path(f"/proc/{pid}/stat").read_text().split(") ",1)[1].split()[19]
    if str(state["pid_stamp"]) != stamp:
        raise ValueError("B process identity changed")
    req = dict(parent_pid=pid, parent_stamp=stamp, attempt=state["attempt"],
               reason="adopt verified CPU/GPU pipelining at an existing durable training receipt")
    emit(root / "B" / "coordinator_refresh.json", req)
    print(json.dumps(req), flush=True)


def run(args):
    root = args.root.resolve()
    from scripts.multimodal.mm03_elastic import announce
    announce(root)
    out = root / "B"
    jobs = teacher_jobs()
    freeze_file(out / "teacher_registration.json", dict(
        base="2026-11-26 registered 3 train scenes × 4 tasks × 8 perturbation seeds",
        execution_choices="Original plan gave the number of seeds only. These explicit IDs and jitter "
                          "were fixed before collection. First seed uses the exact training scene. "
                          "Other seeds add common side/goal-paired uniform dx ±4 mm, dy ±3 mm, yaw ±0.25 deg.",
        seeds=list(PERTURBATION_SEEDS), physics="native MuJoCo 3.3.0; 10 × .002 s; original twelve events",
        train=jobs))
    rows = batch(root, jobs, args.workers)
    emit(out / "teacher_cases.json", rows)
    from scripts.multimodal.mm03_b_rounds import longitudinal
    longitudinal(root, args.workers)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True, type=Path)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--refresh-coordinator", action="store_true")
    args = p.parse_args()
    if args.refresh_coordinator:
        refresh_coordinator(args.root)
        raise SystemExit(0)
    if args.workers < 1:
        p.error("workers must be positive")
    if Path(sys.prefix) != (REPO / ".venv") and os.getenv("MM03_B_NATIVE_BOOT") != "1":
        os.environ["MM03_B_NATIVE_BOOT"] = "1"
        os.execv(str(NATIVE), [str(NATIVE), "-u", "-m", "scripts.multimodal.mm03_b", *sys.argv[1:]])
    run(args)
