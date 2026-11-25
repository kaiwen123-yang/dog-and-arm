"""Execute the four registered P6 adapter and eight isolated feasibility cases."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from pathlib import Path
from time import perf_counter

import mujoco as mj
import numpy as np

from learning.b0.physics import build
from learning.multimodal.judge import DoorTaskJudge
from scripts.b0.eval_contact_segments import continuous_initial
from scripts.multimodal.collect import ROOT, load_scenes
from scripts.multimodal.collect_feasibility import teacher_config
from scripts.multimodal.correction_teacher import P6CorrectionTeacher, capture_physics, restore_physics


def checkpoint_probe(model, original, teacher, frame0, cfg):
    """Replay one held interval twice, with an independent restored physical object.

    The nominal case's following 10 actual substeps supply the other side of
    this comparison. Return only isolated state here, never write to original.
    """
    d = restore_physics(model, capture_physics(model, original))
    restored = P6CorrectionTeacher(model, frame0, cfg)
    restored.restore(teacher.snapshot())
    return d, restored


def held_servo(d, model, mapping, physical):
    # Match p6_single_door's original XML-unit division (including rounding).
    ids = mapping.actuator_ids
    cmd = physical * mapping.finger_factor
    pos = np.r_[0:12, 16:23]
    cmd[pos] += d.qfrc_bias[mapping.dof[pos]] / model.actuator_gainprm[ids[pos], 0]
    d.ctrl[ids] = cmd


def run_case(scene, side, goal, output, parent_run):
    case_id = f"{scene['id']}_{side}_{goal}"
    dest = output / case_id
    case_path = dest / "result.json"
    if case_path.exists():
        return json.loads(case_path.read_text())
    dest.mkdir(parents=True, exist_ok=True)
    start = perf_counter()
    cfg = teacher_config(side, goal, scene)
    m = build(cfg)
    if mj.__version__ != "3.3.0":
        raise ValueError(f"native P6 evaluation requires MuJoCo 3.3.0; got {mj.__version__}")
    d, _, _ = continuous_initial(m, cfg, None)
    frame0, _, _ = continuous_initial(m, cfg, None)
    teacher = P6CorrectionTeacher(m, d, cfg)
    a = teacher.mapping
    judge = DoorTaskJudge(m, cfg, side, goal)
    phase_counts, reasons = Counter(), Counter()
    labels, states, velocities, ticks = [], [], [], []
    margin = np.full(6, np.inf)
    min_margin = []
    probe = None
    delta = {}
    probe_states = []
    is_nominal = scene["id"] == "tr_nominal"
    while not (judge.passed or judge.failure):
        k = teacher.step
        if is_nominal and k == 1000:
            probe = checkpoint_probe(m, d, teacher, frame0, cfg)
            meter = DoorTaskJudge(m, cfg, side, goal).meter
        sample = teacher.before(d)
        if sample is not None:
            held = sample.physical
            labels.append(sample.raw.copy())
            states.append(d.qpos.copy())
            velocities.append(d.qvel.copy())
            ticks.append(k)
            reasons[sample.reason] += 1
            phase_counts[sample.phase] += 1
        q, v = d.qpos.copy(), d.qvel.copy()
        held_servo(d, m, a, held)
        mj.mj_step(m, d)
        c = judge.observe(d, q, v)
        teacher.after(d, c)
        if probe is not None:
            branch, restored = probe
            branch_label = restored.before(branch)
            if branch_label is not None:
                branch_held = branch_label.physical
                delta["held_target_max_abs"] = float(np.max(abs(held - branch_held)))
            held_servo(branch, m, a, branch_held)
            mj.mj_step(m, branch)
            restored.after(branch, meter.measure(branch))
            probe_states.append(np.max(np.abs(np.r_[d.qpos - branch.qpos, d.qvel - branch.qvel])))
            if len(probe_states) == 10:
                delta.update(anchor_physics_step=1000, extra_physics_steps=len(probe_states),
                             max_abs_qpos_qvel=float(max(probe_states)),
                             phase_matched=teacher.phase == restored.phase)
                probe = None
        q_arm = d.qpos[teacher.arm.ik.q]
        limits = teacher.arm_bounds
        margin = np.minimum(margin, np.minimum(q_arm - limits[:, 0], limits[:, 1] - q_arm))
        if k % 10 == 0:
            min_margin.append(margin.copy())
    states.append(d.qpos.copy())
    velocities.append(d.qvel.copy())
    for name, values in (("expert_action_raw", labels), ("boundary_qpos", states),
                         ("boundary_qvel", velocities), ("decision_step", ticks),
                         ("minimum_arm_margin_rad", min_margin)):
        np.save(dest / (name + ".npy"), np.asarray(values), allow_pickle=False)
    comparison = None
    if is_nominal:
        parent = parent_run / "data" / f"{scene['id']}_{side}_{goal}_held"
        parent_judge = parent_run / "judge_checks" / f"{side}_{goal}" / "mm01_judgment.json"
        ref = json.loads(parent_judge.read_text())
        old_raw = np.load(parent / "action_raw.npy", mmap_mode="r")
        old_q = np.load(parent / "qpos.npy", mmap_mode="r")
        limit = min(len(labels), len(old_raw))
        observed_events = [x["end_step"] for x in judge.events]
        comparison = dict(source_episode=str(parent), source_judgment=str(parent_judge),
                          old_success=ref["success"], source_decisions_compared=limit,
                          max_abs_boundary_qpos=float(np.max(np.abs(np.asarray(states[:limit])-old_q[:limit]))),
                          max_abs_normalized_request_float32=float(np.max(np.abs(np.asarray(labels[:limit],
                                                                dtype=np.float32)-old_raw[:limit]))),
                          old_event_steps=[x["end_step"] for x in ref["events"]],
                          current_event_steps=observed_events,
                          event_steps_identical=observed_events == [x["end_step"] for x in ref["events"]])
    result = dict(case_id=case_id, case_role="adapter" if is_nominal else "blind_teacher_only",
                  excluded_from_training=True, side=side, target_deg=goal, scene=scene, cfg=cfg,
                  physics_version=mj.__version__, teacher_decision_count=len(labels),
                  teacher_base_updates=teacher.step, teacher_arm_updates=teacher.arm_queries,
                  phase_decisions=dict(phase_counts), label_qualification=dict(reasons),
                  control_events=teacher.events, teacher_failure=teacher.failure,
                  min_arm_margin_rad=margin.tolist(),
                  final_hinge_deg=float(np.rad2deg(d.qpos[teacher.hinge.qposadr.item()])),
                  frame0_arm_home=teacher.arm.home.tolist(), frame0_leg_rest=teacher.drive.leg_rest.tolist(),
                  frame0_jaw_home_m=float(teacher.arm.home_width), same_state_restore=delta or None,
                  original_comparison=comparison, evidence_dir=str(dest),
                  wall_s=perf_counter()-start, **judge.result())
    tmp = case_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    tmp.replace(case_path)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--parent-run", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()
    nominal = next(s for s in load_scenes()["scenes"] if s["id"] == "tr_nominal")
    reg = json.loads((ROOT/"results/planning/multimodal_mm02_20261125/registration.json").read_text())
    cases = [(s, side, goal) for s in (nominal, *reg["splits"]["new_blind_scenes"])
             for side in ("pull", "push") for goal in (15, 25)]
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_case, *row, args.output, args.parent_run) for row in cases]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps({k: row[k] for k in ("case_id", "success", "next_phase", "physics_steps")}), flush=True)
    (args.output / "teacher_cases.json").write_text(json.dumps(sorted(rows, key=lambda r: r["case_id"]),
                                                              indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
