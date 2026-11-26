"""Within-input inference comparison and independent native CPU-policy repeat."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO/"scripts"))


def maximum(a, b):
    return float(np.max(np.abs(np.asarray(a, dtype=float)-np.asarray(b, dtype=float))))


def same_input(path, package, new):
    import torch
    from learning.multimodal.actor import OnlinePolicy
    torch.set_num_threads(1)
    arrays = {k: np.load(path/(k+".npy"), mmap_mode="r") for k in
              ("t", "proprio", "previous_action", "rgb", "depth", "depth_valid", "image_t", "image_index", "action_raw")}
    meta = json.loads((path/"metadata.json").read_text())
    first_new = np.load(new/"action_raw.npy")[0]
    results = {}
    for name, device in (("original_cpu", "cpu"), ("cuda_singleton", "cuda"), ("cuda_singleton_no_tf32", "cuda")):
        if name.endswith("no_tf32"):
            torch.backends.cudnn.allow_tf32 = False
            torch.backends.cuda.matmul.allow_tf32 = False
        policy = OnlinePolicy.from_checkpoint(package, device)
        policy.reset(meta["task_text"])
        errors = []
        for i in range(min(100, len(arrays["action_raw"]))):
            f = arrays["image_index"][i]
            x = [np.array(arrays[k][f], copy=True) for k in ("rgb", "depth", "depth_valid")]
            pred = policy.step(*x, arrays["proprio"][i], arrays["previous_action"][i],
                               image_age_s=arrays["t"][i]-arrays["image_t"][f], return_raw=True)
            if i==0:
                first = maximum(pred, first_new)
            errors.append(maximum(pred, arrays["action_raw"][i]))
        results[name] = dict(first_max_abs_vs_old=errors[0], first_max_abs_vs_new=first,
                             max_abs_vs_old_on_100_fixed_inputs=max(errors), cases=len(errors))
    return results


def run(root):
    from scripts.multimodal.mm03_a import emit
    from scripts.multimodal.mm03_a_rescue import rescue_jobs, run_rescue
    from scripts.multimodal.mm02_inference import PolicyPipe
    base = root/"A"/"cpu_parity"
    base.mkdir(exist_ok=True)
    name = "supervised_aggregate_pull15_student"
    job = next(j for j in rescue_jobs(REPO) if j["id"]==name)
    parent = Path("/root/autodl-tmp/mm02-20261125/formal/formal_supervised_aggregate_tr_nominal_pull_15_pure")
    source = parent/"episode"
    gpu = root/"A"/"rescue"/name
    cpu = base/name
    torch = str(REPO/".conda/envs/arm-and-dog/bin/python")
    if not cpu.is_dir():
        tmp = Path(tempfile.mkdtemp(prefix=".repeat-", dir=base))
        row = run_rescue(job, tmp, client_factory=lambda p:PolicyPipe(torch, p))
        emit(tmp/"result.json", row)
        tmp.rename(cpu)
    inputs = [torch, "-u", str(Path(__file__).resolve()), "--inputs", str(source),
              "--package", job["checkpoint"], "--new", str(gpu/"episode")]
    infer = json.loads(subprocess.check_output(inputs, cwd=REPO))
    result = {}
    for label, path in (("new_cuda_batched", gpu), ("independent_original_cpu", cpu)):
        arr = {}
        for k in ("qpos", "qvel", "proprio", "previous_action", "rgb", "depth", "depth_valid",
                  "action_raw", "action_clipped", "physical_target", "applied_ctrl"):
            x = np.load(source/(k+".npy"), mmap_mode="r")
            y = np.load(path/"episode"/(k+".npy"), mmap_mode="r")
            n = min(len(x), len(y))
            d = np.abs(np.asarray(x[:n], dtype=float)-np.asarray(y[:n], dtype=float))
            arr[k] = dict(first_max_abs=float(np.nanmax(d[0])), overlap_max_abs=float(np.nanmax(d)), overlap=n)
        row = json.loads((path/"result.json").read_text())
        result[label] = dict(case=str(path), steps=row["physics_steps"], failure=row["first_failure"]["reason"],
                             differences_from_original=arr)
    old = json.loads((parent/"result.json").read_text())
    emit(base/"comparison.json", dict(source=str(source), checkpoint=job["checkpoint"],
         original_steps=old["physics_steps"], original_first_failure=old["first_failure"]["reason"],
         same_inputs=infer, native=result, extra_physics_steps=result["independent_original_cpu"]["steps"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path)
    ap.add_argument("--inputs", type=Path)
    ap.add_argument("--package", type=Path)
    ap.add_argument("--new", type=Path)
    args = ap.parse_args()
    if args.inputs is not None:
        print(json.dumps(same_input(args.inputs, args.package, args.new)))
    else:
        run(args.root)
