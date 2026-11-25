"""Replay the original held action from a saved student snapshot and compare causal inputs."""
import argparse
import json
from pathlib import Path
import pickle

import mujoco as mj
import numpy as np

from scripts.multimodal.collect import instruction
from scripts.multimodal.mm02_physics import (PolicyPipe,TORCH,emit,init_resources,restore_physics)


def check(path):
    with path.open("rb") as f:
        anchor=pickle.load(f)
    parent=anchor["parent"]
    episode=Path(anchor["parent_path"])
    def at(field,t):
        return np.load(episode/(field+".npy"),mmap_mode="r")[t]
    tick=anchor["tick"]
    scene,cfg,m,frame0,teacher,judge=init_resources(parent)
    teacher.restore(anchor["teacher"])
    judge.__dict__.update(anchor["judge"])
    d=restore_physics(m,anchor["physics"])
    a=teacher.mapping
    pipe=PolicyPipe(TORCH,parent["checkpoint"])
    try:
        pipe.reset(instruction(parent["side"],parent["goal"]),tick,anchor["prefix"])
        raw=pipe.step(at("proprio",tick),anchor["previous"],anchor["image"],anchor["image_t"],float(d.time))
    finally:
        pipe.close()
    # Reconstruct the original applied request at the current decision boundary, full precision.
    label=teacher.before(d)
    issued=label.raw if at("execution_source",tick) else raw
    cmd=(a.offset+a.scale*np.clip(issued,-1.,1.))*a.finger_factor
    ctrl=[]
    for sub in range(int(at("substeps",tick))):
        if sub:
            teacher.before(d)
        q,v=d.qpos.copy(),d.qvel.copy()
        d.ctrl[a.actuator_ids]=cmd+d.qfrc_bias[a.dof]*a.bias_gain
        mj.mj_step(m,d)
        contact=judge.observe(d,q,v)
        teacher.after(d,contact)
        ctrl.append(d.ctrl[a.actuator_ids].astype(np.float32))
    def diff(x,y):
        return float(np.max(np.abs(x-y)))
    return dict(parent=parent["id"],anchor_tick=tick,scene=scene["id"],source=int(at("execution_source",tick)),
                snapshot=str(path),physical_substeps=len(ctrl),image_age_s=float(at("t",tick)-anchor["image_t"]),
                student_raw_max_error=diff(raw.astype(np.float32),at("student_action_raw",tick)),
                expert_raw_max_error=diff(label.raw.astype(np.float32),at("expert_action_raw",tick)),
                ctrl_max_error=diff(np.array(ctrl),at("applied_ctrl",tick)[:len(ctrl)]),
                successor_qpos_max_error=diff(d.qpos,at("qpos",tick+1)),
                successor_qvel_max_error=diff(d.qvel,at("qvel",tick+1)))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("run",type=Path)
    args=p.parse_args()
    dest=args.run/"restore_probes.json"
    if not dest.exists():
        rows=[]
        for mode in ("pure","mixed"):
            candidates=sorted((args.run/"round1/collection").glob(f"*_{mode}/candidates.json"))
            options=[a for f in candidates for a in json.loads(f.read_text()) if a["tick"]%5!=0]
            if mode=="mixed":
                options=[a for a in options if np.load(Path(a["path"]).parent.parent/"episode"/"execution_source.npy",
                                                     mmap_mode="r")[a["tick"]]==0]
            if not options:
                raise ValueError("No real off-exposure student anchor in the registered pool")
            rows.append(check(Path(options[len(options)//2]["path"])))
        emit(dest,rows)
        print(json.dumps(rows),flush=True)
