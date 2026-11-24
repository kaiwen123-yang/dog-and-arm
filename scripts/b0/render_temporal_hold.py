"""Render measured validation hold entries and their stopped event clocks."""
import json
import time
from pathlib import Path

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from learning.b0.physics import make_model

OUT = Path("results/b0/standard_temporal_20261124")
RAW = Path("results/raw_large/b0/temporal_entries_v1")
WIDTH, HEIGHT = 448, 240
FPS = 25
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans"
TITLE = ImageFont.truetype(FONT+"-Bold.ttf", 22)
TEXT = ImageFont.truetype(FONT+".ttf", 17)
SMALL = ImageFont.truetype(FONT+".ttf", 15)


def camera(center, distance, azimuth, elevation):
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = center
    cam.distance = distance
    cam.azimuth = azimuth
    cam.elevation = elevation
    return cam


def render(renderer, model, side):
    begin = time.monotonic()
    folder = RAW/f"{side}_0_validation_grip_hold"
    meta = json.loads((folder/"receipt.json").read_text())
    idx = meta["labels"].index(["u0","actor",0,0.])
    with np.load(folder/"substeps.npz") as sub:
        qpost = sub["qpos_post"][:,idx].reshape(-1,model.nq)
        net_force = np.linalg.norm(sub["door_robot_force_N"][:,idx],axis=-1).flatten()
        jaw_force = sub["finger_load_N"][:,idx].reshape(-1,2)
        phase = sub["event_phase"][:,idx].flatten()
    q0 = np.load(folder/"start.npz")["qpos"]
    train_tick = int(np.load(folder/"dynamics.npz")["fail"][0,idx])
    fail = meta["judges"][idx]["failure"]
    tick = fail["first_failure_substep"]
    assert tick == 1 and phase[tick-1] >= 0 and np.all(phase[tick:]==-1)
    q = np.vstack([q0,qpost])
    d = mujoco.MjData(model)
    d.qpos[:] = q0
    mujoco.mj_forward(model,d)
    handle = d.site_xpos[model.site("door_single_"+("front" if side=="pull" else "back")+"_handle").id].copy()
    center = (d.qpos[:3]+handle)/2
    center[2] = .51
    cameras = [camera(center, 2.1, 38 if side=="pull" else 215, -18),
               camera(handle, .42, 52 if side=="pull" else 232, -23)]
    output = OUT/f"hold_{side}_validation_u0.mp4"
    frames_written=0
    def compose(i,pause=False):
        d.qpos[:] = q[i]
        mujoco.mj_forward(model,d)
        frame = Image.new("RGB",(2*WIDTH,416),"#0d1922")
        for col,cam in enumerate(cameras):
            renderer.update_scene(d,camera=cam)
            frame.paste(Image.fromarray(renderer.render()), (col*WIDTH,60))
        draw=ImageDraw.Draw(frame)
        draw.text((14,5),f"{side.upper()}  /  validation hold",font=TITLE,fill="#f4f7fa")
        draw.text((14,34),"Registered u0 first command for 20 ms, followed by the recorded reference commands.",font=SMALL,fill="#c8dbe8")
        draw.text((14,307),f"{2*i:03d} ms   |   "+("PAUSED AT EVENT FAILURE" if pause else "20x slow motion, 2 ms per frame"),
                  font=TEXT,fill="#e4f2f6")
        if i==0:
            status="Measured prefix end. Both clocks start here."
        elif i==tick:
            status=f"Event judge FAIL at {2*tick} ms: {fail['reason']}  ({fail['door_net_force_n']:.2f} N, limit 6 N)"
        else:
            status=f"DIAGNOSTIC TAIL: event score stopped at {2*tick} ms. Training failure at {2*train_tick} ms."
        draw.text((14,334),status,font=TEXT,fill="#ffbc83" if i else "#8ed1ad")
        measurement="No new force observation" if i==0 else (
            f"Previous 2 ms solve:  net door {net_force[i-1]:6.2f} N    finger loads {jaw_force[i-1,0]:6.2f} / {jaw_force[i-1,1]:6.2f} N")
        draw.text((14,364),measurement,font=TEXT,fill="#d2e5eb")
        draw.text((14,389),"Warp off-line response replay   /   end-of-step qpos   /   validation trajectory, segment-initialized event clock",
                  font=SMALL, fill="#acc1cd")
        return np.asarray(frame)
    with imageio.get_writer(output,fps=FPS,codec="libx264",quality=8,macro_block_size=16,ffmpeg_log_level="error") as writer:
        for i in range(len(q)):
            writer.append_data(compose(i))
            frames_written+=1
            if i==tick:
                paused=compose(i,True)
                for _ in range(FPS*2):
                    writer.append_data(paused)
                frames_written+=FPS*2
    return dict(file=str(output),source=str(folder),branch=idx,world="Warp validation response, not an official nominal run",
                event_clock_origin=meta["row"]["formal_start"],event_failure=fail,training_failure_tick=train_tick,
                measured_substeps=len(qpost),dt=.002,fps=FPS,slow_motion_factor=20,paused_seconds=2,
                frames=frames_written,seconds=frames_written/FPS,wall_s=time.monotonic()-begin)


if __name__ == "__main__":
    model=make_model()
    with mujoco.Renderer(model,height=HEIGHT,width=WIDTH) as renderer:
        receipts=[render(renderer,model,side) for side in ("pull","push")]
    (OUT/"hold_videos.json").write_text(json.dumps(receipts,indent=2,allow_nan=False)+"\n")
