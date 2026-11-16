"""Operator-started H0 movement using the existing verified PiperDevice APIs.

MOVE_J 10%, J6 +2 degrees over 4 s, hold 3 s, return over 4 s, hold 3 s;
gripper 40 -> 15 -> 40 mm at 1 N. No CPV, homing, reset or parameter writes.
Requires an explicit initial target because current unpowered J3 can be outside
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--arm-project", type=Path, default=Path("/home/kaiwen/research/OSCBF-research"))
    p.add_argument("--start-deg", nargs=6, type=float, required=True)
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    # Only this explicit operator entry sends motion. Independent recorders never import it.
    lock = open("/tmp/dog_and_arm_piper_motion.lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    sys.path.insert(0, str(a.arm_project.resolve()))
    from piper_oscbf.device import PiperDevice
    device = PiperDevice()
    gripper = device.robot.init_effector("agx_gripper")
    base = [math.radians(v) for v in a.start_deg]
    target = base.copy()
    target[5] += math.radians(2)
    for q in (base, target):
        for i, value in enumerate(q, 1):
            lo, hi = device.robot.get_config()["joint_limits"][f"joint{i}"]
            if not math.isfinite(value) or not lo <= value <= hi:
                raise ValueError(f"J{i} target out of SDK range; refusing silent clamping")
    a.directory.mkdir(parents=True, exist_ok=True)
    prefix = "motion" if a.execute else "motion_preview"
    events = (a.directory / f"{prefix}_events.jsonl").open("x", buffering=1)
    commands = (a.directory / f"{prefix}_commands.csv").open("x", newline="")
    cw = csv.writer(commands)
    cw.writerow(["host_monotonic_ns", "host_unix_ns", "phase", "command_type", "values", "speed_percent_or_force_N"])
    report = {"error": None, "execute_requested": a.execute, "completed": False,
              "start_deg": a.start_deg, "j6_delta_deg": 2, "ramp_seconds": 4,
              "move_j_speed_percent": 10, "gripper_widths_mm": [40, 15, 40], "gripper_force_N": 1,
              "controller_source": str(a.arm_project / "piper_oscbf/device.py"),
              "normal_end": "MOVE_J holds explicit initial target, arm and gripper remain enabled"}
    started_motion = False

    def mark(name, **data):
        events.write(json.dumps({"event": name, "host_monotonic_ns": time.monotonic_ns(),
                                "host_unix_ns": time.time_ns(), **data}) + "\n")
        print(name, data, flush=True)

    def interrupted(*_):
        raise KeyboardInterrupt("operator stop signal")

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)

    def move(q, phase):
        device.state()  # unchanged existing fresh-feedback/fault checks
        device.robot.move_j(list(q))
        cw.writerow([time.monotonic_ns(), time.time_ns(), phase, "move_j", json.dumps(q), 10])

    def segment(name, q0, q1, seconds):
        device.phase = name
        mark(name + "_start")
        t = time.monotonic()
        while True:
            elapsed = time.monotonic() - t
            alpha = min(elapsed / seconds, 1)
            move([x + alpha * (y - x) for x, y in zip(q0, q1)], name)
            if elapsed >= seconds:
                break
            time.sleep(.02)
        row, status = device.state()
        mark(name + "_end", measured_deg=[math.degrees(x) for x in device.angles(row)], status=status)

    try:
        device.connect()
        row, status = device.state(enabled=False)
        actual = [math.degrees(x) for x in device.angles(row)]
        report["initial_deg"] = actual
        report["initial_status"] = status
        mark("initial_read", actual_deg=actual, explicit_start_deg=a.start_deg,
             initial_adjustment_deg=[b - x for x, b in zip(actual, a.start_deg)])
        if not a.execute:
            print("PREVIEW_ONLY: no command sent. --execute is for the on-site operator.", flush=True)
            return
        # This entry is scoped to small motions; refuse an obsolete start pose.
        if max(abs(b - x) for x, b in zip(actual, a.start_deg)) > 3:
            raise RuntimeError("Explicit start differs >3 degrees from live state; inspect current pose before executing")
        # Camera and receive-only arm logger must be live before any enable/motion.
        for filename in ("camera_live.json", "arm_live.json"):
            path = a.directory / filename
            if not path.exists() or time.time() - path.stat().st_mtime > 5:
                raise RuntimeError(f"Independent recorder is not live: {filename}")
        for j in range(1, 7):
            m = device.robot.get_driver_states(j)
            if m is None or time.time() - m.timestamp > .2:
                raise RuntimeError(f"J{j} driver feedback stale")
            if any(v for k, v in m.msg.foc_status.to_dict().items() if k != "driver_enable_status"):
                raise RuntimeError(f"J{j} driver fault before enable")
        started_motion = True
        mark("enable_explicit_start")
        device.enable_at(base)  # existing validated MOVE_J 10% enable handshake
        segment("initial_hold", base, base, 3)
        segment("j6_slow_out", base, target, 4)
        segment("stop_at_offset", target, target, 3)
        segment("j6_slow_return", target, base, 4)
        segment("stop_at_start", base, base, 3)
        for name, width in (("gripper_open", .04), ("gripper_close", .015), ("gripper_reopen", .04)):
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
        report["completed"] = True
        mark("sequence_complete", final_deg=report["final_deg"])
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
        (a.directory / ("motion_summary.json" if a.execute else "motion_preview.json")).write_text(
            json.dumps(report, indent=2) + "\n")
    if report["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
