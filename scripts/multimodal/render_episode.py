"""Render an original-speed HD overview from a single MM-01 integrated episode."""
import argparse
import json
from pathlib import Path
import subprocess

import mujoco as mj
import numpy as np

from learning.b0.physics import build
from scripts.b0.render_saved_success_hd import WIDTH, HEIGHT, FPS, verify_video
from scripts.multimodal.collect_feasibility import teacher_config


def render_episode(episode, output):
    meta=json.loads((episode/"metadata.json").read_text())
    cfg=teacher_config(meta["side"], meta["target_deg"],
                       {"id":meta["scene_id"], "perturbation":meta["perturbation"]})
    model=build(cfg)
    model.vis.global_.offwidth,model.vis.global_.offheight=WIDTH,HEIGHT
    if meta.get("panel_rgb") is not None:
        model.geom("door_single_panel").rgba[:3]=meta["panel_rgb"]
    times=np.load(episode/"t.npy")
    q=np.load(episode/"qpos.npy",mmap_mode="r")
    annotate = meta.get("schema") == "mm02_causal_corrections_v1"
    if annotate:
        from PIL import Image, ImageDraw, ImageFont
        source = np.load(episode/"execution_source.npy")
        stages = np.load(episode/"judge_phase.npy")
        hinge = model.joint("door_single_hinge").qposadr.item()
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 27)
        except OSError:
            font = ImageFont.load_default(size=27)
    ticks=np.rint(times/model.opt.timestep).astype(int)
    stride=round(1/(FPS*model.opt.timestep))
    if ticks[0] or ticks[-1]!=meta["physics_steps"] or not np.all(np.diff(ticks)>0):
        raise ValueError("Integrated episode time is inconsistent")
    frames=np.flatnonzero((ticks%stride==0)|(np.arange(len(ticks))==len(ticks)-1))
    if not np.array_equal(ticks[frames[:-1]],np.arange(0,ticks[-1],stride)):
        raise ValueError("Missing physical samples for real-time playback")
    dest=Path(output)
    tmp=dest.with_suffix(".partial.mp4")
    d=mj.MjData(model)
    option=mj.MjvOption()
    option.sitegroup[:]=0
    cmd=["ffmpeg","-v","error","-nostdin","-y","-f","rawvideo","-pix_fmt","rgb24",
         "-s",f"{WIDTH}x{HEIGHT}","-r",str(FPS),"-i","pipe:0","-an","-c:v","libx264",
         "-crf","17","-preset","veryfast","-threads","3","-pix_fmt","yuv420p",
         "-movflags","+faststart",str(tmp)]
    with mj.Renderer(model,height=HEIGHT,width=WIDTH) as renderer:
        proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        try:
            for k in frames:
                d.qpos[:]=q[k]
                mj.mj_forward(model,d)
                renderer.update_scene(d, camera="p6_overview",scene_option=option)
                pixels = renderer.render()
                if annotate:
                    frame = Image.fromarray(pixels)
                    draw = ImageDraw.Draw(frame)
                    i = min(k, len(source)-1)
                    label = ("teacher" if source[i] else "student")
                    phase = meta["judge_phases"][int(stages[i])]
                    lines = [f'MM-02  {meta["source_policy"]}  |  {meta["partition"]}',
                             meta["episode_id"],
                             f'{meta["side"]}  target {meta["target_deg"]} deg   measured '
                             f'{np.rad2deg(q[k,hinge]):.2f} deg   |   t = {times[k]:.2f} s'
                             f'   |   {phase}   |   control: {label}']
                    draw.rectangle((0,0,WIDTH,118),fill=(20,23,28))
                    for line_id,line in enumerate(lines):
                        draw.text((20,5+line_id*36),line,fill=(250,250,250),font=font)
                    pixels = np.asarray(frame)
                proc.stdin.write(pixels.tobytes())
        finally:
            proc.stdin.close()
            rc=proc.wait()
        if rc:
            raise RuntimeError(f"ffmpeg exited with {rc}")
    stream=verify_video(tmp,len(frames))
    tmp.replace(dest)
    receipt=dict(episode_id=meta["episode_id"],source=meta["source"],input_path=str(episode),
                 success=meta["success"],fps=FPS,width=WIDTH,height=HEIGHT,
                 physics_s=float(times[-1]),frames=len(frames),first_step=int(ticks[frames[0]]),
                 final_step=int(ticks[frames[-1]]),playback_seconds=len(frames)/FPS,
                 camera="p6_overview",full_decode_and_pts_verified=True,codec=stream["codec_name"])
    dest.with_suffix(".json").write_text(json.dumps(receipt,indent=2)+"\n")
    return receipt


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    print(json.dumps(render_episode(args.episode,args.output)),flush=True)
