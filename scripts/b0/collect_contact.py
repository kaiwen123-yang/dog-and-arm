#!/usr/bin/env python3
"""Collect one physically integrated 50 Hz door-teacher episode in a fresh directory."""
from argparse import ArgumentParser
import json
from pathlib import Path
import subprocess

import mujoco as mj
import numpy as np

from scripts.b0.collect_reference import DECIMATION, ROOT, Recorder, dump_json
from learning.b0.physics import ActionMap
from p6_contacts import ContactMeter
from p6_scene import settings
from p6_single_door import run


class HeldTeacher:
    """Sample one pre-bias target; every intervening servo uses that exact target."""
    def __init__(self, release_during_hold=False):
        self.release_during_hold = release_during_hold
        self.mapping = None
        self.target = None

    def select(self, model, step, candidate, arm, fraction):
        if self.mapping is None:
            self.mapping = ActionMap(model)
        if step % DECIMATION == 0:
            a = self.mapping
            if self.release_during_hold and arm.phase == "hold":
                # A documented negative-control trajectory. The opening request
                # goes through the same finite servo as every other action.
                candidate = candidate.copy()
                candidate[a.actuator_ids[-1]] = arm.cfg["open_width_m"]
            self.request = (candidate[a.actuator_ids] - a.offset) / a.scale
            self.target = candidate.copy()
            self.target[a.actuator_ids] = a.offset + a.scale * np.clip(self.request, -1., 1.)
        # Dense frozen teacher reference for read-only pose and ramp checks.
        self.tcp_goal = arm.position
        self.rotation_goal = arm.rotation
        self.ramp = fraction
        return self.target


def collect(side, goal, split, output, evidence, release_during_hold=False, hold_grasp_pose=False, complete_terminal=False, hold_seconds=3, full_task=False, backend="native"):
    episode_id = f"{side}_{goal}_{split}" + ("_drop" if release_during_hold else "")
    if hold_grasp_pose:
        episode_id += "_grip"
    if complete_terminal:
        episode_id += "_terminal"
    path = output / episode_id
    if evidence.exists():
        raise FileExistsError(evidence)
    path.mkdir(parents=True, exist_ok=False)
    cfg = settings("mobile" if side == "pull" else "push", 1)
    cfg.update(target_angle_deg=goal, grip_hold_s=float(hold_seconds), segment_end_after_retreat_hold=not full_task,
               policy_decimation=DECIMATION, teacher_selection="P6 candidate at substep 10*k")
    if split == "validation":
        # Distinct complete integration. Same scene parameters and reference family,
        # with millimetre-scale offsets to avoid duplicating the training episode.
        cfg["perturbation"] = dict(dx=.002, dy=-.001, yaw=.2)
    if release_during_hold:
        cfg["perturbation"] = (dict(dx=-.001, dy=.001, yaw=.1) if split == "train"
                               else dict(dx=.001, dy=.001, yaw=-.15))
    cfg["release_during_hold"] = release_during_hold
    cfg["hold_grasp_pose"] = hold_grasp_pose
    cfg["complete_terminal"] = complete_terminal
    if complete_terminal:
        # Distinct executions, covering physical terminal successors at exactly 20 ms.
        cfg["perturbation"]["dy"] += .0005
    held = HeldTeacher(release_during_hold)
    recorder = live_data = None
    unexpected_steps = []
    raw = []

    def observe(model, data, t, q, v, target, phase, contact):
        nonlocal recorder, live_data
        live_data = data
        if recorder is None:
            recorder = Recorder(model, cfg, path, episode_id)
            recorder.hold = True
        i = len(recorder.steps["phase"])
        if i % DECIMATION == 0:
            raw.append(held.request.copy())
        recorder.step(model, data, t, q, v, target, phase, contact)
        recorder.steps["door_force_norm_sum_N"].append(contact.force_norm_sum)
        recorder.steps["tcp_goal_world_m"].append(held.tcp_goal.copy())
        recorder.steps["tool_goal_world_R"].append(held.rotation_goal.copy())
        recorder.steps["ramp_fraction"].append(held.ramp)
        if contact.unexpected:
            unexpected_steps.append(dict(step=i, categories=contact.unexpected))

    integrator = None
    if backend == "warp":
        from scripts.b0.check_door_teacher import TeacherPhysics
        integrator = TeacherPhysics()
    passed = run(cfg, path, False, False, False, step_observer=observe, held_teacher=held,
                 integrator=integrator)
    summary = json.loads((path / "summary.json").read_text())
    steps = summary["physics_steps"]
    if integrator is not None and steps != integrator.steps:
        raise RuntimeError("Teacher and Warp step counts disagree")
    failure = summary["failure"]
    extension = 0
    if complete_terminal and failure == "lost_grip":
        # Keep the very same MjData, solver state and already-issued physical
        # command. Score no more task events after the first hard failure.
        model = recorder.m
        meter = ContactMeter(model, "preview_floor", "back" if side == "push" else "front")
        a = held.mapping
        logical_target = held.target[a.actuator_ids] * a.finger_factor
        for _ in range((-steps) % DECIMATION):
            t = float(live_data.time)
            q, v = live_data.qpos.copy(), live_data.qvel.copy()
            live_data.ctrl[a.actuator_ids] = logical_target + live_data.qfrc_bias[a.dof] * a.bias_gain
            if integrator is None:
                mj.mj_step(model, live_data)
            else:
                integrator.step(model, live_data)
            observe(model, live_data, t, q, v, held.target, summary["last_phase"], meter.measure(live_data))
            extension += 1
            if not np.isfinite(live_data.qvel).all() or any(w.number for w in live_data.warning):
                break
    margin = np.asarray(recorder.steps["arm_limit_margin_rad_post"])
    negative = np.flatnonzero((margin < 0).any(axis=1))
    first_failure = steps - 1 if failure else None
    steps += extension
    if len(negative) and (first_failure is None or int(negative[0]) <= first_failure):
        first_failure = int(negative[0])
        failure = "arm_joint_limit"
        passed = False
    np.save(path/"teacher_requested_action.npy", np.asarray(raw), allow_pickle=False)
    dump_json(path/"unexpected_contacts.json", unexpected_steps)
    meta = recorder.finish(passed, failure, dict(
        task=side, wm_split=split, group_id=episode_id, noise_seed=None, actor_raw_action_available=False,
        reference_identity=episode_id, full_task=full_task, target_angle_deg=goal, target_convention="absolute hinge degrees",
        initial_perturbation=cfg["perturbation"], first_failure_physics_interval=first_failure,
        post_failure_completed_physics_steps=extension,
        physics_source="native mj_step" if integrator is None else integrator.source, event_log="summary.json", teacher="P6 candidate sampled at each policy boundary before bias; componentwise clamp in declared ActionMap units",
        requested_action="teacher_requested_action.npy is a normalized pre-clamp teacher request; no neural actor",
        code_parent=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,text=True).strip()))
    bounds = np.array(recorder.states["physics_step"])
    valid = np.array(recorder.states["valid_full_interval"])
    requested = np.asarray(raw)
    actions = np.asarray(recorder.states["action_clipped"])
    if not np.allclose(np.clip(requested, -1, 1), actions, atol=1e-12, rtol=0):
        raise ValueError("Executed control encoding disagrees with teacher request")
    if not np.array_equal(np.array(recorder.steps["qpos"])[bounds], np.array(recorder.states["qpos"])):
        raise ValueError("Policy boundary mismatch")
    np.save(path/"actual_dt.npy", np.diff(bounds) * meta["physics_dt"], allow_pickle=False)
    counts = np.array(recorder.steps["phase"])
    loads = np.array(recorder.steps["finger_load_N"])
    angle = np.rad2deg(np.array(recorder.steps["qpos"])[:-1, -1])
    hold = counts == meta["phases"].index("hold") if "hold" in meta["phases"] else np.zeros(steps, bool)
    events = {row["phase"]: round(row["time_s"]/meta["physics_dt"]) for row in summary["events"]}
    result = dict(episode_id=episode_id, raw_directory=str(path), wm_split=split,
                  initial_perturbation=cfg["perturbation"], backend=f"{backend} MuJoCo {meta['mujoco_version']}",
                  physical_teacher_pass=passed, teacher_hold_seconds=hold_seconds,
                  failure=failure, first_failure_interval=first_failure,
                  post_failure_completed_physics_steps=extension,
                  reference_eligible=bool(passed and split == "train"), policy_success_measured=False,
                  target_deg=goal, final_deg=meta["final_door_deg"], physics_steps=steps,
                  fixed_dt_transitions=int(valid.sum()), partial_terminal_substeps=steps%DECIMATION,
                  both_finger_intervals=int((loads > cfg["contact_threshold_n"]).all(1).sum()),
                  hold_intervals=int(hold.sum()), hold_door_range_deg=[angle[hold].min(),angle[hold].max()] if hold.any() else None,
                  event_end_steps=events, final_phase=summary["last_phase"],
                  channel_names=held.mapping.names, teacher_preclip_min=requested.min(0).tolist(),
                  teacher_preclip_max=requested.max(0).tolist(), channel_clipped_intervals=(abs(requested)>1).sum(0).tolist(),
                  channel_actuator_saturation_substeps=np.array(recorder.steps["actuator_saturation"])[:,held.mapping.actuator_ids].sum(0).tolist(),
                  min_arm_limit_margin_rad=float(margin.min()), unexpected_contacts=unexpected_steps,
                  peak_net_door_force_N=float(np.linalg.norm(recorder.steps["door_robot_force_N"],axis=1).max()))
    evidence.parent.mkdir(parents=True, exist_ok=True)
    dump_json(evidence, result)
    return passed


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("side", choices=["pull","push"])
    parser.add_argument("goal", type=int, choices=[0,5,15,25,60])
    parser.add_argument("split", choices=["train","validation"])
    parser.add_argument("--full-task", action="store_true", help="collect one continuous 60 degree pull or 25 degree push from the original P6 start to final parking")
    parser.add_argument("--complete-terminal", action="store_true", help="continue finite lost-grasp intervals to the real 20 ms successor")
    parser.add_argument("--hold-grasp-pose", action="store_true", help="0 degree task: hold the grasp command after closure, with no reverse opening command")
    parser.add_argument("--hold-seconds", type=int, choices=[3,4], default=3,
                        help="duration of the measured teacher hold; the policy event threshold is separate")
    parser.add_argument("--release-during-hold", action="store_true", help="excite a real loss-of-grasp transition during hold")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--extra-full-hold", action="store_true",
                        help="collect one additional physical second of post-opening grasp for the registered full-task reference")
    parser.add_argument("--backend", choices=["native", "warp"], default="native",
                        help="integrator for every physical substep, including the final partial interval")
    args = parser.parse_args()
    if args.extra_full_hold and not args.full_task:
        parser.error("--extra-full-hold requires --full-task")
    duration = (1.5 if args.extra_full_hold else .5) if args.full_task else args.hold_seconds
    episode_id = f"{args.side}_{args.goal}_{args.split}" + ("_drop" if args.release_during_hold else "")
    if args.hold_grasp_pose:
        if args.goal or args.release_during_hold:
            parser.error("use --hold-grasp-pose only for the 0 degree hold task")
        episode_id += "_grip"
    if args.complete_terminal:
        if not args.release_during_hold:
            parser.error("--complete-terminal requires a lost-grasp experiment")
        episode_id += "_terminal"
    if args.full_task:
        if args.goal != (60 if args.side == 'pull' else 25) or args.release_during_hold or args.hold_grasp_pose or args.complete_terminal:
            parser.error('Full tasks require the original goal and no segment interventions')
    elif args.goal not in (0,5,15):
        parser.error('Use --full-task for the continuous task angles')
    output = args.evidence_dir / (episode_id + ".json")
    return 0 if collect(args.side, args.goal, args.split, args.output, output, args.release_during_hold,
                        args.hold_grasp_pose, args.complete_terminal, duration, args.full_task, args.backend) else 1


if __name__ == "__main__":
    raise SystemExit(main())
