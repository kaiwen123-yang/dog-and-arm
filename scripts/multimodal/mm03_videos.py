"""Render the retained MM02 trajectories and the first qualifying MM03 student trajectory."""
import argparse
import json
import math
from pathlib import Path
import subprocess

import mujoco as mj
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from learning.b0.physics import build
from scripts.b0.render_saved_success_hd import FPS, HEIGHT, WIDTH, verify_video
from scripts.multimodal.collect_feasibility import teacher_config
from scripts.multimodal.mm03_launch import read, write


SELECTION = (
    ("r6_bc_stop", "formal", "formal_supervised_aggregate_tr_nominal_pull_15_pure", "timeout:settle"),
    ("r6_bc_support", "formal", "formal_supervised_aggregate_va_pose_pull_15_pure", "wheel_support_or_tilt"),
    ("r6_h32_push15", "formal", "formal_model_trajectory_tr_nominal_push_15_pure", "wheel_support_or_tilt"),
    ("r2_h32_push15", "round2/development", "round2_development_model_trajectory_tr_nominal_push_15_pure", None),
)


def render(case, episode, dest, name, closeup):
    receipt = dest.with_suffix(".json")
    if dest.exists() and receipt.exists():
        return read(receipt)
    meta = read(episode/"metadata.json")
    result = read(case)
    times = np.load(episode/"t.npy")
    positions = np.load(episode/"qpos.npy", mmap_mode="r")
    cfg = teacher_config(meta["side"], meta["target_deg"], dict(id=meta["scene_id"],perturbation=meta["perturbation"]))
    model = build(cfg)
    model.vis.global_.offwidth,model.vis.global_.offheight = WIDTH,HEIGHT
    if meta.get("panel_rgb") is not None:
        model.geom("door_single_panel").rgba[:3] = meta["panel_rgb"]
    ticks = np.rint(times/.002).astype(int)
    if (ticks[0] or ticks[-1] != result["physics_steps"] or not (np.diff(ticks)>0).all()
            or positions.shape!=(len(ticks),model.nq)):
        raise ValueError(f"Recorded native trajectory is incomplete: {episode}")
    stride = round(1/(FPS*.002))
    start = max(0,math.ceil((ticks[-1]-1500)/stride)*stride) if closeup else 0
    wanted = np.r_[np.arange(start,ticks[-1],stride),ticks[-1]]
    index = np.searchsorted(ticks,wanted)
    if not np.array_equal(ticks[index], wanted):
        raise ValueError(f"Missing real-time frame in {episode}")
    if not (meta["source"]=="pure" and result["teacher_steps"]==0):
        raise ValueError("Expected a zero-teacher frame0 episode")
    jaw = model.joint("door_single_hinge").qposadr.item()
    base = model.body("m1_base_link").id
    cam = mj.MjvCamera()
    cam.azimuth, cam.elevation, cam.distance = 130., -13., 1.40
    failure = result.get("first_failure") or {}
    outcome = "12/12 complete" if result["success"] else failure.get("reason",meta.get("failure",""))
    try:
        font = ImageFont.truetype("DejaVuSans.ttf",28)
    except OSError:
        font = ImageFont.load_default()
    options = mj.MjvOption()
    options.sitegroup[:] = 0
    data = mj.MjData(model)
    tmp = dest.with_suffix(".partial.mp4")
    cmd = ["ffmpeg","-v","error","-nostdin","-y","-f","rawvideo","-pix_fmt","rgb24",
           "-s",f"{WIDTH}x{HEIGHT}","-r",str(FPS),"-i","pipe:0","-an","-c:v","libx264",
           "-crf","18","-preset","veryfast","-threads","2","-pix_fmt","yuv420p","-movflags","+faststart",str(tmp)]
    with mj.Renderer(model,height=HEIGHT,width=WIDTH) as renderer:
        enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            for k in index:
                data.qpos[:] = positions[k]
                mj.mj_forward(model,data)
                if closeup:
                    cam.lookat[:] = data.xpos[base]
                    cam.lookat[2] *= .78
                renderer.update_scene(data,camera=cam if closeup else "p6_overview",scene_option=options)
                frame = Image.fromarray(renderer.render())
                pen = ImageDraw.Draw(frame)
                pen.rectangle((0,0,WIDTH,83),fill=(22,24,28))
                pen.text((18,3), f"{name}   |   {meta['source_policy']}   |   {meta['scene_id']}   |   frame 0 student",font=font)
                pen.text((18,43),f"{meta['side']} {meta['target_deg']} deg   |   t = {times[k]:.2f} s   |   door = {np.rad2deg(data.qpos[jaw]):.2f} deg   |   {outcome}",font=font)
                enc.stdin.write(frame.tobytes())
        finally:
            enc.stdin.close()
            rc = enc.wait()
        if rc:
            raise RuntimeError(f"ffmpeg exited {rc} for {dest}")
    stream = verify_video(tmp,len(index))
    tmp.replace(dest)
    record = dict(file=dest.name, case=str(case), raw_episode=str(episode), episode=meta["episode_id"],
                  source="original_recorded_trajectory", actual_new_integration_steps=0,
                  checkpoint=result.get("checkpoint"), source_sha=result.get("sha") or meta.get("source_checkpoint_sha256"),
                  success=result["success"], ordered_events=result["ordered_event_count"],
                  first_failure=failure or None, teacher_decisions=result["teacher_steps"],
                  physics_steps=result["physics_steps"], first_shown_step=int(wanted[0]),last_shown_step=int(wanted[-1]),
                  camera="following base" if closeup else "p6_overview", fps=FPS,width=WIDTH,height=HEIGHT,
                  frames=len(index), physical_duration_s=float(times[index[-1]]-times[index[0]]),
                  stream_duration_s=len(index)/FPS, codec=stream["codec_name"],original_speed=True,
                  full_decode_and_pts_verified=True)
    write(receipt,record)
    print(json.dumps({key:record[key] for key in ("file","episode","frames","success")}),flush=True)
    return record


def original_videos(root):
    parent = Path("/root/autodl-tmp/mm02-20261125")
    dst = root/"videos/mm02"
    dst.mkdir(parents=True, exist_ok=True)
    records=[]
    for stem, part, case_id, reason in SELECTION:
        directory = parent/part/case_id
        case = directory/"result.json"
        result = read(case)
        failure = result["first_failure"]
        if reason and failure["reason"]!=reason:
            raise ValueError(f"Selected case changed: {case}")
        if stem=="r2_h32_push15" and result["ordered_event_count"]<2:
            raise ValueError("R2 historical episode does not include the documented settle")
        for close in (False,True):
            file=dst/f"{stem}_{'detail' if close else 'full'}_1080p.mp4"
            records.append(render(case,directory/"episode",file,f"MM02 {stem.split('_')[0].upper()}",close))
            write(dst/"index.json",dict(videos=records,phase="complete" if len(records)==8 else "rendering"))
    return records


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--first-success", action="store_true")
    opt=p.parse_args()
    if opt.first_success:
        from scripts.multimodal.mm03_first import deliver
        deliver(opt.root)
    else:
        original_videos(opt.root)
