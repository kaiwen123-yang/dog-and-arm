"""Rescore measured boundary directions at the actual adaptation endpoint; no optimizer steps."""
import argparse
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import torch
from scripts.b0 import joint_physics_derivatives as boundary
from scripts.b0.joint_adapt import ck
from scripts.b0.dynamics_h32_pilot import read,write
from scripts.b0.joint_collection import OUT
from scripts.b0.score_temporal_wm import csv_file,load_wm

def run(n):
    folder=OUT/"adapt"/f"node_{n:06}"
    model,rep=boundary.model_and_rep(.00025)
    dyn,_=load_wm(boundary.WM,model,rep,boundary.DEVICE)
    restored=torch.load(ck(n),weights_only=False,map_location="cpu")
    assert restored["batches"]==n and restored["c"]==.50625
    dyn.load_state_dict(restored["dyn"])
    rows=[]
    for r in read(OUT/"physics/boundary_registration.json")["points"]:
        rows+=boundary.collect(model,rep,dyn,r["id"],r["identity"])
    csv_file(folder/"boundary_derivatives.csv",rows)
    evidence={}
    for split in ("train","validation"):
        valid=[r for r in rows if r["wm_sign_match"] is not None and r["split"]==split]
        evidence[split]=dict(matches=sum(r["wm_sign_match"] for r in valid),measured=len(valid))
    write(folder/"derivative_summary.json",dict(weights=str(ck(n)),original_physical_inputs=True,rows=len(rows),
        groups=evidence,extra_optimizer_steps=0,new_physical_intervals=0))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("node",type=int)
    run(p.parse_args().node)
