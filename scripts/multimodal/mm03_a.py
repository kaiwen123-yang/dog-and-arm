"""MM03 A execution and resume entry point. Completed case directories are immutable."""
import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))
SEEDS = (1701, 1702, 1703)


def emit(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix="."+path.name, delete=False) as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")
    os.replace(f.name, path)


def work(item):
    group, job, root = item
    case = root/"A"/group/job["id"]
    case.parent.mkdir(parents=True, exist_ok=True)
    if case.is_dir():
        return json.loads((case/"result.json").read_text())
    attempt = Path(tempfile.mkdtemp(prefix="."+case.name+".attempt-", dir=case.parent))
    try:
        if group == "rescue":
            from scripts.multimodal.mm03_a_rescue import run_rescue
            result = run_rescue(job, attempt)
        else:
            from scripts.multimodal.mm03_a_commands import run_command
            result = run_command(job, attempt)
        result.update(case_dir=str(case), worker_pid=os.getpid(), completed_utc=datetime.now(timezone.utc).isoformat())
        emit(attempt/"result.json", result)
        attempt.rename(case)
        return result
    except BaseException:
        emit(attempt/"exception.json", dict(job=job, pid=os.getpid(), traceback=traceback.format_exc()))
        raise


def batch(root, workers, items, phase):
    todo = []
    results = []
    for group, job in items:
        result = root/"A"/group/job["id"]/"result.json"
        if result.exists():
            results.append(json.loads(result.read_text()))
        else:
            todo.append((group, job, root))
    start = time.monotonic()
    skipped = len(results)
    recovered_steps = sum(r["physics_steps"] for r in results)
    queue = iter(todo)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = {}
        def submit():
            item = next(queue, None)
            if item is not None:
                pending[pool.submit(work, item)] = item[1]["id"]
        for _ in range(min(workers, len(todo))):
            submit()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                case = pending.pop(future)
                result = future.result()
                results.append(result)
                seconds = time.monotonic()-start
                new_steps = sum(r["physics_steps"] for r in results)-recovered_steps
                status = dict(phase=phase, complete=len(results), scheduled=len(items), resumed=skipped,
                              case=case, last_success=result["success"], last_steps=result["physics_steps"],
                              completed_physics_steps=new_steps+recovered_steps, active=list(pending.values()),
                              newly_completed_episodes_s=(len(results)-skipped)/seconds, measured_physics_steps_s=new_steps/seconds,
                              timestamp=datetime.now(timezone.utc).isoformat())
                emit(root/"A"/"progress.json", status)
                print(json.dumps(status), flush=True)
                submit()
    results.sort(key=lambda r:r["id"])
    emit(root/"A"/"blocks"/(phase+".json"), dict(cases=results, physics_steps=sum(r["physics_steps"] for r in results)))
    return results


def train(root, seed, block, workers):
    folder = root/"A"/"low"/f"seed{seed}"/f"block{block}"
    if (folder/"train_result.json").exists():
        return
    torch = REPO/".conda/envs/arm-and-dog/bin/python"
    args = [str(torch), "-u", "-m", "scripts.multimodal.mm03_a_train", "--root", str(root),
            "--seed", str(seed), "--block", str(block)]
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/"training.log").open("a", buffering=1) as log:
        subprocess.run(args, cwd=REPO, stdout=log, stderr=subprocess.STDOUT, check=True)


def run(args):
    from scripts.multimodal.mm03_a_commands import make_jobs
    from scripts.multimodal.mm03_a_rescue import rescue_jobs
    root = args.root.resolve()
    state = root/"A"
    state.mkdir(parents=True, exist_ok=True)
    datasets = json.loads((REPO/"results/multimodal/mm02_20261125/manifest.json").read_text())["parent"]
    def trials(stage, seed=None, block=None, checkpoint=None):
        return [{**j, "arm_parent": datasets, "checkpoint": str(checkpoint) if checkpoint else None}
                for j in make_jobs(stage, seed, block)]
    initial = rescue_jobs(REPO)
    commands = trials("command_teacher")
    development = trials("development", SEEDS[0], 0)
    design = dict(wheels=["FAR", "FBL", "RAR", "RBL"], command_teacher=commands,
                  channel_interventions=initial, development_design=development, seeds=SEEDS,
                  corrective_blocks_max=2, local_development_target=36,
                  local_pass="Full 30 s, no registered stability/limit/collision/saturation/solver fault, at least 1 s terminal continuous P6 stopped/4-wheel support, peak drift after last stop <= original 20 mm station tolerance, median body-axis measured/requested response >=0.5 on each commanded nonzero axis.",
                  controller="Local-v1 uniformly uses travel PI cap; no mode/phase, no ideal world state in low deployment.",
                  nominal_adapter_cases="B/teachers, exact unperturbed tr_nominal x pull/push x 15/25; same episodes counted once.",
                  low_hold="Each high-level effective request held 20 ms; local integrators update every 2 ms. Pre-bias normalized targets add original bias only in physical servo.")
    emit(state/"design.json", design)
    items = []
    # Start actual interventions and command collection concurrently in the same bounded pool.
    for i in range(max(len(initial), len(commands))):
        if i < len(initial):
            items.append(("rescue", initial[i]))
        if i < len(commands):
            items.append(("command_teacher", commands[i]))
    batch(root, args.workers, items, "initial_collection")
    active = list(SEEDS)
    summaries = {}
    for block in range(3):
        if block:
            pending = []
            for seed in active:
                base = state/"low"/f"seed{seed}"
                pending.extend([(f"low/seed{seed}/block{block}/correction", j) for j in
                                trials("correction", seed, block, base/f"block{block-1}"/"deploy.pt")])
            batch(root, args.workers, pending, f"correction_{block}")
        with ThreadPoolExecutor(max_workers=min(3, args.workers)) as pool:
            list(pool.map(lambda s: train(root, s, block, args.workers), active))
        tests = []
        for seed in active:
            prefix = f"low/seed{seed}/block{block}"
            tests.extend([(prefix+"/development", j) for j in
                          trials("development", seed, block, state/prefix/"deploy.pt")])
        results = batch(root, args.workers, tests, f"development_{block}")
        retry = []
        for seed in active:
            rows = [r for r in results if r["seed"] == seed]
            count = sum(r["success"] for r in rows)
            if len(rows) != 40:
                raise ValueError("Incomplete local development suite")
            summaries[seed] = dict(block=block, successes=count, cases=len(rows),
                                   latest=str(state/"low"/f"seed{seed}"/f"block{block}"/"deploy.pt"))
            if count<36:
                retry.append(seed)
        emit(state/"low"/"summary.json", summaries)
        active = retry
        if not active:
            break
    if active:
        tests = []
        for seed in active:
            prefix = f"low/seed{seed}/block2"
            tests.extend([(prefix+"/oracle", j) for j in trials("oracle", seed, 2, state/prefix/"deploy.pt")])
        batch(root, args.workers, tests, "low_true_velocity_oracle")
    emit(state/"complete.json", dict(status="completed_A", low=summaries,
         rescue=44, initial_command_trials=96, source="native simulation",
         adapter_reference="B/teachers (four shared nominal cases)", hardware_commands=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    options = parser.parse_args()
    if options.workers<1:
        parser.error("--workers must be positive")
    native = REPO/".venv/bin/python"
    # A may be dispatched from the common system launcher or the Torch binary.
    if Path(sys.prefix).resolve() != (REPO/".venv").resolve():
        os.execv(str(native), [str(native), "-u", str(Path(__file__).resolve()), *sys.argv[1:]])
    options.root.mkdir(parents=True, exist_ok=True)
    with (options.root/"lane_A.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(options)
