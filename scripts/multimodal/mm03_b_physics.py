"""Frame-zero native MM03 B episodes, continuous P6 prefixes and true successors."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import pickle
from pathlib import Path
import time

import mujoco as mj
import numpy as np

from learning.b0.physics import build
from learning.multimodal.judge import DoorTaskJudge, PHASES
from scripts.b0.eval_contact_segments import continuous_initial
from scripts.multimodal.collect import EpisodeWriter, instruction
from scripts.multimodal.collect_feasibility import teacher_config
from scripts.multimodal.correction_teacher import P6CorrectionTeacher, capture_physics
from scripts.multimodal.mm02_physics import JUDGE_DYNAMIC, digest, emit, scenes
from scripts.multimodal.mm03_adapter import CommandTeacher

REG = Path(__file__).resolve().parents[2] / "results/planning/multimodal_mm03_20261126/registration.json"


class BWriter(EpisodeWriter):
    def supervision_mask(self, arrays, success):
        return arrays["action_supervision_mask"] & arrays["valid_transition"]


def complete_result(case, root):
    # The episode is published by directory rename. Recover the case record after an
    # interruption between this rename and result.json without repeating physics.
    path = case / "episode"
    meta = json.loads((path / "metadata.json").read_text())
    result = dict(meta["case_result"], raw_episode=str(path),
                  bc_labels=meta["bc_labels"], camera_frames=meta["frames"])
    emit(case / "result.json", result)
    if result["mode"] == "pure" and result["success"] and "reload" not in result["partition"]:
        events = root / "B" / "success"
        emit(events / (result["episode_id"] + ".json"), dict(case=str(case / "result.json"),
             episode=str(path), checkpoint=result["checkpoint"], split=result["partition"],
             classification="pure_frame0", action_source="student_all_23"))
    return result


def scene_for(job):
    catalog = scenes()
    if job["scene"] not in catalog:
        blind = json.loads(REG.read_text())["splits"]["new_blind_scenes"]
        catalog.update((scene["id"], scene) for scene in blind)
    scene = dict(catalog[job["scene"]])
    if "train_perturbation" in job:
        if scene["split"] != "train":
            raise ValueError("Training jitter supplied outside training")
        scene["perturbation"] = job["train_perturbation"]
    return scene


def save_handoff(case, model, data, command, original, judge, writer, previous, tick, image, job):
    """Exact pre-action solver, both teacher histories and actual finite-window policy context."""
    case.mkdir(parents=True,exist_ok=True)
    arrays = writer.arrays
    indices = np.maximum(np.arange(tick-9,tick),0)
    history = np.stack([arrays["proprio"][k] for k in indices])
    past = np.stack([arrays["action_clipped"][k-1] if k else np.zeros_like(previous) for k in indices])
    physics = capture_physics(model,data)
    identity = digest(np.ascontiguousarray(physics["integration"]).tobytes())
    path = case / ("handoff_" + identity + ".pkl")
    if not path.exists():
        tmp = case / (path.name + ".part")
        with tmp.open("wb") as f:
            pickle.dump(dict(schema="mm03_actual_prefix_handoff_v1",source=job,physics=physics,
                teacher=command.snapshot(),independent_p6=original.snapshot() if original is not None else None,
                judge=deepcopy({k:getattr(judge,k) for k in JUDGE_DYNAMIC}),previous=previous.copy(),
                prefix=(history,past),tick=tick,time=float(data.time),image_t=arrays["image_t"][-1],
                image=tuple(x.copy() for x in image), full_raw_prefix="episode rows [0,tick)"),f,protocol=5)
        os.replace(tmp,path)
    return str(path)


def episode(task):
    root, job = task
    root = Path(root)
    case = root / "B" / job["partition"] / job["id"]
    mode = job["mode"]
    if job["scene"].startswith("te_mm03") and not (root / "B" / "candidate_freeze.json").is_file():
        raise ValueError("All candidate packages must be frozen before opening a new combination")
    if (case / "result.json").exists():
        return json.loads((case / "result.json").read_text())
    if (case / "episode" / "metadata.json").exists():
        return complete_result(case, root)
    scene = scene_for(job)
    cfg = teacher_config(job["side"], job["goal"], scene)
    model = build(cfg)
    if mj.__version__ != "3.3.0" or abs(model.opt.timestep - .002) > 1e-12:
        raise ValueError("MM03 requires native MuJoCo 3.3.0 at 2 ms")
    d, _, _ = continuous_initial(model, cfg, None)
    initial_digest = digest(np.r_[d.qpos, d.qvel].astype("<f8").tobytes())
    judge = DoorTaskJudge(model, cfg, job["side"], job["goal"])
    evaluate_only = job["use"] == "evaluation"
    student = None
    command = None
    original = None
    if mode not in ("teacher", "p6_reference"):
        from scripts.multimodal.mm03_inference import PolicyClient
        student = PolicyClient(job["checkpoint"], kind="task")
        student.reset(instruction(job["side"], job["goal"]))
    if not evaluate_only or mode == "teacher":
        command = CommandTeacher(model, d, cfg)
    parity_path = root / "B" / f'prefix_p6_parity_{job["side"]}.json'
    has_original_output = command is not None and hasattr(command,"original_boundary_label")
    shared_p6 = mode == "prefix" and has_original_output and parity_path.is_file()
    if mode == "p6_reference" or (mode == "prefix" and not shared_p6):
        original = P6CorrectionTeacher(model, d, cfg)
    parity_ticks = 0
    parity_max = 0.
    parity_phase_mismatch = False
    parity_phases = set()
    writer = BWriter(model, cfg, scene, job["side"], job["goal"], job["id"], mode)
    writer.meta.update(schema="mm03_causal_task_v1", source=mode, source_policy=job["method"],
        seed=job["seed"], round=job["round"], partition=job["partition"], checkpoint=job.get("checkpoint"),
        phase_owner="original independent DoorTaskJudge", judge_phase_names=PHASES,
        velocity_request_units=["m/s", "rad/s"], expert_request_source="CommandTeacher effective request",
        expert_targets="same CommandTeacher query: normalized pre-bias 23 and effective vx,wz",
        teacher_prefix_executor="original P6 held at 20ms" if mode == "prefix" else None,
        student_state="10 observations and actual previous actions maintained from physical frame0",
        execution_source_values={"0": "student", "1": "teacher"}, seed_perturbation=scene["perturbation"])
    m = writer.mapping
    prev = np.zeros(23, dtype=np.float32)
    tick, switched = 0, None
    handoff = None
    teacher_decisions = label_counts = 0
    begun = time.monotonic()
    groups = Counter()
    min_margin = np.full(6, np.inf)
    min_height = np.inf
    max_support_gap = 0.
    try:
        while not judge.failure and not judge.passed:
            t = float(d.time)
            p, image = writer.boundary(t, d.qpos, d.qvel)
            pred = None
            if student is not None:
                # This also updates the causal policy during the real teacher prefix.
                proposal = student.step(p, prev, image, writer.arrays["image_t"][-1], t, return_aux=True)
                pred = proposal["raw"]
                writer.arrays["student_high_request"].append(proposal["high"].copy())
                writer.arrays["student_estimated_vx_wz"].append(proposal["estimate"].copy())
            if mode == "prefix" and switched is None and tick >= 1 and judge.i >= job["switch_phase"] and d.time >= .30:
                switched = tick
                handoff = save_handoff(case,model,d,command,original,judge,writer,prev,tick,image,job)
            use_teacher = mode in ("teacher", "p6_reference") or (mode == "prefix" and switched is None)
            label = command.before(d) if command is not None else None
            if original is not None and use_teacher:
                p6_label = original.before(d)
                if mode=="prefix" and has_original_output:
                    base_label = command.original_boundary_label
                    parity_ticks += 1
                    parity_phases.add(p6_label.phase)
                    parity_phase_mismatch |= p6_label.phase != base_label.phase
                    parity_max = max(parity_max, float(np.max(np.abs(p6_label.raw-base_label.raw))))
            if use_teacher:
                if shared_p6:
                    executed = command.original_boundary_label.raw
                else:
                    executed = p6_label.raw if original is not None else label.raw
            else:
                executed = pred
            if not np.isfinite(executed).all():
                raise FloatingPointError(f"Nonfinite actual request in {job['id']} at {t}")
            actual = np.clip(executed, -1., 1.)
            physical = m.offset + m.scale * actual
            if label is not None:
                request = np.asarray(command.request, dtype=np.float32).copy()
                if request.shape != (2,) or not np.isfinite(request).all():
                    raise ValueError("Invalid command-conditioned teacher velocity label")
                for key, value in (("expert_action_raw", label.raw), ("expert_action_target", label.target),
                                   ("expert_request", request), ("expert_label_valid", bool(label.valid)),
                                   ("expert_label_reason", label.reason)):
                    writer.arrays[key].append(np.array(value, copy=True))
                if label.valid and (mode == "teacher" or not use_teacher):
                    groups[judge.i // 2] += 1
                    label_counts += 1
            valid = label is not None and label.valid and (mode == "teacher" or not use_teacher)
            writer.action(executed, actual, physical, judge.phase, valid)
            writer.arrays["executed_action_clipped"].append(actual.astype(np.float32))
            writer.arrays["judge_phase"].append(judge.i)
            writer.arrays["execution_source"].append(int(use_teacher))
            teacher_decisions += int(use_teacher)
            servo = physical * m.finger_factor
            for substep in range(10):
                if substep:
                    if command is not None:
                        command.before(d)
                    if original is not None and use_teacher:
                        original.before(d)
                q, v = d.qpos.copy(), d.qvel.copy()
                d.ctrl[m.actuator_ids] = servo + d.qfrc_bias[m.dof] * m.bias_gain
                mj.mj_step(model, d)
                contact = judge.observe(d, q, v)
                if command is not None:
                    command.after(d, contact)
                if original is not None and use_teacher:
                    original.after(d, contact)
                writer.substep(d.ctrl[m.actuator_ids], contact.finger_normal)
                min_height = min(min_height, float(d.qpos[2]))
                pos = d.qpos[judge.arm_q]
                min_margin = np.minimum(min_margin, np.minimum(pos - judge.ranges[:, 0], judge.ranges[:, 1] - pos))
                max_support_gap = max(max_support_gap, judge.unloaded * .002)
                if judge.passed or judge.failure:
                    break
            prev = actual.astype(np.float32)
            tick += 1
        writer.boundary(float(d.time), d.qpos, d.qvel)
        verdict = judge.result()
        result = {**job, **verdict, "episode_id": job["id"], "ordered_event_count": len(judge.events),
            "source": ("original_P6_teacher_prefix_then_student" if mode == "prefix" else
                       "command_adapter_teacher" if mode == "teacher" else
                       "original_P6_held_reference" if mode == "p6_reference" else "pure_frame0"),
            "teacher_steps": teacher_decisions, "teacher_substeps": 10 * teacher_decisions -
            (10 - writer.arrays["substeps"][-1] if use_teacher else 0),
            "student_steps": tick - teacher_decisions, "prefix_switch_tick": switched,
            "real_solver_handoff":handoff,
            "prefix_reached": switched is not None if mode == "prefix" else None,
            "same_p6_query_reused": shared_p6, "p6_query_comparison_ticks":parity_ticks,
            "p6_query_max_abs":parity_max if parity_ticks else None,
            "eligible_by_group_before_partial_filter": dict(groups), "initial_state_sha256": initial_digest,
            "min_arm_margins_rad": min_margin.tolist(), "min_root_height_m": min_height,
            "max_nonfull_support_s": max_support_gap, "decisions": tick, "wall_s": time.monotonic() - begun,
            "recorded_utc": datetime.now(timezone.utc).isoformat()}
        path = case / "episode"
        writer.save(path, judge.passed, judge.failure["reason"] if judge.failure else None,
                    extra={"case_result": result, "physical_config": cfg,
                           "teacher_failure": command.failure if command else None,
                           "real_prefix_teacher_failure": original.failure if original else None})
        result = complete_result(case, root)
        if (mode=="prefix" and job["group"]==5 and switched is not None and parity_ticks==switched and
                parity_ticks>0 and parity_max==0 and not parity_phase_mismatch):
            from scripts.multimodal.mm03_b import emit as unique_emit
            unique_emit(parity_path, dict(case=str(case/"result.json"), reset=initial_digest,
                checked_continuous_20ms_commands=parity_ticks, all_23_max_abs=parity_max,
                phases=sorted(parity_phases), side=job["side"], method="P6 query cached before local adaptation",
                additional_physics_steps=0))
        print(f"B {job['id']} events={len(judge.events)} result={judge.passed} steps={judge.steps}", flush=True)
        return result
    finally:
        writer.sensors.close()
        if student is not None:
            student.close()
