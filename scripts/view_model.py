#!/usr/bin/env python3
"""Inspect MJCF without stepping by default; --simulate explicitly enables physics.

Examples:
  python scripts/view_model.py sim/scenes/door_double.xml
  python scripts/view_model.py sim/scenes/door_single.xml --simulate
  MUJOCO_GL=egl python scripts/view_model.py sim/scenes/door_double.xml --snapshot results/doors/double_closed.png

The optional snapshot is a static mj_forward render, not task-success evidence.
Choose MUJOCO_GL before Python starts if using a headless renderer.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import time

import mujoco


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", type=Path)
    parser.add_argument("--simulate", action="store_true", help="Run real mj_step; no controller is supplied by this viewer.")
    parser.add_argument("--snapshot", type=Path, help="Save one static image and exit, without opening a window.")
    parser.add_argument("--camera", help="Named MJCF camera; defaults to overview if present, otherwise the free camera.")
    parser.add_argument("--keyframe", help="Reset to this existing keyframe before displaying.")
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    args = parser.parse_args()
    if args.simulate and args.snapshot:
        parser.error("--snapshot is a static inspection mode; use --simulate separately.")

    model = mujoco.MjModel.from_xml_path(str(args.model.resolve()))
    data = mujoco.MjData(model)
    if args.keyframe:
        key_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, args.keyframe)
        if key_id < 0:
            parser.error(f"No keyframe named {args.keyframe!r}.")
        mujoco.mj_resetDataKeyframe(model, data, key_id)
    camera_name = args.camera
    if camera_name is None and mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "overview") >= 0:
        camera_name = "overview"
    camera_id = -1
    if camera_name:
        camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if camera_id < 0:
            parser.error(f"No camera named {camera_name!r}.")
    mujoco.mj_forward(model, data)
    print(f"{args.model}: nq={model.nq}, nv={model.nv}, nu={model.nu}, neq={model.neq}")

    if args.snapshot:
        from PIL import Image
        model.vis.global_.offwidth = max(model.vis.global_.offwidth, args.width)
        model.vis.global_.offheight = max(model.vis.global_.offheight, args.height)
        with mujoco.Renderer(model, height=args.height, width=args.width) as renderer:
            renderer.update_scene(data, camera=camera_id)
            image = renderer.render()
            args.snapshot.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(image).save(args.snapshot)
        print(f"Saved static inspection image: {args.snapshot}")
        return

    from mujoco import viewer as mj_viewer

    mode = "PHYSICS: mj_step, no control policy" if args.simulate else "STATIC: mj_forward only"
    print(f"{mode}. Close the viewer window to exit.")
    with mj_viewer.launch_passive(model, data) as viewer:
        if camera_id >= 0:
            viewer.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
            viewer.cam.fixedcamid = camera_id
        while viewer.is_running():
            started = time.monotonic()
            with viewer.lock():
                if args.simulate:
                    mujoco.mj_step(model, data)
                else:
                    mujoco.mj_forward(model, data)
            viewer.sync()
            interval = model.opt.timestep if args.simulate else 1 / 60
            time.sleep(max(0.0, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
