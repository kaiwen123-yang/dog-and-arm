"""Command trials on the original passive-door M1/Piper plant at 500 Hz."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import time

import mujoco as mj
import numpy as np

from learning.multimodal.sensors import RobotSensors
from scripts.multimodal.mm02_physics import build, continuous_initial, scenes, teacher_config
from scripts.multimodal.mm03_adapter import LocalVelocityTeacher
from p6_contacts import ContactMeter


COMMANDS = ("zero", "forward_stop", "reverse_stop", "left_turn_stop", "right_turn_stop",
            "forward_left_stop", "forward_right_stop", "alternating_motion_stop")
ARMS = ("stowed", "pregrasp_hold", "grasp_hold", "complete_pull_or_push_segment")
TRAIN_SCENES = ("tr_nominal", "tr_offset", "tr_load")
DEV_SCENES = ("tr_nominal", "tr_offset", "tr_load", "va_pose", "te_combination")
VELOCITY = ((0, 0), (.65, 0), (-.65, 0), (0, .65), (0, -.65),
            (.55, .55), (.55, -.55), (.60, .45))


def command_at(tick, profile, cfg, gain, stop):
    t = tick*.02
    vx, wz = VELOCITY[COMMANDS.index(profile)]
    if t < 2 or t >= stop or (profile == "alternating_motion_stop" and 8 <= t < 12):
        vx = wz = 0
    elif profile == "alternating_motion_stop" and t >= 12:
        vx, wz = -vx, -wz
    # For every profile the final eight seconds include an uninterrupted stop.
    return np.array([gain*vx*cfg["straight_speed_m_s"], gain*wz*cfg["yaw_rate_rad_s"]])


def make_jobs(stage, seed=None, block=None):
    if stage == "command_teacher":
        design = [(scene, i, arm, 1., 20.) for scene in TRAIN_SCENES for i in range(8) for arm in range(4)]
    elif stage in ("development", "oracle"):
        used = DEV_SCENES[:1] if stage == "oracle" else DEV_SCENES
        design = [(scene, i, (i+k)%4, 1., 20.) for k, scene in enumerate(used) for i in range(8)]
    elif stage == "correction":
        rng = np.random.default_rng(seed + 9007*block)
        # Exactly 32; half explicitly prioritize zero or straight motion-to-stop.
        choices = [0, 0, 1, 2]*4 + list(range(8))*2
        design = [(TRAIN_SCENES[j%3], i, int(rng.integers(4)), float(rng.uniform(.70, 1.1)),
                   float(rng.uniform(16., 22.))) for j, i in enumerate(choices)]
    else:
        raise ValueError(stage)
    jobs = []
    for j, (scene, i, arm, gain, stop) in enumerate(design):
        side = ("pull", "push")[(i+arm)%2]
        jobs.append(dict(id=f"{j:03d}_{scene}_{COMMANDS[i]}_{arm}", scene=scene, side=side,
                         goal=15 if arm < 3 else 25, command=COMMANDS[i], arm=ARMS[arm],
                         gain=gain, stop_s=stop, stage=stage, seed=seed, block=block))
    return jobs


def arm_track(parent, job):
    # All four modes select original physical command sequences; pauses hold
    # a recorded command. There are no synthetic joint excursions.
    src = parent/"data"/f"tr_nominal_{job['side']}_{job['goal']}_held"
    metadata = json.loads((src/"metadata.json").read_text())
    if not (metadata["success"] and metadata["split"] == "train"):
        raise ValueError(f"Expected a successful training-side P6 trajectory in {src}")
    arm = np.load(src/"action_clipped.npy", mmap_mode="r")[:, 16:]
    phases = np.load(src/"phase.npy")
    if job["arm"] == "stowed":
        return arm[:1], src, 0
    begin = int(np.flatnonzero(phases == metadata["phases"].index("pregrasp"))[0])
    if job["arm"] == "complete_pull_or_push_segment":
        end = len(arm)
    else:
        phase = "pregrasp" if job["arm"] == "pregrasp_hold" else "grasp"
        end = int(np.flatnonzero(phases == metadata["phases"].index(phase))[-1]) + 1
    return arm[begin:end], src, begin


def velocity(q, v, rot):
    mj.mju_quat2Mat(rot, q[3:7])
    r = rot.reshape(3, 3)
    return np.array([r[:, 0] @ v[:3], r[2] @ v[3:6]])


def run_command(job, folder):
    scene = scenes()[job["scene"]]
    cfg = teacher_config(job["side"], job["goal"], scene)
    model = build(cfg)
    if mj.__version__ != "3.3.0" or abs(model.opt.timestep-.002) > 1e-12:
        raise RuntimeError("The MM03 command trials require native MuJoCo 3.3.0 / 2 ms")
    data, _, _ = continuous_initial(model, cfg, None)
    scratch = mj.MjData(model)
    local = LocalVelocityTeacher(model, data, cfg)
    sensors = RobotSensors(model, cfg["handle_site"])
    meter = ContactMeter(model, "preview_floor", "back" if job["side"] == "push" else "front",
                         cfg["contact_threshold_n"], cfg["wheel_threshold_n"])
    m = sensors.mapping
    a = defaultdict(list)
    arm, src, arm_start = arm_track(Path(job["arm_parent"]), job)
    rot = np.empty(9)
    limits = model.jnt_range[model.actuator_trnid[m.actuator_ids[16:22], 0]]
    saturation = np.zeros(model.nu, dtype=int)
    max_fault = failure = None
    unloaded = peak_unloaded = steps = support_total = final_stable = 0
    unsupport_counts = np.zeros(4, dtype=np.int64)
    min_force = np.full(4, np.inf)
    stop_xy = None
    max_stop_drift = 0.
    peak_tilt = peak_stop_speed = 0.
    previous = np.zeros(23)
    client = None
    start = time.monotonic()
    try:
        if job["stage"] != "command_teacher":
            from scripts.multimodal.mm03_inference import PolicyClient
            client = PolicyClient(job["checkpoint"], kind="low_oracle" if job["stage"] == "oracle" else "low")
            client.reset("")
        for tick in range(1500):
            now = float(data.time)
            p = sensors.proprio(data.qpos, data.qvel)
            request = command_at(tick, job["command"], cfg, job["gain"], job["stop_s"])
            actual_v = velocity(data.qpos, data.qvel, rot)
            infer_request = np.r_[request, actual_v] if job["stage"] == "oracle" else request
            predicted = (None if client is None else client.step(p, previous, None, now, now,
                                                                  request=infer_request))
            if now+1.e-9 >= job["stop_s"] and stop_xy is None:
                stop_xy = data.qpos[:2].copy()
            for sub in range(10):
                scratch.qpos[:] = data.qpos
                scratch.qvel[:] = data.qvel
                mj.mj_kinematics(model, scratch)
                label = local.update(scratch, request)
                if sub == 0:
                    arm_index = min(tick, len(arm)-1)
                    chosen = label if predicted is None else predicted
                    actual = np.clip(np.r_[chosen, arm[arm_index]], -1., 1.)
                    if not np.isfinite(actual).all():
                        raise FloatingPointError("Nonfinite low control")
                    target = (m.offset + m.scale*actual)*m.finger_factor
                    for name, row in (("proprio", p), ("previous", previous), ("command", request),
                                      ("teacher16", label), ("velocity", actual_v), ("actual", actual),
                                      ("arm_tick", arm_start + arm_index)):
                        a[name].append(np.array(row, copy=True))
                    a["valid"].append(bool(failure is None and np.isfinite(label).all() and (abs(label)<=1.00000001).all()))
                    previous = actual
                v = data.qvel.copy()
                q = data.qpos.copy()
                dctrl = data.qfrc_bias[m.dof]*m.bias_gain
                data.ctrl[m.actuator_ids] = target + dctrl
                mj.mj_step(model, data)
                c = meter.measure(data)
                steps += 1
                loaded = bool(c.supported.all())
                unloaded = 0 if loaded else unloaded+1
                peak_unloaded = max(peak_unloaded, unloaded)
                unsupport_counts += ~c.supported
                min_force = np.minimum(min_force, c.normal)
                support_total += int(loaded)
                mj.mju_quat2Mat(rot, q[3:7])
                r = rot.reshape(3, 3)
                tilt = float(np.rad2deg(max(abs(np.arctan2(r[2, 1], r[2, 2])),
                                           abs(np.arcsin(np.clip(-r[2, 0], -1., 1.))))))
                peak_tilt = max(peak_tilt, tilt)
                saturation = np.where(abs(data.actuator_force) >= cfg["sat_fraction"]*model.actuator_forcerange[:, 1],
                                      saturation+1, 0)
                arm_q = data.qpos[m.q[16:22]]
                reason = None
                if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all() or any(data.warning.number):
                    reason = max_fault = "nonfinite_or_solver_warning"
                elif np.any((arm_q<limits[:, 0]) | (arm_q>limits[:, 1])):
                    reason = "arm_joint_limit"
                elif c.unexpected:
                    reason = "unexpected_contact:" + ",".join(sorted(c.unexpected))
                elif unloaded*.002 >= cfg["unloaded_limit_s"] or tilt >= cfg["tilt_limit_deg"]:
                    reason = "wheel_support_or_tilt"
                elif saturation.max()*.002 >= cfg["sat_limit_s"]:
                    reason = "persistent_saturation"
                if reason and failure is None:
                    failure = dict(reason=reason, step=steps, wheel_n=c.normal.tolist(), tilt_deg=tilt)
                if stop_xy is not None:
                    drift = float(np.linalg.norm(q[:2]-stop_xy))
                    max_stop_drift = max(max_stop_drift, drift)
                    speed = float(np.linalg.norm(v[:2]))
                    if now >= 29:
                        peak_stop_speed = max(peak_stop_speed, speed)
                    stable = loaded and speed < cfg["settle_speed_m_s"] and abs(np.rad2deg(r[2] @ v[3:6])) < cfg["settle_yaw_rate_deg_s"]
                    final_stable = final_stable+1 if stable else 0
                if max_fault:
                    a["valid"][-1] = False
                    break
            if max_fault:
                break
        # Raw teacher labels after the first local stability failure are retained,
        # but excluded from BC membership. These trials still run their 30 s course.
        for key, rows in a.items():
            dtype = bool if key == "valid" else np.int32 if key == "arm_tick" else np.float32
            np.save(folder/(key+".npy"), np.asarray(rows, dtype=dtype), allow_pickle=False)
        cmd, vel = np.asarray(a["command"]), np.asarray(a["velocity"])
        moving = abs(cmd)>1.e-8
        ratios = [float(np.median(vel[moving[:, k], k]/cmd[moving[:, k], k]))
                  if moving[:, k].any() else None for k in range(2)]
        response = all(x is None or x >= .5 for x in ratios)
        stable_end = final_stable*.002+1.e-9 >= cfg["settle_time_s"]
        passed = steps == 15000 and failure is None and stable_end and max_stop_drift <= cfg["position_tol_m"] and response
        return {**job, "success": passed, "first_failure": failure, "physics_steps": steps,
                "local_reference_version": local.version, "arm_provenance": str(src), "arm_start_tick": arm_start,
                "eligible_rows": int(np.sum(a["valid"])), "decisions": len(cmd), "duration_s": steps*.002,
                "all_supported_fraction": support_total/steps, "unsupported_samples": unsupport_counts.tolist(),
                "minimum_wheel_load_n": min_force.tolist(), "max_incomplete_support_s": peak_unloaded*.002,
                "peak_tilt_deg": peak_tilt, "stable_at_end_s": final_stable*.002, "last_second_peak_speed_m_s": peak_stop_speed,
                "max_stop_drift_m": max_stop_drift, "median_motion_velocity_to_request_vx_wz": ratios,
                "tracking_direction_at_least_half_request": response, "estimator_oracle": job["stage"] == "oracle",
                "engineering_only": True, "wall_s": time.monotonic()-start}
    finally:
        sensors.close()
        if client is not None:
            client.close()
