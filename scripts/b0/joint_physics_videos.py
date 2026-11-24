"""Render judged successor-driven policy motion up to each development judge stop."""
import argparse

import imageio.v2 as imageio
import mujoco
import numpy as np
from PIL import Image, ImageDraw
from learning.b0.physics import make_model
from scripts.b0.joint_physics_audit import OUT,RAW,read,write
from scripts.b0.render_temporal_hold import camera,WIDTH,HEIGHT,TITLE,TEXT,SMALL


def render(side,node):
    model=make_model()
    d=mujoco.MjData(model)
    dest=OUT/(side+"_"+node+"_actor.mp4")
    clips=[]
    count=0
    with mujoco.Renderer(model,height=HEIGHT,width=WIDTH) as renderer,imageio.get_writer(dest,fps=25,codec="libx264",quality=7,macro_block_size=16,ffmpeg_log_level="error") as writer:
        for phase in ("grasp","hold","release"):
            name=f"{side}_0_validation_grip_{phase}"
            folder=RAW/"closedloop"/node/"formal_2ms"/"repeat0"/name
            info=read(folder/"result.json")
            with np.load(folder/"trace.npz") as tr:
                q=np.concatenate((tr["query_q0"][:1],tr["qpos_post"]))
                force=np.linalg.norm(tr["door_robot_force_N"],axis=-1)
                fingers=tr["finger_load_N"]
                actual_calls=tr["query_judge_ticks"].cumsum()
            assert len(q)==info["scored_ticks"]+1==len(force)+1
            d.qpos[:]=q[0]
            mujoco.mj_forward(model,d)
            h=d.site_xpos[model.site("door_single_"+("front" if side=="pull" else "back")+"_handle").id].copy()
            c=(d.qpos[:3]+h)/2
            c[2]=.51
            cams=[camera(c,2.05,38 if side=="pull" else 215,-18),camera(h,.44,52 if side=="pull" else 232,-22)]
            selected=np.unique(np.r_[0,1,np.arange(5,len(q),5),len(q)-1])
            first=count
            for i in selected:
                d.qpos[:]=q[i]
                mujoco.mj_forward(model,d)
                img=Image.new("RGB",(2*WIDTH,416),"#10202a")
                draw=ImageDraw.Draw(img)
                draw.text((16,4),f"{side.upper()}   {phase.upper()}    /    {node}",font=TITLE,fill="white")
                draw.text((16,33),"Warp 2 ms  |  validated 200 ms prefix  |  frozen Actor with measured successor at each 20 ms",font=SMALL,fill="#bad3e0")
                for col,cam in enumerate(cams):
                    renderer.update_scene(d,camera=cam)
                    img.paste(Image.fromarray(renderer.render()),(col*WIDTH,58))
                queried=int(np.searchsorted(actual_calls,max(0,i-1),side="right"))+1
                jaw=(q[i,29]-q[i,30])*1000
                draw.text((16,307),f"{2*i:04d} ms     |     Actor query {queried} of {info['actor_queries']}     |     jaw width {jaw:.2f} mm",font=TEXT,fill="#f4f7f8")
                measured=(f"Last solve: net door {force[i-1]:.2f} N, fingers {fingers[i-1,0]:.2f} / {fingers[i-1,1]:.2f} N" if i else "Initial pose after measured prefix")
                draw.text((16,338),measured,font=TEXT,fill="#b9d9d4")
                stop=info["first_failure"]
                stopped=i==len(q)-1
                note=("Judge stop: "+stop["reason"] if stop else ("Segment passed" if info["passed"] else "640 ms development horizon")) if stopped else "Development case, original event judge"
                draw.text((16,372),note,font=TEXT,fill="#ffcb94" if stopped else "#b8cbd4")
                repetitions=28 if stopped else (12 if i==0 else 1)
                for _ in range(repetitions):
                    writer.append_data(np.asarray(img))
                count+=repetitions
            clips.append(dict(phase=phase,frames=count-first,measured_s=info["duration_s"],actor_queries=info["actor_queries"],
                judge=info["first_failure"],passed=info["passed"],raw=info["raw"],start=name))
    reader=imageio.get_reader(dest)
    try:
        actual=sum(1 for _ in reader)
    finally:
        reader.close()
    assert actual==count
    return dict(side=side,node=node,file=str(dest),frames_verified=actual,fps=25,rendering="Only original-judge observed samples, final image held for reading. Three independent validation entries, all scored commands from the actual frozen Actor.",segments=clips)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node",default="shared_u0")
    a=p.parse_args()
    rows=[render(side,a.node) for side in ("pull","push")]
    write(OUT/("videos_"+a.node+".json"),dict(clips=rows))
    print([(r["side"],r["frames_verified"]) for r in rows])
