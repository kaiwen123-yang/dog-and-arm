"""Receive-only Piper H logger, using the already installed pyAgxArm V189 SDK.

Joint rows are completed three-frame receive groups, not cache poll frequency.
SDK snapshots are explicitly polls with each feedback's own timestamp.
An independent SocketCAN receiver preserves raw/error frames. No send API used.
"""
import argparse
import csv
import json
import math
import signal
import subprocess
import threading
import time
from pathlib import Path
from importlib.metadata import version

import can
from pyAgxArm import AgxArmFactory, ArmModel, PiperFW, create_agx_arm_config


def stats(channel):
    base = Path("/sys/class/net") / channel / "statistics"
    return {k: int((base / k).read_text()) for k in
            ("rx_packets", "rx_errors", "rx_dropped", "tx_packets", "tx_errors", "tx_dropped")}


def message(m):
    if m is None:
        return None
    return {"sdk_timestamp_s": m.timestamp,
            "data": m.msg.to_dict() if hasattr(m.msg, "to_dict") else list(m.msg)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--raw-directory", type=Path, required=True)
    p.add_argument("--seconds", type=float, default=0, help="0: record until Ctrl+C/SIGTERM")
    p.add_argument("--channel", default="can0")
    p.add_argument("--usb-serial", default="004F00374548570120353731")
    a = p.parse_args()
    props = subprocess.check_output(["udevadm", "info", "--query=property",
                                    f"--path=/sys/class/net/{a.channel}"], text=True)
    if f"ID_SERIAL_SHORT={a.usb_serial}" not in props.splitlines():
        raise RuntimeError("USB-CAN identity mismatch")
    link = json.loads(subprocess.check_output(
        ["ip", "-j", "-details", "link", "show", a.channel], text=True))[0]
    if "UP" not in link["flags"] or link["linkinfo"]["info_data"]["bittiming"]["bitrate"] != 1000000:
        raise RuntimeError("Known Piper CAN must already be UP at 1 Mbps; recorder will not configure it")
    a.directory.mkdir(parents=True, exist_ok=True)
    a.raw_directory.mkdir(parents=True, exist_ok=True)
    for path in (a.directory / "joints.csv", a.directory / "arm_summary.json", a.raw_directory / "raw_can.csv"):
        if path.exists():
            raise FileExistsError(f"Use a new run directory; preserving existing evidence: {path}")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    robot = AgxArmFactory.create_arm(create_agx_arm_config(
        robot=ArmModel.PIPER_H, firmeware_version=PiperFW.V189,
        interface="socketcan", channel=a.channel, bitrate=1000000,
        auto_connect=False, enable_check_can=True, timeout=.05))
    gripper = robot.init_effector("agx_gripper")
    report = {"pyAgxArm": version("pyAgxArm"), "firmware_profile": "V189",
              "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
              "started_unix_ns": time.time_ns(), "started_monotonic_ns": time.monotonic_ns(),
              "recorder_sends_commands": False, "error": None,
              "joint_rows": 0, "gripper_rows": 0, "raw_frames": 0, "can_error_frames": 0,
              "snapshot_kind": "cached_poll_10hz_with_sdk_timestamps",
              "interface_before": stats(a.channel)}
    raw_bus = can.Bus(interface="socketcan", channel=a.channel, receive_own_messages=False,
                      ignore_config=True)

    def raw_loop():
        try:
            with (a.raw_directory / "raw_can.csv").open("x", newline="") as f, \
                    (a.directory / "can_errors.csv").open("x", newline="") as e:
                w, ew = csv.writer(f), csv.writer(e)
                fields = ["can_timestamp_s", "host_monotonic_ns", "host_unix_ns", "id",
                          "is_rx", "is_error", "is_remote", "data_hex"]
                w.writerow(fields)
                ew.writerow(fields)
                while not stop.is_set():
                    frame = raw_bus.recv(.05)
                    if frame is None:
                        continue
                    row = [frame.timestamp, time.monotonic_ns(), time.time_ns(), hex(frame.arbitration_id),
                           int(frame.is_rx), int(frame.is_error_frame), int(frame.is_remote_frame), frame.data.hex()]
                    w.writerow(row)
                    report["raw_frames"] += 1
                    if frame.is_error_frame:
                        ew.writerow(row)
                        report["can_error_frames"] += 1
        except Exception as exc:
            report["raw_error"] = repr(exc)
            stop.set()

    raw_thread = threading.Thread(target=raw_loop, name="h0-passive-raw-can")
    try:
        robot.connect(start_read_thread=False)
        raw_thread.start()
        comm = robot.get_context().get_comm()
        pending = {}
        started = next_poll = next_flush = time.monotonic()
        with (a.directory / "joints.csv").open("x", newline="") as j, \
                (a.directory / "gripper.csv").open("x", newline="") as g, \
                (a.directory / "arm_snapshots.jsonl").open("x") as s:
            jw, gw = csv.writer(j), csv.writer(g)
            jw.writerow(["host_monotonic_ns", "host_unix_ns", "can_first_s", "can_last_s", "sdk_timestamp_s"] +
                        [f"q{i}_rad" for i in range(1, 7)])
            gw.writerow(["host_monotonic_ns", "host_unix_ns", "can_timestamp_s", "width_m", "force_N", "status_code", "mode"])
            print("ARM_RECEIVE_ONLY_STARTED", a.directory, flush=True)
            while not stop.is_set() and (a.seconds == 0 or time.monotonic() - started < a.seconds):
                frame = comm.recv()  # same SDK decoding path as existing read_joint_state.py
                mono, unix = time.monotonic_ns(), time.time_ns()
                if frame is not None and frame.is_rx and not frame.is_remote_frame and len(frame.data) == 8:
                    if frame.arbitration_id in (0x2A5, 0x2A6, 0x2A7):
                        pending[frame.arbitration_id] = frame.timestamp
                        if len(pending) == 3:
                            first, last = min(pending.values()), max(pending.values())
                            pending.clear()
                            m = robot.get_joint_angles()
                            q = list(m.msg) if m else []
                            if len(q) == 6 and all(math.isfinite(x) for x in q):
                                jw.writerow([mono, unix, first, last, m.timestamp, *q])
                                report["joint_rows"] += 1
                                report["last_joint_deg"] = [math.degrees(x) for x in q]
                    elif frame.arbitration_id == 0x2A8:
                        data = frame.data
                        # Width feedback in micrometres, force in millinewtons (SDK protocol).
                        gw.writerow([mono, unix, frame.timestamp,
                                     int.from_bytes(data[:4], "big", signed=True) * 1e-6,
                                     int.from_bytes(data[4:6], "big", signed=True) * 1e-3, data[6], data[7]])
                        report["gripper_rows"] += 1
                now = time.monotonic()
                if now >= next_poll:
                    snap = {"kind": "cached_poll", "host_monotonic_ns": mono, "host_unix_ns": unix,
                            "joint": message(robot.get_joint_angles()), "arm": message(robot.get_arm_status()),
                            "drivers": [message(robot.get_driver_states(i)) for i in range(1, 7)],
                            "gripper": message(gripper.get_gripper_status())}
                    s.write(json.dumps(snap) + "\n")
                    report["last_snapshot"] = snap
                    next_poll = now + .1
                if now >= next_flush:
                    for f in (j, g, s):
                        f.flush()
                    (a.directory / "arm_live.json").write_text(json.dumps(report, indent=2) + "\n")
                    next_flush = now + 2
    except Exception as exc:
        report["error"] = repr(exc)
        raise
    finally:
        stop.set()
        if raw_thread.ident is not None:
            raw_thread.join()
        raw_bus.shutdown()
        robot.disconnect()
        report["ended_monotonic_ns"] = time.monotonic_ns()
        report["interface_after"] = stats(a.channel)
        report["interface_delta"] = {k: report["interface_after"][k] - v for k, v in report["interface_before"].items()}
        (a.directory / "arm_summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({k: v for k, v in report.items() if k != "last_snapshot"}), flush=True)


if __name__ == "__main__":
    main()
