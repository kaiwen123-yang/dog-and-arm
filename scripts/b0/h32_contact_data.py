"""Collect independent current-policy Warp cohorts and retain genuine 32-step windows."""
import argparse
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from learning.b0.contact_training import ContactRun
from scripts.b0.h32_recovery import write


def main(a):
    anchor=torch.load(a.anchor,map_location="cpu",weights_only=False)
    cfg=dict(anchor["cfg"],cohort_steps=40,worlds=64,actor_batch=64,wm_batch=64,reference_directory=str(a.references))
    cfg.pop("physical_action_prior",None)
    paths=[a.references/x for x in cfg["references"]]
    run=ContactRun(cfg,paths,paths,anchor,anchor,"cuda:0")
    out=Path("results/b0")/a.run
    raw=Path("results/raw_large/b0")/a.run
    out.mkdir(exist_ok=False)
    raw.mkdir(exist_ok=False)
    folds=[("train",61300+i) for i in range(8)]+[("calibration",61400+i) for i in range(2)]+[("validation",61500+i) for i in range(3)]
    write(out/"registration.json",dict(anchor=str(a.anchor),reference_directory=str(a.references),
          allocation=folds,worlds=64,steps=40,noise=cfg["collection_noise"],
          design="All lanes in one fresh cohort belong to the listed split; failures end valid replay after the true 20ms successor. First ten held targets reconstruct the RSI. No held-out task cases."))
    results=[]
    for split,seed in folds:
        np.random.seed(seed)
        torch.manual_seed(seed)
        group=f"{split}_{seed}"
        d=raw/group
        data=run.collect(d)
        # Online collect updates WM input statistics; the frozen behavior Actor and physical data are unaffected.
        data.update(split=split,group=group,seed=seed,path=str(d))
        results.append(data)
    write(out/"cohorts.json",results)
    print(f"{len(results)} cohorts; {sum(x['valid_transitions'] for x in results)} real transitions",flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",required=True)
    p.add_argument("--references",type=Path,default=Path("results/raw_large/b0/full_warp_hold_park_r1"))
    p.add_argument("--anchor",type=Path,default=Path("results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt"))
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", ".."):
        p.error("Select a fresh run directory")
    main(a)
