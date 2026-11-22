#!/usr/bin/env python3
"""Collect B0 teacher references in a private new directory using native MuJoCo."""
from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import sys

import mujoco as mj
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
from learning.b0.physics import ActionMap
from p4_fixed_door import smooth
from p6_base import wheel_geometry, wheel_rates
from p6_contacts import ContactMeter
from p6_scene import build, settings
from p6_single_door import run as run_p6

FREE = ("support", "moving_arm", "park", "moving_arm_wm_validation")
DOORS = ("pull", "push")
PIN = "86ade863de712dd6cd402714229b12b1bdae5b13"
DECIMATION = 10


def dump_json(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def save_arrays(path, arrays):
    path.mkdir(exist_ok=True)
    for name, values in arrays.items():
        np.save(path / (name + ".npy"), np.asarray(values), allow_pickle=False)


class Recorder:
    def __init__(self, model, cfg, path, name):
        self.m, self.cfg, self.path, self.name = model, cfg, path, name
        self.s = mj.MjData(model)  # scratch only for FK at sampled integrated states
        self.states, self.steps = defaultdict(list), defaultdict(list)
        self.hold = name in FREE
        joints = model.actuator_trnid[:, 0]
        mapping = ActionMap(model)
        self.ids = mapping.actuator_ids
        self.legs, self.wheels, self.arm = self.ids[:12], self.ids[12:16], self.ids[16:22]
        self.grip = self.ids[-1]
        self.offset, self.scale = mapping.offset, mapping.scale
        self.q = model.jnt_qposadr[joints]
        self.v = model.jnt_dofadr[joints]
        self.tcp = model.site("p4_grasp").id
        self.handle = model.site(cfg["handle_site"]).id
        self.hinge = model.joint("door_single_hinge").id
        self.finger2 = model.joint("piper_gripper_joint2").qposadr[0]
        self.lo, self.hi = model.jnt_range[joints[self.arm]].T
        self.last_q = self.last_v = None
        self.phase_names = []

    def frame(self, qpos, qvel, time):
        d = self.s
        d.qpos[:] = qpos
        d.qvel[:] = qvel
        mj.mj_kinematics(self.m, d)
        self.states["t"].append(time)
        self.states["qpos"].append(qpos.copy())
        self.states["qvel"].append(qvel.copy())
        self.states["tcp_world"].append(d.site_xpos[self.tcp].copy())
        self.states["handle_world"].append(d.site_xpos[self.handle].copy())
        self.states["hinge_world"].append(d.xanchor[self.hinge].copy())
        self.states["root_angvel_world"].append(d.xmat[self.m.body("m1_base_link").id].reshape(3,3) @ qvel[3:6])
        self.states["root_linvel_world"].append(qvel[:3].copy())
        self.states["opening_m"].append(qpos[self.q[self.grip]] - qpos[self.finger2])
        self.states["finger_residual_m"].append(qpos[self.q[self.grip]] + qpos[self.finger2])

    def step(self, model, d, t, q0, v0, target_xml_order, phase, contacts):
        k = len(self.steps["phase"])
        if k % DECIMATION == 0:
            self.frame(q0, v0, t)
        if phase not in self.phase_names:
            self.phase_names.append(phase)
        self.steps["phase"].append(self.phase_names.index(phase))
        self.steps["qpos"].append(q0.copy())
        self.steps["qvel"].append(v0.copy())
        self.steps["physical_target"].append(target_xml_order[self.ids])
        self.steps["ctrl"].append(d.ctrl.copy())
        self.steps["actuator_force"].append(d.actuator_force.copy())
        self.steps["finger_load_N"].append(contacts.finger_normal)
        self.steps["wheel_load_N"].append(contacts.normal)
        self.steps["wheel_slip_long_m_s"].append(contacts.slip_long)
        self.steps["wheel_slip_lat_m_s"].append(contacts.slip_lat)
        self.steps["door_robot_force_N"].append(contacts.door_force)
        self.steps["unexpected_contact_N"].append(max(contacts.unexpected.values(), default=0.))
        self.steps["arm_limit_margin_rad_post"].append(
            np.minimum(d.qpos[self.q[self.arm]]-self.lo, self.hi-d.qpos[self.q[self.arm]]))
        self.steps["actuator_saturation"].append(np.abs(d.actuator_force) >= .98*model.actuator_forcerange[:,1])
        self.last_q = d.qpos.copy()
        self.last_v = d.qvel.copy()
        self.last_t = float(d.time)

    def finish(self, success, failure, extra):
        m = self.m
        n = len(self.steps["phase"])
        self.frame(self.last_q, self.last_v, self.last_t)
        # Include terminal state exactly, even if the door task ends between 50 Hz ticks.
        self.steps["qpos"].append(self.last_q)
        self.steps["qvel"].append(self.last_v)
        save_arrays(self.path / "substeps", self.steps)
        bounds = np.r_[np.arange(0, n, DECIMATION), n]
        valid = np.diff(bounds) == DECIMATION
        self.states["valid_full_interval"] = valid
        self.states["physics_step"] = bounds
        self.states["policy_step"] = np.arange(len(bounds))
        self.states["terminated"] = np.arange(len(valid)) == len(valid)-1
        self.states["truncated"] = np.zeros(len(valid), bool)
        self.states["phase"] = np.asarray(self.steps["phase"])[bounds[:-1]]
        if self.hold:
            targets = np.asarray(self.steps["physical_target"])
            physical = targets[bounds[:-1]]
            if not np.array_equal(targets, np.repeat(physical, np.diff(bounds), axis=0)):
                raise ValueError("Physical target changed inside a policy interval")
            self.states["physical_target"] = physical
            policy = (physical-self.offset)/self.scale
            if np.abs(policy).max() > 1.000001:
                raise ValueError("Teacher produced an unrepresentable B0 action")
            # This is exact interface encoding of the teacher, independent of an actor.
            self.states["action_clipped"] = np.clip(policy, -1., 1.)
            self.states["last_action"] = np.vstack([np.zeros(m.nu), self.states["action_clipped"]])
        save_arrays(self.path, self.states)
        q, v = np.asarray(self.states["qpos"]), np.asarray(self.states["qvel"])
        hinge = m.joint(self.hinge)
        jnames = [m.joint(i).name for i in range(m.njnt)]
        rollout = dict(finished=True, success=bool(success), failure=failure,
                       episode_id=self.name, source="teacher", mount="rail_bridge_front60_v2",
                       action_schema="legs_rad12,wheel_rad_s4,arm_rad6,jaw_width_m1",
                       logical_actuator_ids=self.ids.tolist(), action_offset=self.offset.tolist(),
                       action_scale=self.scale.tolist(), actuator_names_xml=[m.actuator(i).name for i in range(m.nu)],
                       joint_names=jnames, qposadr=m.jnt_qposadr.tolist(), dofadr=m.jnt_dofadr.tolist(),
                       physics_dt=float(m.opt.timestep), policy_dt=DECIMATION*float(m.opt.timestep),
                       reference_fps=50, fk_tcp="p4_grasp", handle_site=self.cfg["handle_site"],
                       initial_qpos=q[0].tolist(), initial_qvel=v[0].tolist(), quaternion="wxyz",
                       root_velocity="qvel[:3] world linear, qvel[3:6] body angular; explicit world vectors provided",
                       position_unit="hinges rad, slide or translation m",
                       force_units="hinge N m, prismatic N, XML order",
                       condition="C01", scene_seed=None, training_seed=None, phases=self.phase_names,
                       duration_s=self.last_t, physics_steps=n, full_intervals=int(valid.sum()),
                       final_partial_substeps=n%DECIMATION, held_action_replay=self.hold,
                       substep_schema="qpos,qvel length N+1; all remaining arrays length N. index k describes [k,k+1].",
                       numpy_version=np.__version__, mujoco_version=mj.__version__, teacher_pin=PIN,
                       final_door_deg=float(np.rad2deg(q[-1,hinge.qposadr[0]])),
                       max_abs_door_deg=float(np.max(np.abs(np.rad2deg(q[:,hinge.qposadr[0]])))),
                       final_speed_m_s=float(np.linalg.norm(v[-1,:2])),
                       max_speed_m_s=float(np.linalg.norm(v[:,:2],axis=1).max()),
                       root_displacement_xy_m=(q[-1,:2]-q[0,:2]).tolist(),
                       peak_arm_excursion_deg=np.rad2deg(np.abs(q[:,self.q[self.arm]]-q[0,self.q[self.arm]]).max(0)).tolist(),
                       min_arm_margin_rad=float(np.min(self.steps["arm_limit_margin_rad_post"])),
                       unexpected_contact_peak_N=float(np.max(self.steps["unexpected_contact_N"])),
                       **extra)
        dump_json(self.path / "metadata.json", rollout)
        return rollout


def free_episode(path, name):
    cfg = settings("mobile", 1)
    model = build(cfg)
    d = mj.MjData(model)
    mj.mj_resetDataKeyframe(model, d, model.key("home").id)
    mj.mj_forward(model, d)
    r = Recorder(model, cfg, path, name)
    meter = ContactMeter(model, "preview_floor")
    p5 = yaml.safe_load((ROOT / "config/p5.yaml").read_text())
    sign, lateral = wheel_geometry(d, model.body("m1_base_link").id, model.actuator_trnid[r.wheels,0])
    home = d.qpos[r.q].copy()
    ids = np.r_[r.legs, r.arm, r.grip]
    val = name.endswith("validation")
    kind = "moving_arm" if val else name
    duration = {"support":7., "moving_arm":7., "park":7.}[kind]
    dt = model.opt.timestep
    rng = np.random.default_rng(13097) if val else None
    for k in range(round(duration/(DECIMATION*dt))):
        t = k*DECIMATION*dt
        if kind == "park":
            speed_frac = smooth((t-.45)/.9)*(1.-smooth((t-2.6)/1.5))
            arm_frac = smooth((t-.2)/1.2)*(1.-smooth((t-2.7)/1.7))
            phase = "roll" if t < 2.6 else "brake_retract" if t < 4.4 else "park"
        else:
            speed_frac = 0. if kind == "support" else smooth((t-1.)/.9)*(1.-smooth((t-5.)/.9))
            arm_frac = smooth((t-.8)/2.2)*(1.-smooth((t-3.6)/2.2))
            phase = "settle" if t < .8 else "extend" if t < 3.6 else "return" if t < 5.8 else "park"
        target = home.copy()
        target[r.arm] += np.deg2rad(p5["arm_excursion_deg"])*arm_frac
        target[r.wheels] = wheel_rates(sign, lateral, p5["rolling_radius_m"], p5["straight_speed_m_s"]*speed_frac, 0.)
        target[r.grip] = 2.*home[r.grip] + .02*arm_frac
        if val:
            # Independent episode and excitation, excluded from the reference library.
            # Filtered by holding each perturbation for 0.2 s (10 policy ticks).
            if k%10 == 0:
                noise = rng.uniform(-1., 1., model.nu)
            target[r.legs] += .004*noise[r.legs]
            target[r.arm] += .012*noise[r.arm]
            target[r.wheels] += .035*noise[r.wheels]
            target[r.grip] += .001*noise[r.grip]
        for substep in range(DECIMATION):
            q0, v0 = d.qpos.copy(), d.qvel.copy()
            t0 = float(d.time)
            d.ctrl[:] = target
            d.ctrl[r.grip] = .5*target[r.grip]
            d.ctrl[ids] += d.qfrc_bias[r.v[ids]] / model.actuator_gainprm[ids,0]
            mj.mj_step(model, d)
            c = meter.measure(d)
            r.step(model, d, t0, q0, v0, target, phase, c)
            if np.any(~np.isfinite(d.qpos)) or any(w.number for w in d.warning):
                raise RuntimeError(f"{name} solver failure at {d.time}")
    unexpected = float(np.max(r.steps["unexpected_contact_N"]))
    motion = abs(d.qpos[0]-r.states["qpos"][0][0])
    speed = np.linalg.norm(d.qvel[:2])
    no_door = not np.any(r.steps["door_robot_force_N"])
    travel_ok = motion < .01 if kind == "support" else motion > .10
    passed = unexpected == 0 and no_door and travel_ok and (speed < .005 or val) and np.min(r.steps["arm_limit_margin_rad_post"]) >= 0.
    cfg["arm_excursion_deg"] = p5["arm_excursion_deg"]
    dump_json(path / "config.json", cfg)
    return r.finish(passed, None if passed else "free_motion_physical_check",
                    dict(task=kind, wm_split="validation" if val else "train", noise_seed=13097 if val else None,
                         teacher="P5 speed allocation, smooth ramp and joint excursion in P6 scene; simultaneous schedules and opening +20 mm are B0 adaptations",
                         target_angle_deg=None, door_robot_contact=not no_door, final_substep_wheel_load_N=r.steps["wheel_load_N"][-1].tolist()))


def door_episode(path, name):
    cfg = settings("mobile" if name == "pull" else "push", 1)
    recorder = None
    def observe(model, data, t, q, v, target, phase, contacts):
        nonlocal recorder
        if recorder is None:
            recorder = Recorder(model, cfg, path, name)
        recorder.step(model, data, t, q, v, target, phase, contacts)
    passed = run_p6(cfg, path, False, False, False, step_observer=observe)
    summary = json.loads((path / "summary.json").read_text())
    return recorder.finish(passed, summary["failure"], dict(task=name, wm_split="reference_only",
                           noise_seed=None, teacher="frozen P6 mobile/push C01", target_angle_deg=cfg["target_angle_deg"],
                           event_log="summary.json", final_substep_wheel_load_N=recorder.steps["wheel_load_N"][-1].tolist()))


def index_collection(output, index_dir):
    """Verify collected episode boundaries and read back the named actuator path."""
    from learning.b0.physics import NativePlant
    from learning.b0.reference import load_episode

    index_dir.mkdir(exist_ok=True, parents=True)
    entries, references, audit = [], [], {}
    for name in FREE + DOORS:
        path = output / name
        meta = json.loads((path/"metadata.json").read_text())
        d = load_episode(path)
        q, v, b = d["qpos"], d["qvel"], d["physics_step"]
        subq = np.load(path/"substeps/qpos.npy", mmap_mode="r")
        subv = np.load(path/"substeps/qvel.npy", mmap_mode="r")
        if not np.array_equal(q, subq[b]) or not np.array_equal(v, subv[b]):
            raise ValueError(f"{name} transition mismatched its source physics step")
        if not d["terminated"][-1] or d["terminated"][:-1].any() or d["truncated"].any():
            raise ValueError(f"{name} terminal boundary")
        if not np.array_equal(np.rint(np.diff(d["t"])/meta["physics_dt"]), np.diff(b)):
            raise ValueError(f"{name} step/time mismatch")
        run_id = output.resolve().name
        episode_id = run_id + "/" + name
        try:
            relative_path = str(path.resolve().relative_to(ROOT))
        except ValueError:
            relative_path = str(path.resolve())
        entry = dict(episode_id=episode_id, reference_id=name, path=relative_path,
                     task=meta["task"], source="teacher", wm_split=meta["wm_split"],
                     mount=meta["mount"], teacher_pin=PIN, initial_condition="C01",
                     success=meta["success"], failure=meta["failure"], reference_fps=50, physics_dt=.002,
                     duration_s=meta["duration_s"], full_intervals=meta["full_intervals"],
                     final_partial_substeps=meta["final_partial_substeps"],
                     held_action_replay=meta["held_action_replay"], noise_seed=meta["noise_seed"],
                     accepted_reference=meta["success"] and name != "moving_arm_wm_validation",
                     target_angle_deg=meta["target_angle_deg"])
        entries.append(entry)
        if entry["accepted_reference"]:
            references.append(entry)
        checks = dict(policy_state_equals_substep_boundary=True, terminal_frames=1,
                      initial_time_s=float(d["t"][0]), terminal_time_s=float(d["t"][-1]),
                      root_displacement_xy_m=meta["root_displacement_xy_m"],
                      peak_speed_m_s=meta["max_speed_m_s"], terminal_speed_m_s=meta["final_speed_m_s"],
                      peak_arm_excursion_deg=meta["peak_arm_excursion_deg"],
                      worst_arm_limit_margin_rad=meta["min_arm_margin_rad"],
                      peak_unexpected_contact_N=meta["unexpected_contact_peak_N"],
                      final_door_deg=meta["final_door_deg"])
        if name in FREE:
            plant = NativePlant(build(settings("mobile", 1)))
            mapping = plant.mapping
            if not (np.array_equal(mapping.actuator_ids, meta["logical_actuator_ids"]) and
                    np.array_equal(mapping.scale, meta["action_scale"]) and
                    np.array_equal(mapping.offset, meta["action_offset"])):
                raise ValueError(f"{name} real training actuator mapping mismatch")
            plant.reset(q[0], v[0])
            max_qerr, max_verr = 0., 0.
            for k, action in enumerate(d["action_clipped"]):
                result = plant.step(action)
                if result["failure_reason"]:
                    raise ValueError(f"{name} actual target revisit failed at {k}: {result}")
                max_qerr = max(max_qerr, float(np.abs(plant.data.qpos - q[k+1]).max()))
                max_verr = max(max_verr, float(np.abs(plant.data.qvel - v[k+1]).max()))
            if max_qerr > 1e-7 or max_verr > 1e-6:
                raise ValueError(f"{name} action replay diverged: {max_qerr} / {max_verr}")
            checks.update(native_action_replay_steps=len(d["action_clipped"]),
                          max_qpos_error_mixed_units=max_qerr, max_qvel_error_mixed_units=max_verr,
                          opening_range_m=[float(d["opening_m"].min()), float(d["opening_m"].max())])
        else:
            summary = json.loads((path/"summary.json").read_text())
            checks["events"] = [{key: event[key] for key in ("phase","time_s","door_deg","continuous_s")}
                                for event in summary["events"]]
            checks["p6_task_success"] = summary["task_success"]
            checks["p6_solver_warning_counts"] = summary["warnings"]
        audit[name] = checks
    dump_json(index_dir/"reference_manifest.json", dict(schema=1, storage="NumPy .npy per field",
              reference_fps=50, pose_quaternion="wxyz", root_linvel="world m/s", root_angvel_world="world rad/s",
              joint_names=meta["joint_names"], qposadr=meta["qposadr"], dofadr=meta["dofadr"],
              reference_selection="support/moving_arm/park for B0-03; native pull/push for B0-04",
              references=references))
    (index_dir/"episode_index.jsonl").write_text("".join(json.dumps(row,ensure_ascii=False)+"\n" for row in entries))
    dump_json(index_dir/"native_teacher_checks.json", audit)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("tasks", nargs="*", metavar="TASK")
    parser.add_argument("--output", type=Path, default=None, help="new episode directories under this run root")
    parser.add_argument("--index-dir", type=Path,
                        help="verify six episodes at --output with NativePlant, write lightweight manifests here")
    args = parser.parse_args()
    if set(args.tasks) - set(FREE+DOORS):
        parser.error(f"tasks must be from {FREE+DOORS}")
    if not args.tasks and not (args.index_dir and args.output):
        parser.error("provide tasks to collect or --output and --index-dir for an existing collection")
    output = args.output or ROOT/"results/raw_large/b0"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output.mkdir(parents=True, exist_ok=True)
    success = True
    for name in args.tasks:
        path = output / name
        path.mkdir(exist_ok=False)
        result = free_episode(path, name) if name in FREE else door_episode(path, name)
        print(f"{name} success={result['success']} sim_s={result['duration_s']:.3f} -> {path}", flush=True)
        success = success and result["success"]
    if args.index_dir:
        index_collection(output, args.index_dir)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
