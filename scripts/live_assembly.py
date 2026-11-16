#!/usr/bin/env python3
"""Desktop-only, explicitly kinematic assembly preview for MuJoCo 3.3.0.

From the repository root:
    .venv/bin/python scripts/live_assembly.py
    .venv/bin/python scripts/live_assembly.py --watch
    .venv/bin/python scripts/live_assembly.py --scripted-demo

Only mj_forward is called. Neither this viewer nor its event log establishes
dynamic stability, contact-task success, or that a person actually saw a frame.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import queue
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MODE = "KINEMATIC_PREVIEW"
GRIPPER_JOINTS = ("piper_gripper_joint1", "piper_gripper_joint2")


def arguments():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path,
                        default=ROOT / "sim/scenes/assembly_preview.xml")
    parser.add_argument("--events", type=Path,
                        default=ROOT / "results/assembly/live_events.jsonl")
    parser.add_argument("--watch", action="store_true",
                        help="watch the model and recursively referenced XML files")
    parser.add_argument("--scripted-demo", action="store_true",
                        help="explicitly enable a slow, kinematic arm/gripper animation")
    parser.add_argument("--step-deg", type=float, default=2.0,
                        help="hinge-joint increment in degrees (default: 2)")
    parser.add_argument("--step-m", type=float, default=0.002,
                        help="slide-joint increment in metres (default: 0.002)")
    parser.add_argument("--collision-group", type=int, choices=range(6), default=3,
                        help="geom group containing collision geometry (default: 3)")
    args = parser.parse_args()
    if not all(math.isfinite(x) and x > 0 for x in (args.step_deg, args.step_m)):
        parser.error("joint increments must be positive and finite")
    args.model = args.model.expanduser().resolve()
    args.events = args.events.expanduser().resolve()
    return args


def xml_snapshot(model_path):
    """Track XML metadata, including missing files; no hashes or mesh scan."""
    pending, seen, snapshot = [model_path], set(), {}
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        seen.add(path)
        try:
            stat = path.stat()
            snapshot[str(path)] = (stat.st_mtime_ns, stat.st_size)
            root = ET.parse(path).getroot()
        except FileNotFoundError:
            snapshot[str(path)] = None
            continue
        except ET.ParseError:
            # An editor can momentarily leave incomplete XML while saving.
            continue
        for element in root.iter():
            reference = element.get("file", "")
            if element.tag == "include" or reference.lower().endswith(".xml"):
                if reference:
                    pending.append(path.parent / reference)
    return snapshot


def load_model(mj, path):
    # MjSpec preserves file-relative asset paths. Renaming in memory makes the
    # native window title explicit without modifying any source XML.
    spec = mj.MjSpec.from_file(str(path))
    spec.modelname = f"{MODE} | {path.name}"
    model = spec.compile()
    data = mj.MjData(model)
    home = mj.mj_name2id(model, mj.mjtObj.mjOBJ_KEY, "home")
    if home < 0:
        raise ValueError("模型缺少名为 home 的 keyframe；请先生成完整 assembly_preview.xml。")
    mj.mj_resetDataKeyframe(model, data, home)
    mj.mj_forward(model, data)
    joints = []
    for joint in range(model.njnt):
        name = mj.mj_id2name(model, mj.mjtObj.mjOBJ_JOINT, joint) or ""
        scalar = model.jnt_type[joint] in (
            mj.mjtJoint.mjJNT_HINGE, mj.mjtJoint.mjJNT_SLIDE)
        if scalar and name.startswith(("m1_", "piper_")) and name not in GRIPPER_JOINTS:
            joints.append((name, joint))
    # Keep the arm first; retain the model's order within arm/base groups.
    joints.sort(key=lambda item: not item[0].startswith("piper_"))
    return model, data, home, joints


def gripper_limits(mj, model):
    ids = [mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, name) for name in GRIPPER_JOINTS]
    if any(joint < 0 for joint in ids):
        return None
    if any(model.jnt_type[joint] != mj.mjtJoint.mjJNT_SLIDE for joint in ids):
        raise ValueError("两个 piper_gripper_joint 必须是 slide joint。")
    # Official parallel fingers use q1 = width/2 and q2 = -width/2.
    low, high = 0.0, 0.1
    for joint, sign in zip(ids, (1.0, -1.0)):
        if model.jnt_limited[joint]:
            bounds = sorted(sign * 2.0 * float(v) for v in model.jnt_range[joint])
            low, high = max(low, bounds[0]), min(high, bounds[1])
    if high <= low:
        raise ValueError("夹爪 joint1/joint2 的限位与 q1=+w/2、q2=-w/2 不一致。")
    return [int(model.jnt_qposadr[joint]) for joint in ids], low, high


def set_width(data, gripper, width):
    addresses, low, high = gripper
    width = min(high, max(low, width))
    data.qpos[addresses[0]], data.qpos[addresses[1]] = width / 2.0, -width / 2.0
    return float(width)


def clamp_joint(model, joint, value):
    if model.jnt_limited[joint]:
        low, high = model.jnt_range[joint]
        return float(min(high, max(low, value)))
    return float(value)


def close_viewer(viewer):
    # In 3.3.0 close() waits for the render loop; m becomes None when the
    # viewer thread has also released its window/Simulate wrapper. Wait for
    # that cleanup before launching a replacement, so windows never overlap.
    viewer.close()
    while viewer.m is not None:
        time.sleep(0.01)


def run(args, mj, viewer_api, glfw, record):
    actions = {
        glfw.KEY_LEFT: "previous_joint", glfw.KEY_RIGHT: "next_joint",
        glfw.KEY_DOWN: "decrease_joint", glfw.KEY_UP: "increase_joint",
        glfw.KEY_SPACE: "toggle_gripper", glfw.KEY_F8: "toggle_camera",
        glfw.KEY_F9: "toggle_collision_group", glfw.KEY_F10: "reload",
        glfw.KEY_F11: "reset_home", glfw.KEY_F12: "quit",
    }
    print(f"\n{MODE}: 只做运动学预览，物理时间不推进，不运行实机。", flush=True)
    print("窗口获得焦点后：\n"
          "  ←/→ 选择单关节；↓/↑ 小步调整；Space 夹爪开/闭\n"
          "  F8 腕相机/自由视角；F9 碰撞组显隐；F10 重新加载 XML\n"
          "  F11 恢复 home；F12 退出；Esc 为 MuJoCo 原生自由视角\n"
          "  鼠标拖动/滚轮按 MuJoCo 原生方式旋转、平移、缩放。\n"
          "  修改配置后需先重新生成 XML；--watch 只跟踪 XML。\n"
          "  手动调整关节、夹爪或 home 会停止 scripted demo。", flush=True)
    print(f"事件日志：{args.events}\n日志只证明本程序收到/执行了事件，不证明用户已看到画面。", flush=True)

    loaded = load_model(mj, args.model)
    demo = args.scripted_demo
    next_load_event = "load"
    selected_name = None
    collisions_visible = False
    use_wrist_camera = False
    free_camera = None
    keys = queue.SimpleQueue()

    while True:
        model, data, home, joints = loaded
        gripper = gripper_limits(mj, model)
        camera_id = mj.mj_name2id(model, mj.mjtObj.mjOBJ_CAMERA, "wrist_rgbd")
        selected = next((i for i, item in enumerate(joints) if item[0] == selected_name), 0)
        home_qpos = data.qpos.copy()
        demo_joints = [(name, joint) for name, joint in joints
                       if name.startswith("piper_") and
                       model.jnt_type[joint] == mj.mjtJoint.mjJNT_HINGE][:2]
        demo_start, last_demo_cycle = 0.0, -1
        demo_width = float(data.qpos[gripper[0][0]] - data.qpos[gripper[0][1]]) if gripper else 0.0
        candidate = None
        while not keys.empty():
            keys.get_nowait()

        # Callback runs on the renderer thread: only enqueue, never change data
        # or call close() while that thread holds a MuJoCo viewer lock.
        def key_callback(key):
            keys.put((key, time.monotonic_ns()))

        viewer = viewer_api.launch_passive(model, data, key_callback=key_callback,
                                           show_left_ui=False, show_right_ui=False)
        try:
            with viewer.lock():
                viewer.opt.geomgroup[args.collision_group] = int(collisions_visible)
                if free_camera:
                    viewer.cam.lookat[:] = free_camera[0]
                    viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = free_camera[1:]
                if use_wrist_camera and camera_id >= 0:
                    viewer.cam.type = mj.mjtCamera.mjCAMERA_FIXED
                    viewer.cam.fixedcamid = camera_id
                else:
                    use_wrist_camera = False
                    viewer.cam.type = mj.mjtCamera.mjCAMERA_FREE
            viewer.sync()
            record(next_load_event, model=str(args.model), mujoco_version=mj.__version__, home="home", nq=model.nq,
                   joints=[name for name, _ in joints], camera_available=camera_id >= 0,
                   collision_group=args.collision_group,
                   collision_geom_count=int(sum(model.geom_group == args.collision_group)),
                   scripted_demo=demo, user_visibility="not_observed_by_script")
            print(f"已{ '重载' if next_load_event == 'reload' else '打开' }预览窗口：{args.model.name}", flush=True)
            if joints:
                selected_name = joints[selected][0]
                print(f"当前关节：{selected_name}", flush=True)
            if gripper is None:
                print("当前模型没有完整的 Piper 双指关节；Space 不执行夹爪动作。", flush=True)
            if camera_id < 0:
                print("当前模型没有 wrist_rgbd camera；F8 将保留自由视角。", flush=True)
            if demo:
                demo_start = time.monotonic()
                record("scripted_demo_start", period_s=16.0, max_arm_amplitude_deg=6.0)
            snapshot = xml_snapshot(args.model) if args.watch else {}
            next_watch = time.monotonic() + 0.5
            changed_at = None
            quit_requested = False

            while viewer.is_running() and not quit_requested:
                loop_start = time.monotonic()
                reload_reason = None
                with viewer.lock():
                    while not keys.empty():
                        key, received_ns = keys.get_nowait()
                        action = actions.get(key, "native_or_unhandled")
                        record("key", keycode=key, action=action, received_monotonic_ns=received_ns)
                        if action in ("decrease_joint", "increase_joint", "toggle_gripper", "reset_home") and demo:
                            demo = False
                            record("scripted_demo_stop", reason="manual_pose_control")
                            print("scripted demo 已停止；当前进入手动运动学预览。", flush=True)
                        if action in ("previous_joint", "next_joint") and joints:
                            selected = (selected + (1 if action == "next_joint" else -1)) % len(joints)
                            selected_name = joints[selected][0]
                            print(f"当前关节：{selected_name}", flush=True)
                        elif action in ("decrease_joint", "increase_joint") and joints:
                            name, joint = joints[selected]
                            address = int(model.jnt_qposadr[joint])
                            hinge = model.jnt_type[joint] == mj.mjtJoint.mjJNT_HINGE
                            increment = math.radians(args.step_deg) if hinge else args.step_m
                            sign = 1 if action == "increase_joint" else -1
                            value = clamp_joint(model, joint, float(data.qpos[address]) + sign * increment)
                            data.qpos[address] = value
                            record("joint_position_set", joint=name, value=value, unit="rad" if hinge else "m")
                            print(f"{name}: {value:.5f} {'rad' if hinge else 'm'}", flush=True)
                        elif action == "toggle_gripper" and gripper:
                            addresses, low, high = gripper
                            width = float(data.qpos[addresses[0]] - data.qpos[addresses[1]])
                            width = set_width(data, gripper, low if width > (low + high) / 2 else high)
                            record("gripper_position_set", width_m=width)
                            print(f"夹爪名义开口：{width * 1000:.1f} mm（运动学位置）", flush=True)
                        elif action == "toggle_camera":
                            use_wrist_camera = not (viewer.cam.type == mj.mjtCamera.mjCAMERA_FIXED and
                                                    viewer.cam.fixedcamid == camera_id)
                            if use_wrist_camera and camera_id >= 0:
                                free_camera = (viewer.cam.lookat.copy(), float(viewer.cam.distance),
                                               float(viewer.cam.azimuth), float(viewer.cam.elevation))
                                viewer.cam.type = mj.mjtCamera.mjCAMERA_FIXED
                                viewer.cam.fixedcamid = camera_id
                            else:
                                use_wrist_camera = False
                                viewer.cam.type = mj.mjtCamera.mjCAMERA_FREE
                                if free_camera:
                                    viewer.cam.lookat[:] = free_camera[0]
                                    viewer.cam.distance, viewer.cam.azimuth, viewer.cam.elevation = free_camera[1:]
                            record("camera_selected", camera="wrist_rgbd" if use_wrist_camera else "free")
                        elif action == "toggle_collision_group":
                            collisions_visible = not bool(viewer.opt.geomgroup[args.collision_group])
                            viewer.opt.geomgroup[args.collision_group] = int(collisions_visible)
                            record("collision_group_visibility", group=args.collision_group, visible=collisions_visible)
                        elif action == "reset_home":
                            mj.mj_resetDataKeyframe(model, data, home)
                            record("home_reset", keyframe="home")
                        elif action == "reload":
                            reload_reason = "F10"
                        elif action == "quit":
                            quit_requested = True

                    if demo:
                        phase = 2 * math.pi * (loop_start - demo_start) / 16.0
                        for index, (_, joint) in enumerate(demo_joints):
                            address = int(model.jnt_qposadr[joint])
                            offset = math.radians(6.0 if index == 0 else 3.0) * math.sin(phase)
                            data.qpos[address] = clamp_joint(model, joint, home_qpos[address] + offset)
                        if gripper:
                            _, low, high = gripper
                            other = high if demo_width <= (low + high) / 2 else low
                            set_width(data, gripper, demo_width + (other - demo_width) * (1 - math.cos(phase)) / 2)
                        cycle = int((loop_start - demo_start) / 16.0)
                        if cycle != last_demo_cycle:
                            record("scripted_demo_cycle", cycle=cycle, simulation_time_s=float(data.time))
                            last_demo_cycle = cycle
                    data.qvel[:] = 0
                    mj.mj_forward(model, data)
                viewer.sync()

                if args.watch and loop_start >= next_watch:
                    current = xml_snapshot(args.model)
                    if current != snapshot:
                        changed_at, snapshot = loop_start, current
                    elif changed_at is not None and loop_start - changed_at >= 0.4:
                        reload_reason, changed_at = "XML_changed", None
                    next_watch = loop_start + 0.5
                if reload_reason and not quit_requested:
                    record("reload_requested", reason=reload_reason)
                    try:
                        candidate = load_model(mj, args.model)
                        gripper_limits(mj, candidate[0])
                    except Exception as exc:
                        candidate = None
                        record("reload_failed", error=str(exc), retained_previous_viewer=True)
                        print(f"重载失败，保留旧窗口/旧模型：{exc}", file=sys.stderr, flush=True)
                    else:
                        with viewer.lock():
                            use_wrist_camera = (viewer.cam.type == mj.mjtCamera.mjCAMERA_FIXED and
                                                viewer.cam.fixedcamid == camera_id)
                            if not use_wrist_camera:
                                free_camera = (viewer.cam.lookat.copy(), float(viewer.cam.distance),
                                               float(viewer.cam.azimuth), float(viewer.cam.elevation))
                        print("重载：新模型已编译；先关闭旧窗口，再打开新窗口并恢复 home。", flush=True)
                        break
                time.sleep(max(0.0, 1.0 / 60.0 - (time.monotonic() - loop_start)))
        finally:
            close_viewer(viewer)
            record("viewer_closed")
        if candidate is None:
            return
        loaded, next_load_event = candidate, "reload"


def main():
    args = arguments()
    args.events.parent.mkdir(parents=True, exist_ok=True)
    session = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}"
    with args.events.open("a", encoding="utf-8", buffering=1) as events:
        def record(event, **fields):
            events.write(json.dumps({"utc": datetime.now(timezone.utc).isoformat(),
                                     "monotonic_ns": time.monotonic_ns(), "session": session,
                                     "mode": MODE, "event": event, **fields}, ensure_ascii=False) + "\n")

        record("session_start", model=str(args.model), executable=sys.executable,
               watch=args.watch, scripted_demo=args.scripted_demo)
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            message = ("没有 DISPLAY/WAYLAND_DISPLAY，未打开可视化窗口。请在用户 Linux 桌面终端中运行本命令；"
                       "SSH/无桌面会话不能视为用户已看到实时画面。本脚本不会静默改用 headless。")
            record("startup_failed", reason=message)
            print(message, file=sys.stderr)
            return 2
        try:
            import glfw
            import mujoco
            import mujoco.viewer
        except ImportError as exc:
            record("startup_failed", reason=str(exc))
            print(f"请使用已安装 MuJoCo 3.3.0 的项目虚拟环境运行：{exc}", file=sys.stderr)
            return 2
        if mujoco.__version__ != "3.3.0":
            message = f"本入口使用 MuJoCo 3.3.0；当前为 {mujoco.__version__}。请切换到项目虚拟环境。"
            record("startup_failed", reason=message)
            print(message, file=sys.stderr)
            return 2
        if not glfw.init():
            message = "GLFW 无法连接桌面显示服务，未打开 viewer；请检查用户桌面会话/显示权限。"
            record("startup_failed", reason=message)
            print(message, file=sys.stderr)
            return 2
        try:
            run(args, mujoco, mujoco.viewer, glfw, record)
        except KeyboardInterrupt:
            record("interrupted", reason="Ctrl-C")
        except Exception as exc:
            record("runtime_failed", reason=str(exc))
            print(f"预览未完成：{exc}", file=sys.stderr, flush=True)
            return 1
        finally:
            glfw.terminate()
        record("session_end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
