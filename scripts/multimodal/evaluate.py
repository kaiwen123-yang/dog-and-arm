"""Execute a frozen 23-channel student from the original physical free-base reset."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

import mujoco as mj
import numpy as np

from learning.b0.physics import build
from learning.multimodal.judge import DoorTaskJudge
from scripts.b0.eval_contact_segments import continuous_initial
from scripts.multimodal.collect import EpisodeWriter, instruction, load_scenes
from scripts.multimodal.collect_feasibility import teacher_config
from scripts.multimodal.render_episode import render_episode


class SensorClient:
    def __init__(self, python, checkpoint, text):
        self.process=subprocess.Popen([str(python),"-m","scripts.multimodal.policy_worker",str(checkpoint),text],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        if self.process.stdout.readline()!=b"READY\n":
            self.close()
            raise RuntimeError("Frozen Actor initialization failed")
        self.image_t=None

    def action(self, proprio, previous, image, image_t, now):
        fresh=self.image_t!=image_t
        packet=[struct.pack("<Bf",fresh,now-image_t),np.asarray(proprio,dtype="<f4").tobytes(),
                np.asarray(previous,dtype="<f4").tobytes()]
        if fresh:
            rgb,depth,valid=image
            packet.extend((rgb.tobytes(),np.asarray(depth,dtype="<f4").tobytes(),
                           np.asarray(valid,dtype="?").tobytes()))
            self.image_t=image_t
        proc=self.process
        proc.stdin.write(b"".join(packet))
        proc.stdin.flush()
        answer=proc.stdout.read(23*4)
        if len(answer)!=23*4:
            raise RuntimeError(f"Actor worker lost at {now:.3f}s, exit={proc.poll()}")
        return np.frombuffer(answer,dtype="<f4").astype(np.float64)

    def close(self):
        self.process.stdin.close()
        self.process.stdout.close()
        if self.process.wait():
            raise RuntimeError("Frozen Actor process returned an error")


def evaluate(args):
    scene=next(row for row in load_scenes()["scenes"] if row["id"]==args.scene)
    if args.feedback_dir and scene["split"]!="train":
        raise ValueError("Training feedback must use a preassigned training scene")
    if args.goal not in load_scenes()["goal_deg"]:
        raise ValueError("Unregistered command target")
    cfg=teacher_config(args.side,args.goal,scene)
    model=build(cfg)
    if mj.__version__!="3.3.0" or abs(model.opt.timestep-.002)>1e-12:
        raise ValueError("Use the native 3.3.0 physics runtime and registered 2 ms step")
    d,_,_=continuous_initial(model,cfg,None)
    initial_hash=hashlib.sha256(np.r_[d.qpos,d.qvel].astype("<f8").tobytes()).hexdigest()
    name=f"{args.branch}_{scene['id']}_{args.side}_{args.goal}"
    case=args.output/name
    case.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    text=instruction(args.side,args.goal)
    checkpoint_hash=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
    source=f"MM01_frozen_{args.branch}"
    recorder=EpisodeWriter(model,cfg,scene,args.side,args.goal,name,source)
    mapping=recorder.mapping
    judge=DoorTaskJudge(model,cfg,args.side,args.goal)
    previous=np.zeros(23)
    client=SensorClient(args.actor_python,args.checkpoint,text)
    try:
        while not judge.passed and not judge.failure:
            now=float(d.time)
            proprio,image=recorder.boundary(now,d.qpos,d.qvel)
            raw=client.action(proprio,previous,image,recorder.arrays["image_t"][-1],now)
            if not np.isfinite(raw).all():
                raise ValueError("Nonfinite policy action")
            previous=np.clip(raw,-1.,1.)
            target=mapping.offset+mapping.scale*previous
            servo=target*mapping.finger_factor
            recorder.action(raw,previous,target,judge.phase,supervised=False)
            for _ in range(10):
                q,v=d.qpos.copy(),d.qvel.copy()
                d.ctrl[mapping.actuator_ids]=servo+d.qfrc_bias[mapping.dof]*mapping.bias_gain
                mj.mj_step(model,d)
                c=judge.observe(d,q,v)
                recorder.substep(d.ctrl[mapping.actuator_ids],c.finger_normal)
                if judge.passed or judge.failure:
                    break
        recorder.boundary(float(d.time),d.qpos,d.qvel)
        path=args.feedback_dir/name if args.feedback_dir else case/"episode"
        meta=recorder.save(path,judge.passed,judge.failure["reason"] if judge.failure else None,
                           extra=dict(checkpoint_sha256=checkpoint_hash,initial_state_sha256=initial_hash,
                                      image_source="native integrated episode, synchronous simulated wrist RGB-D",
                                      policy_request_recording="online_preclamp_head",
                                      decision_source="frozen student on its own successive observations"))
    finally:
        client.close()
        recorder.sensors.close()
    result=dict(method="M1Piper-Multimodal-v1",branch=args.branch,scene_id=args.scene,
                scene_split=scene["split"],side=args.side,target_deg=args.goal,task_text=text,
                measured_at_utc=datetime.now(timezone.utc).isoformat(),raw_episode=str(path),
                checkpoint=str(args.checkpoint),checkpoint_sha256=checkpoint_hash,case_id=name,
                initial_state_sha256=initial_hash,decision_calls=meta["transitions"],
                camera_frames=meta["frames"],final_deg=float(np.rad2deg(d.qpos[judge.hinge.qposadr.item()])),
                bc_labels=meta["bc_labels"],wall_s=time.monotonic()-start,**judge.result())
    (case/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:result[k] for k in ("case_id","success","next_phase","final_deg","physics_steps")}),flush=True)
    if result["success"] and args.first_video_dir:
        args.first_video_dir.mkdir(parents=True,exist_ok=True)
        claim=args.first_video_dir/"first_success.json"
        try:
            with claim.open("x") as f:
                json.dump({"case":str(case),"raw_episode":str(path),"checkpoint_sha256":checkpoint_hash},f)
        except FileExistsError:
            return
        render_episode(path,args.first_video_dir/"first_student_success_1080p.mp4")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--actor-python",type=Path,default=Path(".conda/envs/arm-and-dog/bin/python"))
    p.add_argument("--branch",required=True)
    p.add_argument("--scene",required=True)
    p.add_argument("--side",choices=["pull","push"],required=True)
    p.add_argument("--goal",type=int,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--feedback-dir",type=Path)
    p.add_argument("--first-video-dir",type=Path)
    evaluate(p.parse_args())
