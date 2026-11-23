"""Probe the original physical-action prior on a shared real replay batch at u0, u1 and u5."""
import argparse
import json
import os
from pathlib import Path
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from learning.b0.contact_training import ContactRun
from scripts.b0.h32_recovery import gradient_audit,write


def main(a):
    device="cuda:0"
    initial=torch.load(a.anchor,weights_only=False,map_location="cpu")
    cfg=dict(initial["cfg"],worlds=64,cohort_steps=40,actor_batch=64,wm_batch=64,reference_directory=str(a.references))
    paths=[a.references/name for name in cfg["references"]]
    run=ContactRun(cfg,paths,paths,initial,initial,device)
    replay=torch.load(a.replay,weights_only=False,map_location=device)
    run.replay.chunks.extend(replay["replay"])
    np.random.seed(729)
    torch.manual_seed(729)
    starts=run.policy.wm_env.sample_initial_states()
    rng=torch.cuda.get_rng_state()
    out=Path("results/b0")/a.run
    out.mkdir(exist_ok=False)
    write(out/"sources.json",dict(anchors=[str(p) for p in a.checkpoints],prior=str(a.anchor),replay=str(a.replay),weight=cfg["physical_action_prior"],
        probe="Same real batch and sensor RNG for every package. Evaluate its own WM and terminal critic, and its gradient under the historical 0.02 physical action prior anchored to u0, without optimizing."))
    for i,path in enumerate(a.checkpoints):
        state=torch.load(path,weights_only=False,map_location="cpu")
        for key in ("actor","dyn","critic"):
            getattr(run,key).load_state_dict(state[key])
        torch.cuda.set_rng_state(rng)
        gradient_audit(run,starts,out/f"gradient_{i}.json")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--anchor",type=Path,required=True)
    p.add_argument("--references",type=Path,default=Path("results/raw_large/b0/full_warp_hold_park_r1"))
    p.add_argument("--replay",type=Path,required=True)
    p.add_argument("--checkpoints",type=Path,nargs="+",required=True)
    p.add_argument("--run",required=True)
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("",".",".."):
        p.error("Fresh output directory required")
    main(a)
