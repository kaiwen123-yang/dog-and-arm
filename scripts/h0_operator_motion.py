"""Operator-started H0 movement using the existing verified PiperDevice APIs.

MOVE_J 10%, J6 +2 degrees over 4 s, hold 3 s, return over 4 s, hold 3 s;
gripper 40 -> 15 -> 40 mm at 1 N. No CPV, homing, reset or parameter writes.
Alternatively, --calibration-target-deg positions an already enabled arm once.
Calibration mode has no enable, homing, return or gripper sequence.
The original H0 sequence requires an explicit initial target because current unpowered J3 can be outside
the SDK bounds; silent clamping is rejected. Run without --execute to inspect.
"""
import argparse
import csv
import fcntl
import json
import math
import signal
import sys
import time
from pathlib import Path


# Start with the 2 degree excursion and 0.5 deg/s reference rate used in H0.
CAL_STEP_DEG = 2.
CAL_RATE_DEG_S = .5
CAL_ARRIVAL_DEG = .5


def calibration_driver_issues(device, status, *, require_can=True):
    issues = []
    if require_can and int(status["ctrl_mode"]) != 1:
        issues.append(f"Controller is not in CAN control (ctrl_mode={status['ctrl_mode']})")
    if any(status["err_status"].values()):
        issues.append(f"Controller reports joint errors: {status['err_status']}")
    now = time.time()
    for joint in range(1, 7):
        message = device.robot.get_driver_states(joint)
        if message is None or not 0 <= now - message.timestamp < .2:
            issues.append(f"J{joint} has no fresh driver feedback")
            continue
        flags = message.msg.foc_status.to_dict()
        if not flags["driver_enable_status"]:
            issues.append(f"J{joint} is not already enabled")
        faults = [key for key, value in flags.items() if value and key != "driver_enable_status"]
        if faults:
            issues.append(f"J{joint} driver fault: {faults}")
    return issues


def calibration_position_issues(device, measured, target):
    issues = []
    limits = device.robot.get_config()["joint_limits"]
    for joint, (start, goal) in enumerate(zip(measured, target), 1):
        lo, hi = limits[f"joint{joint}"]
        for label, value in (("measured", start), ("target", goal)):
            if not math.isfinite(value) or not lo <= value <= hi:
                issues.append(f"J{joint} {label} angle outside SDK limits")
        if abs(goal - start) > math.radians(CAL_STEP_DEG) + 1e-10:
            issues.append(f"J{joint} excursion exceeds {CAL_STEP_DEG:g} deg")
    return issues


def near_zero_issues(device, measured, status):
    # This explicit operator request only covers the small excursion near home.
    issues = calibration_driver_issues(device, status, require_can=False)
    ctrl = int(status["ctrl_mode"])
    if ctrl not in (0, 1, 2) or (ctrl == 2 and int(status["teach_status"]) != 2):
        issues.append("Release drag teaching and confirm its lamp is off before handoff")
    if any(not math.isfinite(a) or abs(math.degrees(a)) > 5. for a in measured):
        issues.append("Outside 5 degree near-zero return envelope")
    for j, angle in enumerate(measured, 1):
        lo, hi = device.robot.get_config()["joint_limits"][f"joint{j}"]
        if not lo <= 0. <= hi or max(lo - angle, angle - hi) > math.radians(1.):
            issues.append(f"J{j} outside near-boundary recovery envelope")
    return issues


def handoff_near_zero(device, anchor, status, mark):
    # PiPER H manual 3.1.3(5): stopped teaching -> standby -> CAN.
    # This SDK has no public standby setter. Use the installed firmware
    # profile's typed mode message through its existing sender.
    initial_mode = int(status["ctrl_mode"])
    transitions = {2: (0, 1), 0: (1,), 1: ()}[initial_mode]
    previous_mode = initial_mode
    for mode in transitions:
        device.phase = "handoff_standby" if mode == 0 else "handoff_can"
        mark(device.phase + "_request")
        msg = device.robot._MSG_ModeCtrl(ctrl_mode=mode, move_mode=1, move_spd_rate_ctrl=10)
        device.robot._send_msg(msg)
        sent = time.time()
        stable_since = None
        deadline = time.monotonic() + 2.
        while time.monotonic() < deadline:
            row, status = device.state()
            issues = calibration_driver_issues(device, status, require_can=False)
            if issues:
                raise RuntimeError("; ".join(issues))
            if max(abs(q - start) for q, start in zip(device.angles(row), anchor)) > math.radians(.5):
                raise RuntimeError("Measured arm moved during control-mode handoff")
            current = int(status["ctrl_mode"])
            if current not in (previous_mode, mode):
                raise RuntimeError(f"Unexpected controller mode during handoff: {current}")
            fresh = device.robot.get_arm_status()
            fresh_drives = all(device.robot.get_driver_states(j).timestamp > sent for j in range(1, 7))
            if current == mode and fresh.timestamp > sent and fresh_drives:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= .3:
                    break
            else:
                stable_since = None
            time.sleep(.01)
        else:
            raise RuntimeError(f"No sustained acknowledgement of control mode {mode}")
        mark(device.phase + "_confirmed", status=status, measured_deg=list(map(math.degrees,device.angles(row))))
        previous_mode = mode


def checked_calibration_state(device):
    row, status = device.state()
    issues = calibration_driver_issues(device, status)
    if issues:
        raise RuntimeError("; ".join(issues))
    return row, status


def calibration_arrival(device, target):
    deadline = time.monotonic() + 3.
    stable_since = None
    while time.monotonic() < deadline:
        row, status = checked_calibration_state(device)
        angles = device.angles(row)
        if not all(math.isfinite(angle) for angle in angles):
            raise RuntimeError("Nonfinite measured joint feedback")
        error = max(abs(math.degrees(a - b)) for a, b in zip(angles, target))
        arrived = (int(status["mode_feedback"]) == 1 and int(status["motion_status"]) == 0
                   and error <= CAL_ARRIVAL_DEG)
        if arrived:
            if stable_since is None:
                stable_since = time.monotonic()
                low, high = angles[:], angles[:]
            low = list(map(min, low, angles))
            high = list(map(max, high, angles))
            if max(math.degrees(b - a) for a, b in zip(low, high)) > .1:
                stable_since = None
            elif time.monotonic() - stable_since >= .5:
                return row, status, error
        else:
            stable_since = None
        time.sleep(.02)
    raise RuntimeError("Target arrival and 0.5 s of quiet feedback were not confirmed")


def log_calibration_submissions(comm, writer, device):
    # The SDK can swallow ENOBUFS/ENETDOWN. Record the actual python-can
    # send result in this same sender and surface it to the caller.
    submit = comm.send_bus.send
    sdk_send = comm.send
    submission_error = None

    def logged_submit(msg, *args, **kwargs):
        nonlocal submission_error
        started = time.monotonic_ns()
        try:
            result = submit(msg, *args, **kwargs)
        except Exception as exc:
            submission_error = exc
            writer.writerow([started, time.monotonic_ns(), device.phase, hex(msg.arbitration_id),
                             msg.data.hex(), "error", repr(exc)])
            raise
        writer.writerow([started, time.monotonic_ns(), device.phase, hex(msg.arbitration_id),
                         msg.data.hex(), "host_submitted", ""])
        return result

    def checked_send(msg, *args, **kwargs):
        nonlocal submission_error
        submission_error = None
        result = sdk_send(msg, *args, **kwargs)
        if submission_error is not None:
            raise RuntimeError("CAN frame submission failed") from submission_error
        return result

    comm.send_bus.send = logged_submit
    comm.send = checked_send


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--recording-directory", type=Path,
                   help="Independent recorder directory, when this attempt has its own subdirectory")
    p.add_argument("--arm-project", type=Path, default=Path("/home/kaiwen/research/OSCBF-research"))
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--start-deg", nargs=6, type=float, help="Original H0 J6 and gripper sequence")
    mode.add_argument("--calibration-target-deg", nargs=6, type=float,
                      help="Single absolute joint target; already enabled, stationary CAN control required")
    mode.add_argument("--handoff-near-zero", action="store_true",
                      help="Explicit stopped-teaching handoff and one physical six-axis return near zero")
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    # Only this explicit operator entry sends motion. Independent recorders never import it.
    lock = open("/tmp/dog_and_arm_piper_motion.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    sys.path.insert(0, str(a.arm_project.resolve()))
    from piper_oscbf.device import PiperDevice
    device = PiperDevice()
    # PiperDevice turns this off for its CPV loop. For MOVE_J restore the same
    # mode-before-target sequence as the verified home_zero_simple.py entry.
    device.robot.set_auto_set_motion_mode_enabled(True)
    calibration = a.calibration_target_deg is not None or a.handoff_near_zero
    if calibration:
        target_deg = [0.] * 6 if a.handoff_near_zero else a.calibration_target_deg
        target = list(map(math.radians, target_deg))
        if not all(map(math.isfinite, target)):
            p.error("Calibration target must be finite")
        checked_targets = ()
    else:
        gripper = device.robot.init_effector("agx_gripper")
        base = [math.radians(v) for v in a.start_deg]
        target = base.copy()
        target[5] += math.radians(2)
        checked_targets = (base, target)
    for q in checked_targets:
        for i, value in enumerate(q, 1):
            lo, hi = device.robot.get_config()["joint_limits"][f"joint{i}"]
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"J{i} target out of SDK range; refusing silent clamping")
    a.directory.mkdir(parents=True, exist_ok=True)
    prefix = "motion" if a.execute else "motion_preview"
    if calibration:
        prefix = "calibration_pose" if a.execute else "calibration_preview"
    events = (a.directory / f"{prefix}_events.jsonl").open("x", buffering=1)
    commands = (a.directory / f"{prefix}_commands.csv").open("x", newline="")
    cw = csv.writer(commands)
    cw.writerow(["host_monotonic_ns", "host_unix_ns", "phase", "command_type", "values", "speed_percent_or_force_N"])
    txfile = (a.directory / f"{prefix}_sdk_tx.csv").open("x", newline="")
    txw = csv.writer(txfile)
    if calibration:
        txw.writerow(["host_submit_start_ns", "host_submit_end_ns", "phase", "id", "data_hex", "result", "error"])
    else:
        txw.writerow(["host_monotonic_ns", "host_unix_ns", "phase", "id", "data_hex"])
    report = {"error": None, "execute_requested": a.execute, "command_sequence_completed": False,
              "start_deg": a.start_deg, "j6_delta_deg": 2, "ramp_seconds": 4,
              "move_j_speed_percent": 10, "gripper_widths_mm": [40, 15, 40], "gripper_force_N": 1,
              "controller_source": str(a.arm_project / "piper_oscbf/device.py"),
              "normal_end": "MOVE_J holds explicit initial target, arm and gripper remain enabled"}
    if calibration:
        report = {"mode": "handoff_near_zero" if a.handoff_near_zero else "single_calibration_pose", "error": None, "execute_requested": a.execute,
                  "command_sequence_completed": False, "target_deg": target_deg,
                  "max_joint_step_deg": 5. if a.handoff_near_zero else CAL_STEP_DEG, "reference_rate_deg_s": CAL_RATE_DEG_S,
                  "move_j_speed_percent": 10, "controller_source": str(a.arm_project / "piper_oscbf/device.py")}
    started_motion = False

    def mark(name, **data):
        events.write(json.dumps({"event": name, "host_monotonic_ns": time.monotonic_ns(),
                                "host_unix_ns": time.time_ns(), **data}) + "\n")
        print(name, data, flush=True)

    def interrupted(*_):
        raise KeyboardInterrupt("operator stop signal")

    stop_signals = [signal.SIGINT, signal.SIGTERM]
    if calibration:
        stop_signals.append(signal.SIGHUP)
    for sig in stop_signals:
        signal.signal(sig, interrupted)

    def move(q, phase):
        if calibration:
            row, _ = checked_calibration_state(device)
            measured = device.angles(row)
            if any(not math.isfinite(x) or abs(x - ref) > math.radians(1) for x, ref in zip(measured, q)):
                raise RuntimeError("Measured joint tracking diverged from calibration reference")
        else:
            device.state()
        device.robot.move_j(list(q))
        cw.writerow([time.monotonic_ns(), time.time_ns(), phase, "move_j", json.dumps(q), 10])

    def segment(name, q0, q1, seconds):
        device.phase = name
        mark(name + "_start")
        t = time.monotonic()
        previous = t
        while True:
            now = time.monotonic()
            if calibration and now - previous > .2:
                raise RuntimeError("Calibration command loop interrupted")
            previous = now
            elapsed = now - t
            alpha = min(elapsed / seconds, 1)
            move([x + alpha * (y - x) for x, y in zip(q0, q1)], name)
            if elapsed >= seconds:
                break
            time.sleep(.02)
        row, status = device.state()
        mark(name + "_end", measured_deg=[math.degrees(x) for x in device.angles(row)], status=status)

    try:
        device.connect()
        comm = device.robot.get_context().get_comm()
        send = comm.send
        def recorded_send(msg, *args, **kwargs):
            txw.writerow([time.monotonic_ns(), time.time_ns(), device.phase,
                          hex(msg.arbitration_id), msg.data.hex()])
            return send(msg, *args, **kwargs)
        if calibration:
            log_calibration_submissions(comm, txw, device)
        else:
            comm.send = recorded_send
        row, status = device.state(enabled=False)
        actual = [math.degrees(x) for x in device.angles(row)]
        report["initial_deg"] = actual
        report["initial_status"] = status
        if calibration:
            base = device.angles(row)
            if a.handoff_near_zero:
                issues = near_zero_issues(device, base, status)
            else:
                issues = calibration_driver_issues(device, status) + calibration_position_issues(device, base, target)
            if int(status["motion_status"]) != 0:
                issues.append("Controller reports a move in progress")
            report["readiness_issues"] = issues
            mark("calibration_preview", actual_deg=actual, target_deg=target_deg, issues=issues)
            if issues and a.execute:
                raise RuntimeError("; ".join(issues))
        else:
            mark("initial_read", actual_deg=actual, explicit_start_deg=a.start_deg,
                 initial_adjustment_deg=[b - x for x, b in zip(actual, a.start_deg)])
        if not a.execute:
            print("PREVIEW_ONLY: no command sent. --execute is for the on-site operator.", flush=True)
            return
        # This entry is scoped to small motions; refuse an obsolete start pose.
        if not calibration and max(abs(b - x) for x, b in zip(actual, a.start_deg)) > 3:
            raise RuntimeError("Explicit start differs >3 degrees from live state; inspect current pose before executing")
        # Camera and receive-only arm logger must be live before any enable/motion.
        for filename in ("camera_live.json", "arm_live.json"):
            path = (a.recording_directory or a.directory) / filename
            if not path.exists() or time.time() - path.stat().st_mtime > 5:
                raise RuntimeError(f"Independent recorder is not live: {filename}")
        for j in range(1, 7):
            m = device.robot.get_driver_states(j)
            if m is None or time.time() - m.timestamp > .2:
                raise RuntimeError(f"J{j} driver feedback stale")
            if any(v for k, v in m.msg.foc_status.to_dict().items() if k != "driver_enable_status"):
                raise RuntimeError(f"J{j} driver fault before enable")
        if calibration:
            # Confirm a stationary measured starting point immediately before TX.
            time.sleep(.25)
            if a.handoff_near_zero:
                fresh, status = device.state()
                issues = near_zero_issues(device, device.angles(fresh), status)
                if issues or int(status["motion_status"]) != 0:
                    raise RuntimeError(f"Near-zero handoff not ready: {issues}, {status}")
                if max(abs(x - y) for x, y in zip(device.angles(fresh), base)) > math.radians(.1):
                    raise RuntimeError("Starting position is moving before mode handoff")
                handoff_near_zero(device, base, status, mark)
            fresh, status = checked_calibration_state(device)
            measured = device.angles(fresh)
            if int(status["motion_status"]) != 0 or max(abs(a1 - a0) for a1, a0 in zip(measured, base)) > math.radians(.1):
                raise RuntimeError("Starting joint position is moving")
            issues = (near_zero_issues(device, measured, status) if a.handoff_near_zero
                      else calibration_position_issues(device, measured, target))
            if issues:
                raise RuntimeError("; ".join(issues))
            delta_deg = max(math.degrees(abs(q1 - q0)) for q0, q1 in zip(measured, target))
            device.phase = "calibration_pose"
            # For the explicitly requested near-zero return, a measured joint
            # slightly outside the SDK interval must go directly to its named
            # zero target. Never send an out-of-range reference for SDK clamping.
            reference_start = measured[:]
            if a.handoff_near_zero:
                limits = device.robot.get_config()["joint_limits"]
                for j, angle in enumerate(measured):
                    lo, hi = limits[f"joint{j+1}"]
                    if not lo <= angle <= hi:
                        reference_start[j] = 0.
            mark("calibration_move_start", target_deg=target_deg,
                 first_reference_deg=list(map(math.degrees, reference_start)))
            print("单次定位开始。现场可按 Ctrl+C 请求阻尼急停，必要时使用物理急停。", flush=True)
            started_motion = True
            device.robot.set_speed_percent(10)
            segment("calibration_pose", reference_start, target, max(.1, delta_deg / CAL_RATE_DEG_S))
            row, status, error = calibration_arrival(device, target)
            report.update(command_sequence_completed=True, final_deg=list(map(math.degrees, device.angles(row))),
                          final_status=status, max_final_joint_error_deg=error)
            mark("calibration_arrived", final_deg=report["final_deg"], max_error_deg=error)
            return
        started_motion = True
        mark("enable_explicit_start")
        device.enable_at(base)  # existing validated MOVE_J 10% enable handshake
        segment("initial_hold", base, base, 3)
        segment("j6_slow_out", base, target, 4)
        segment("stop_at_offset", target, target, 3)
        segment("j6_slow_return", target, base, 4)
        segment("stop_at_start", base, base, 3)
        for name, width in (("gripper_open", .04), ("gripper_close", .015), ("gripper_reopen", .04)):
            device.phase = name
            mark(name + "_start", command_width_m=width, force_N=1)
            t = time.monotonic()
            while time.monotonic() - t < 1.5:
                device.state()
                gripper.move_gripper_m(value=width, force=1.)
                cw.writerow([time.monotonic_ns(), time.time_ns(), name, "gripper", width, 1])
                time.sleep(.05)
                m = gripper.get_gripper_status()
                if m is None or time.time() - m.timestamp > .2:
                    raise RuntimeError("Gripper feedback unavailable")
                faults = [k for k, v in m.msg.foc_status.to_dict().items()
                          if v and k not in ("driver_enable_status", "homing_status")]
                if faults:
                    raise RuntimeError(f"Gripper faults: {faults}")
            mark(name + "_end", measured_width_m=m.msg.value, measured_force_N=m.msg.force)
            segment(name + "_hold", base, base, 2)
        row, status = device.state()
        report["final_deg"] = [math.degrees(x) for x in device.angles(row)]
        report["final_status"] = status
        report["command_sequence_completed"] = True
        j6 = [math.degrees(r["q6_rad"]) for r in device.feedback]
        report["observed_j6_range_deg"] = max(j6) - min(j6)
        report["joint_motion_observed"] = report["observed_j6_range_deg"] > 0
        mark("command_sequence_complete", final_deg=report["final_deg"],
             observed_j6_range_deg=report["observed_j6_range_deg"])
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = repr(exc)
        mark("exception", error=report["error"])
        if started_motion:
            try:
                # Same damping emergency-stop API as existing home_zero_simple.py.
                device.robot.electronic_emergency_stop()
                mark("damping_emergency_stop_sent")
                print("已发送阻尼急停，可能下沉；现场确认停止，必要时按物理急停。", flush=True)
            except Exception as stop_exc:
                report["stop_error"] = repr(stop_exc)
                print("软件急停发送失败，请立即使用物理急停。", flush=True)
    finally:
        device.disconnect()
        events.close()
        commands.close()
        txfile.close()
        summary = prefix + "_summary.json" if calibration else ("motion_summary.json" if a.execute else "motion_preview.json")
        (a.directory / summary).write_text(
            json.dumps(report, indent=2) + "\n")
    if report["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
