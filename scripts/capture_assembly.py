#!/usr/bin/env python3
"""Export the actual assembly model's static views and optional kinematic video.

Examples (run in the project's MuJoCo 3.3.0 environment):
    python scripts/capture_assembly.py
    python scripts/capture_assembly.py --video

Select an OpenGL backend in the calling shell when necessary.  This script
does not set MUJOCO_GL, alter shell configuration, call mj_step or use hardware.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
MODE = "KINEMATIC_PREVIEW"
CAMERAS = {"overview": "overview", "side": "side", "front": "front", "wrist_rgb": "wrist_rgbd"}
FINGERS = ("piper_gripper_joint1", "piper_gripper_joint2")
VIDEO_SECONDS = 8.0
VIDEO_ARM_JOINT = "piper_joint2"
VIDEO_MAX_ANGLE_RAD = math.radians(5.0)


def font(size=15):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def annotated(rgb: np.ndarray, *lines: str) -> Image.Image:
    raw = Image.fromarray(rgb).convert("RGB")
    height = 10 + 21 * len(lines)
    image = Image.new("RGB", (raw.width, raw.height+height), (15, 21, 29))
    image.paste(raw, (0, height))
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((10, 5 + 21 * index), line, font=font(), fill=(237, 242, 247))
    return image


def width_from_data(model, data, finger_ids) -> float:
    values = [float(data.qpos[model.jnt_qposadr[index]]) for index in finger_ids]
    if abs(values[0] + values[1]) > 1e-7:
        raise ValueError("The pose violates the two-finger q2=-q1 relation")
    return 2.0 * values[0]


def set_width(model, data, finger_ids, width: float) -> None:
    for index, value in zip(finger_ids, (width / 2.0, -width / 2.0)):
        if model.jnt_limited[index]:
            lower, upper = model.jnt_range[index]
            if not lower <= value <= upper:
                raise ValueError(f"Requested preview gripper width is outside the model limits: {width}")
        data.qpos[model.jnt_qposadr[index]] = value


def rgb_frame(renderer, data, options, camera: str) -> np.ndarray:
    renderer.disable_depth_rendering()
    renderer.update_scene(data, camera=camera, scene_option=options)
    return renderer.render()


def depth_preview(depth: np.ndarray, near: float, far: float, width: float) -> tuple[Image.Image, dict]:
    valid = np.isfinite(depth) & (depth > 0) & (depth < far * (1.0 - 1e-5))
    pixels = depth[valid]
    if pixels.size == 0:
        raise ValueError("Wrist camera has no finite foreground depth before its far plane")
    low, high = map(float, np.percentile(pixels, [2, 98]))
    if high <= low:
        high = low + 0.001
    scaled = np.zeros(depth.shape, dtype=float)
    scaled[valid] = np.clip((depth[valid] - low) / (high - low), 0, 1)
    palette = np.array([[38, 16, 76], [50, 97, 140], [35, 159, 139],
                        [151, 204, 83], [253, 231, 37]], dtype=float)
    positions = scaled * (len(palette) - 1)
    indices = np.minimum(positions.astype(int), len(palette) - 2)
    fractions = positions - indices
    color = ((1-fractions[..., None]) * palette[indices]
             + fractions[..., None] * palette[indices+1]).astype(np.uint8)
    color[~valid] = 0
    labeled = annotated(color, f"{MODE} | width {1000*width:.1f} mm",
                        "SYNTHETIC_ALIGNED_RGBD | optical-axis depth (m)")
    image = Image.new("RGB", (labeled.width, labeled.height+64), (15, 21, 29))
    image.paste(labeled, (0, 0))
    draw = ImageDraw.Draw(image)
    bar_left, bar_right, bar_y = 18, image.width-18, image.height-33
    draw.rectangle((0, image.height-61, image.width, image.height), fill=(15, 21, 29))
    for x in range(bar_left, bar_right):
        coordinate = (x-bar_left) / max(1, bar_right-bar_left-1) * (len(palette)-1)
        index = min(int(coordinate), len(palette)-2)
        value = (1-(coordinate-index))*palette[index] + (coordinate-index)*palette[index+1]
        draw.line((x, bar_y, x, bar_y+11), fill=tuple(value.astype(int)))
    draw.text((bar_left, image.height-58), f"Display: {low:.3f} to {high:.3f} m (2-98%)",
              font=font(13), fill=(237, 242, 247))
    draw.text((bar_left, image.height-19), "Raw metric values: wrist_depth_m.npy",
              font=font(12), fill=(237, 242, 247))
    return image, {"raw_dtype": str(depth.dtype), "shape": list(depth.shape),
                   "units": "m", "meaning": "linear optical-axis depth from MuJoCo Renderer",
                   "near_clip_m": near, "far_clip_m": far,
                   "foreground_pixels": int(pixels.size), "total_pixels": int(depth.size),
                   "foreground_min_m": float(pixels.min()), "foreground_max_m": float(pixels.max()),
                   "preview_percentiles": [2, 98], "preview_display_range_m": [low, high],
                   "raw_array_modified_for_preview": False,
                   "background_note": "Far-plane/background values remain unchanged in the raw NPY; black in preview."}


def choose_arm_offset(model, data, home: int) -> dict:
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, VIDEO_ARM_JOINT)
    tcp = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "piper_tcp_nominal")
    if joint < 0 or tcp < 0:
        raise ValueError("The preview needs piper_joint2 and the piper_tcp_nominal site")
    if model.jnt_type[joint] != mujoco.mjtJoint.mjJNT_HINGE:
        raise ValueError("The preview arm joint must be a hinge")
    address = model.jnt_qposadr[joint]
    mujoco.mj_resetDataKeyframe(model, data, home)
    mujoco.mj_forward(model, data)
    initial, initial_z = float(data.qpos[address]), float(data.site_xpos[tcp, 2])
    candidates = []
    for sign in (1, -1):
        target = initial + sign * VIDEO_MAX_ANGLE_RAD
        if model.jnt_limited[joint]:
            target = float(np.clip(target, *model.jnt_range[joint]))
        if abs(target-initial) < 1e-10:
            continue
        mujoco.mj_resetDataKeyframe(model, data, home)
        data.qpos[address] = target
        mujoco.mj_forward(model, data)
        candidates.append({"target_q_rad": target, "offset_rad": target-initial,
                           "tcp_world_z_change_m": float(data.site_xpos[tcp, 2])-initial_z})
    if not candidates:
        raise ValueError("No legal small arm-joint offset from home")
    chosen = max(candidates, key=lambda candidate: candidate["tcp_world_z_change_m"])
    return {"joint": VIDEO_ARM_JOINT, "joint_id": int(joint), "qpos_address": int(address),
            "home_q_rad": initial, **chosen, "candidate_offsets": candidates,
            "selection": "Choose the legal +/-5 degree candidate with higher TCP world Z using FK only.",
            "raises_tcp_at_peak_candidate": chosen["tcp_world_z_change_m"] > 0}


def smooth_width(frame: int, points: list[tuple[int, float]]) -> float:
    for (begin, start), (end, finish) in zip(points, points[1:]):
        if frame <= end:
            phase = (frame-begin) / (end-begin)
            blend = phase*phase*(3-2*phase)
            return start + blend*(finish-start)
    return points[-1][1]


def render_video(args, model, data, renderer, options, home, finger_ids) -> dict:
    motion = choose_arm_offset(model, data, home)
    frames = int(VIDEO_SECONDS * args.fps)
    waypoints = [(0, .04), (frames//3, .08), (2*frames//3, .02), (frames-1, .04)]
    path = args.output / "kinematic_preview.mp4"
    samples = []
    print(f"Rendering {frames} kinematic frames at {args.fps} fps; physics remains unstepped.", flush=True)
    with imageio.get_writer(path, fps=args.fps, codec="libx264", quality=8,
                           pixelformat="yuv420p", macro_block_size=1,
                           ffmpeg_log_level="error") as writer:
        for frame in range(frames):
            phase = frame / (frames-1)
            arm_q = motion["home_q_rad"] + motion["offset_rad"] * math.sin(math.pi*phase)**2
            width = smooth_width(frame, waypoints)
            mujoco.mj_resetDataKeyframe(model, data, home)
            data.qpos[motion["qpos_address"]] = arm_q
            set_width(model, data, finger_ids, width)
            data.qvel[:] = 0
            mujoco.mj_forward(model, data)
            panels = []
            for camera in ("overview", "wrist_rgbd"):
                rgb = rgb_frame(renderer, data, options, camera)
                panel = annotated(rgb, f"{MODE} | {camera}",
                                  f"width {1000*width:.1f} mm | video t={frame/args.fps:.2f} s")
                panels.append(np.asarray(panel))
            writer.append_data(np.concatenate(panels, axis=1))
            samples.append({"frame": frame, "video_time_s": frame/args.fps,
                            "arm_joint_q_rad": arm_q, "gripper_width_m": width})
            if (frame+1) % (2*args.fps) == 0 or frame+1 == frames:
                print(f"Video frames saved: {frame+1}/{frames}", flush=True)
    actual_angles = [sample["arm_joint_q_rad"] for sample in samples]
    actual_widths = [sample["gripper_width_m"] for sample in samples]
    return {"file": path.name, "mode": MODE, "physics_stepped": False,
            "duration_s": frames/args.fps, "fps": args.fps, "frame_count": frames,
            "frame_size_px": [2*args.width, args.height+52], "views": ["overview", "wrist_rgbd"],
            "arm_motion": motion, "actual_arm_range_rad": [min(actual_angles), max(actual_angles)],
            "actual_arm_range_deg": list(map(math.degrees, [min(actual_angles), max(actual_angles)])),
            "gripper_waypoints": [{"frame": frame, "video_time_s": frame/args.fps,
                                    "width_m": width} for frame, width in waypoints],
            "actual_gripper_width_range_m": [min(actual_widths), max(actual_widths)],
            "other_coordinates": "Reset from home and unchanged in every frame.",
            "time_note": "Video timestamps are media time; mj_forward does not advance physics time.",
            "frame_parameters": samples}


def capture(args, manifest: dict) -> None:
    if mujoco.__version__ != "3.3.0":
        raise RuntimeError(f"Use MuJoCo 3.3.0 for this project; found {mujoco.__version__}")
    model = mujoco.MjModel.from_xml_path(str(args.model))
    data = mujoco.MjData(model)
    home = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    if home < 0:
        raise ValueError("Assembly model is missing its home keyframe")
    finger_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in FINGERS]
    if any(index < 0 for index in finger_ids):
        raise ValueError("Assembly model is missing its physical finger joints")
    cameras = dict(CAMERAS)
    if mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "wrist_detail") >= 0:
        cameras["wrist_detail"] = "wrist_detail"
    camera_ids = {name: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, name)
                  for name in cameras.values()}
    if any(index < 0 for index in camera_ids.values()):
        raise ValueError(f"Missing required model cameras: {[name for name, index in camera_ids.items() if index < 0]}")
    mujoco.mj_resetDataKeyframe(model, data, home)
    mujoco.mj_forward(model, data)
    width = width_from_data(model, data, finger_ids)
    options = mujoco.MjvOption()
    options.geomgroup[3] = 0  # collision-only duplicates are hidden
    options.sitegroup[:] = 0
    # Offscreen buffer capacity is changed only in this in-memory model.
    model.vis.global_.offwidth = max(int(model.vis.global_.offwidth), args.width)
    model.vis.global_.offheight = max(int(model.vis.global_.offheight), args.height)
    manifest.update(home_qpos=data.qpos.tolist(), still_gripper_width_m=width,
                    cameras={name: {"id": int(index), "fovy_deg": float(model.cam_fovy[index]),
                                    "world_position_m": data.cam_xpos[index].tolist(),
                                    "world_rotation_matrix": data.cam_xmat[index].reshape(3, 3).tolist()}
                             for name, index in camera_ids.items()}, images={})
    with mujoco.Renderer(model, height=args.height, width=args.width) as renderer:
        wrist_rgb = None
        for filename, camera in cameras.items():
            rgb = rgb_frame(renderer, data, options, camera)
            annotated(rgb, f"{MODE} | {camera} | width {1000*width:.1f} mm").save(args.output / f"{filename}.png")
            manifest["images"][filename] = {"file": f"{filename}.png", "camera": camera,
                                           "annotations_added": True, "annotation_placement": "31-pixel top margin",
                                           "file_size_px": [args.width, args.height+31]}
            print(f"Saved {filename}.png from {camera}", flush=True)
            if camera == "wrist_rgbd":
                wrist_rgb = rgb.copy()
        # Explicitly restore the wrist scene after any optional external view.
        # Home qpos is unchanged. MuJoCo 3.3 Renderer converts depth to metres.
        renderer.update_scene(data, camera="wrist_rgbd", scene_option=options)
        renderer.enable_depth_rendering()
        depth = renderer.render().copy()
        renderer.disable_depth_rendering()
        np.save(args.output / "wrist_depth_m.npy", depth, allow_pickle=False)
        np.save(args.output / "wrist_rgb_uint8.npy", wrist_rgb, allow_pickle=False)
        near = float(model.vis.map.znear * model.stat.extent)
        far = float(model.vis.map.zfar * model.stat.extent)
        preview, depth_info = depth_preview(depth, near, far, width)
        preview.save(args.output / "wrist_depth_preview.png")
        manifest["depth"] = {**depth_info, "file": "wrist_depth_m.npy",
                             "preview_file": "wrist_depth_preview.png", "camera": "wrist_rgbd",
                             "preview_size_px": [args.width, args.height+116],
                             "paired_raw_rgb_file": "wrist_rgb_uint8.npy",
                             "same_camera_pose_and_pixel_grid_as_rgb": True}
        if args.video:
            manifest["video"] = render_video(args, model, data, renderer, options, home, finger_ids)
    manifest["status"] = "completed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, default=ROOT / "sim/scenes/assembly_preview.xml")
    parser.add_argument("--output", type=Path, default=ROOT / "results/assembly")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    if args.width < 160 or args.height < 120 or not 1 <= args.fps <= 60:
        parser.error("Use width >= 160, height >= 120, and fps between 1 and 60")
    if args.video and args.height % 2:
        parser.error("Video height must be even for yuv420p")
    args.model, args.output = args.model.expanduser().resolve(), args.output.expanduser().resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "mode": MODE,
                "model": args.model.relative_to(ROOT).as_posix() if args.model.is_relative_to(ROOT) else str(args.model),
                "mujoco_version": mujoco.__version__, "status": "failed",
                "render_size_px": [args.width, args.height], "physics_stepped": False,
                "hardware_accessed": False, "gl_backend_requested_by_caller": os.environ.get("MUJOCO_GL"),
                "camera_mode": "synthetic_aligned_rgbd", "hardware_calibrated": False,
                "notes": ["All images are rendered from the actual assembled MuJoCo model.",
                          "PNG/video labels and depth color legend are in outside margins, leaving the full camera image visible.",
                          "Annotated PNGs are for inspection; paired unannotated RGB/depth arrays are saved as NPY.",
                          "Wrist RGB and depth share one virtual camera, pose and pixel grid.",
                          "Raw depth is linear optical-axis distance in metres, not a normalized display image.",
                          "These are synthetic images, not DC1 hardware data or optical/hand-eye calibration.",
                          "Only mj_forward is used; this does not demonstrate standing, dynamics or door manipulation."]}
    try:
        capture(args, manifest)
    except Exception as error:
        manifest["error"] = f"{type(error).__name__}: {error}"
        print(manifest["error"], file=sys.stderr)
        print("If this is a graphics-context error, select a working MUJOCO_GL backend in the calling shell.", file=sys.stderr)
    manifest_path = args.output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{manifest['status']}: {manifest_path}")
    return 0 if manifest["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
