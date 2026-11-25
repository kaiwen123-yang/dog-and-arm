"""Run and index the registered RefXY2 physics packages using the original judges."""
import argparse
import csv
import fcntl
import json
from pathlib import Path
import subprocess
import time

import numpy as np

ROUND = Path("refxy2_pair_20261125")
OUT = Path("results/b0") / ROUND
RAW = Path("results/raw_large/b0") / ROUND
FREE_SOURCE = Path("/root/autodl-tmp/dog-and-arm-b0/results/raw_large/b0/native_teacher_20261121_r1")
REFERENCE = Path("results/raw_large/b0/full_warp_hold_park_r1")
LIMITS = {"pull": (5872, 5948), "push": (5870, 5946)}
METHOD = {"measured": "SuperMimic-M1Piper-RefXY2-v1", "zero": "SuperMimic-M1Piper-RefXY2-zero-v1"}


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def collect_video(dest, checkpoint, backend, branch, node):
    from scripts.b0.official_flow_eval import export_complete_videos
    export_complete_videos(dest, checkpoint, backend)
    for path in dest.glob("*/full/nominal/video_manifest.json"):
        record = read(path)
        if "method_id" in record:
            continue
        case = read(path.parent / "result.json")
        ticks = np.load(Path(case["raw_directory"]) / "physics_step.npy")
        record.update(method_id=METHOD[branch], branch=branch, local_update=node, run="refxy2_pair_s0_v1",
                      shared_plus_zero=node == 0, reference=case["episode"], task_phases=case["phases"],
                      first_step=int(ticks[0]), last_step=int(ticks[-1]), physics_gate_passed=case["passed"])
        write(path, record)
        print("V0", path, record["video"], flush=True)


def run_group(branch, node, label, backend, protocol, reverse):
    ck = RAW / branch / f"checkpoint_{node:06}.pt"
    sub = ROUND / "assessment" / label
    run_name = f"{backend}_{protocol}"
    dest = Path("results/b0") / sub / run_name
    full = protocol == "full"
    if not (dest / "evaluation.json").is_file():
        shell = "scripts/project_env.sh" if backend == "native" else "scripts/b0/env.sh"
        cmd = ["bash", shell, "python", "-u", "scripts/b0/eval_contact_segments.py", "--checkpoint", str(ck),
               "--backend", backend, "--round", str(sub), str(sub), "--run", run_name, "--paper-score",
               "--warning-log", str(OUT / "assessment" / label / "warnings.jsonl")]
        if full:
            cmd += ["--record-servo", "--full-task", "--references", str(REFERENCE),
                    "--side", *(("push", "pull") if reverse else ("pull", "push"))]
        else:
            cmd += ["--manifest", f"config/b0/contact_dev_{protocol}.json", "--formal-contact"]
        if dest.exists():
            cmd.append("--resume")
        with subprocess.Popen(cmd) as process:
            while full and process.poll() is None:
                collect_video(dest, ck, backend, branch, node)
                time.sleep(2)
            if process.wait():
                raise subprocess.CalledProcessError(process.returncode, cmd)
    if full:
        collect_video(dest, ck, backend, branch, node)


def full_windows(case):
    import mujoco
    from learning.b0.contact_events import FrozenDoorReference
    from learning.b0.physics import build
    from scripts.b0.pregrasp_geometry import fk, longest, norms, rotate

    raw = Path(case["raw_directory"])
    ref = REFERENCE / case["episode"]
    model = build(case["actual_config"])
    data = mujoco.MjData(model)
    frozen = FrozenDoorReference.from_episode(ref, model)
    target, orient_goal = frozen.endpoint_pose["pregrasp"]
    lo, hi = LIMITS[case["side"]]
    obs = dict(zip(case["readiness_columns"], np.load(raw / "readiness.npy").T))
    with np.load(raw / "solved_servo_trace.npz") as trace:
        k = trace["step"]
        q = trace["q_pre"].astype(np.float64)
    np.testing.assert_array_equal(k, np.arange(case["physics_steps"]))
    np.testing.assert_array_equal(k + 1, obs["step"])
    actual_phase = obs["actual_phase"].astype(int)
    pre = actual_phase == case["phases"].index("pregrasp")
    fixed = (k >= lo) & (k < hi)
    active = pre & obs["ramp"].astype(bool)
    ready = pre & obs["ready"].astype(bool)
    xyz, orientation, rot = fk(model, data, q)
    dist = norms(xyz-target)
    angle = np.arccos(np.clip((np.sum(orientation*orient_goal, axis=(1, 2))-1)/2, -1., 1.))
    qr = np.load(ref/"substeps/qpos.npy", mmap_mode="r")[k].astype(np.float64)
    xref, _, rotref = fk(model, data, qr)
    def local(qpos):
        result = qpos.copy()
        result[:, :7] = (0, 0, 0, 1, 0, 0, 0)
        return fk(model, data, result)[0]
    fr, fa = local(qr), local(q)
    terms = dict(root_translation=q[:, :3]-qr[:, :3], root_rotation=rotate(rot-rotref, fr),
                 arm_fk=rotate(rot, fa-fr), reference_progress=xref-target)
    direction=(xyz-target)/np.maximum(dist[:, None], 1e-15)
    def describe(mask):
        if not mask.any():
            return None
        d = dist[mask] * 1000.
        return dict(n=int(mask.sum()), k_first=int(k[mask][0]), k_last=int(k[mask][-1]),
                    min_mm=float(d.min()), p50_mm=float(np.median(d)), p95_mm=float(np.percentile(d,95)),
                    max_mm=float(d.max()), p95_over_3mm=float(np.percentile(d,95)/3),
                    position_ticks=int(np.count_nonzero(d <= 3.)),
                    longest_original_ready_ticks=longest(mask & ready),
                    longest_endpoint_ready_ticks=longest(mask & (dist <= .003) & (angle <= .02) & (k >= lo)),
                    phases={case["phases"][p]: int(np.count_nonzero(mask & (actual_phase == p)))
                            for p in np.unique(actual_phase[mask])},
                    mean_signed_projection_mm={key: float((v[mask]*direction[mask]).sum(1).mean()*1000)
                                               for key,v in terms.items()})
    return dict(index="q_pre at interval k; readiness.step=k+1", fixed_start=lo, fixed_stop=hi,
                fixed_available=int(fixed.sum()), fixed=describe(fixed) if fixed.sum()==hi-lo else None,
                actual_pregrasp=describe(pre), actual_after_ramp=describe(active),
                max_observed_judge_vs_pre_fk_mm=float(np.max(np.abs(obs["endpoint_m"][pre]-dist[pre]))*1000)
                    if pre.any() else None, original_longest_ready_ticks=int(case["longest_ready_steps"].get("pregrasp",0)))


def package(branch, node, repeat=False):
    from scripts.b0 import official_flow_free as free
    if node not in (0, 200, 500, 1000) or (node == 0 and branch != "measured"):
        raise ValueError("Only registered nodes and the shared +0 package are supported")
    if repeat and node not in (0,200):
        raise ValueError("Only extension decision packages are repeated")
    label = ("shared_0" if node==0 else f"{branch}_{node}") + ("_repeat" if repeat else "")
    dest = OUT/"assessment"/label
    dest.mkdir(parents=True,exist_ok=True)
    full_only = repeat or node == 500
    backends = ("native","warp") if repeat else ("warp","native")
    rows = []
    for backend in backends:
        for protocol in (("full",) if full_only else ("full","v1","hold_margin_v2")):
            run_group(branch,node,label,backend,protocol,repeat)
            group = dest / f"{backend}_{protocol}"
            for p in sorted(group.glob("*/*/nominal/result.json")):
                a = read(p)
                score = p.parent/"return.json"
                row=dict(id=f"{label}/{backend}/{p.parent.relative_to(group)}",kind="full" if protocol=="full" else "contact",
                         backend=backend, reference=a["episode"], side=a["side"], segment=a["segment"],
                         passed=a["passed"], events=[e["phase"] for e in a["events"]], steps=a["physics_steps"],
                         first_failure=a["first_failure"], final_door_deg=a["final_door_deg"],
                         peak_net_force_n=a.get("measured_peak_net_force_n"), result=str(p), score=str(score),
                         raw=a["raw_directory"])
                if protocol=="full":
                    assert a["prefix_physics_steps"]==0 and a["start_substep"]==0
                    row["windows"] = full_windows(a)
                rows.append(row)
    if not full_only:
        free.RAW = RAW/branch
        free.OUT = dest
        sub = dest/"free"/f"u{node:06}"
        if not (sub/"evaluation.json").exists():
            free.evaluate(node,FREE_SOURCE)
        with (sub/"cases.csv").open() as f:
            for a in csv.DictReader(f):
                rows.append(dict(id=f"{label}/free/{a['reference_id']}/{a['case']}", kind="free",
                                 backend="warp", reference=a["reference_id"], passed=a["passed"]=="True",
                                 result=str(sub/"cases.csv"), metrics=a))
    assert sum(r["kind"]=="full" for r in rows)==4
    assert sum(r["kind"]=="contact" for r in rows)==(0 if full_only else 20)
    assert sum(r["kind"]=="free" for r in rows)==(0 if full_only else 60)
    assert len({r["id"] for r in rows})==len(rows)
    write(dest/"package.json",dict(branch=branch,local_update=node,method_id=METHOD[branch],common_plus_zero=node==0,
                                   repeat=repeat,registered_process_node=node==500,cases=rows))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("branch", choices=METHOD)
    p.add_argument("node", type=int)
    p.add_argument("--repeat", action="store_true")
    a = p.parse_args()
    (OUT/"assessment").mkdir(parents=True, exist_ok=True)
    with (OUT/"assessment"/f".{a.branch}_{a.node}_{a.repeat}.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        package(a.branch, a.node, a.repeat)
