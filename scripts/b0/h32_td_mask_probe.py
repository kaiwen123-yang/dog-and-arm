"""Same real replay, RNG, starting critic and minibatches; change only the real TD terminal mask."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from learning.b0.contact_training import ContactRun
from scripts.b0.h32_real_critic import fit_real_critic
from scripts.b0.h32_recovery import gradient_audit,write


def main(a):
    device="cuda:0"
    initial=torch.load(a.anchor,weights_only=False,map_location="cpu")
    after=torch.load(a.replay,weights_only=False,map_location=device)
    cfg=after["cfg"]
    paths=[Path(cfg["reference_directory"])/n for n in cfg["references"]]
    run=ContactRun(cfg,paths,paths,initial,after,device)
    run.replay.chunks.extend(after["replay"])
    np.random.seed(377)
    torch.manual_seed(377)
    starts=run.policy.wm_env.sample_initial_states()
    out=Path("results/b0")/a.run
    out.mkdir(exist_ok=False)
    optimizer_start=[deepcopy(o.state_dict()) for o in run.policy.critic_optimizers]
    rows=[]
    for mask in (False,True):
        run.critic.load_state_dict(initial["critic"])
        for opt,s in zip(run.policy.critic_optimizers,optimizer_start):
            opt.load_state_dict(deepcopy(s))
        torch.manual_seed(618)
        m=fit_real_critic(run,mask)
        torch.manual_seed(621)
        tag="terminal" if mask else "continue"
        gradient_audit(run,starts,out/(tag+".json"))
        rows.append(dict(mask=mask,**m))
    write(out/"sources.json",dict(u0_actor_critic=str(a.anchor),exact_post_wm_and_replay=str(a.replay),
        recipe="Two single-variable offline critic fits before a hypothetical next Actor step. Same eight balanced 64-sample batches, optimizers and seed. Same 64 replay starts and imagined sensor RNG when probing subsequent H32 gradients. No new Actor update or physical task claimed.",fits=rows))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--anchor",type=Path,required=True)
    p.add_argument("--replay",type=Path,required=True)
    p.add_argument("--run",required=True)
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", ".."):
        p.error("Fresh output directory required")
    main(a)
