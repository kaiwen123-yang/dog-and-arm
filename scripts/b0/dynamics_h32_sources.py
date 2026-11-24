"""Measure source losses on the same ten actual u1 joint WM minibatches at each pilot node."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")

import numpy as np
import torch
from scripts.b0.dynamics_h32_pilot import ARMS, OUT, RAW, build, load_common, write
from scripts.b0.dynamics_h32_probe import observed_draws, assert_draws
from scripts.b0.score_temporal_wm import csv_file


@torch.no_grad()
def main():
    run=build("control")
    load_common(run)
    fixed=[]
    with observed_draws(run) as draws:
        for i,h in enumerate([7]*8+[1]*2):
            td,_=run.registered_wm.draw(h,i,run.b,run.replay)
            rec=run.registered_wm.rows[-1]
            sizes=[(key,row["samples"]) for key,row in rec["sources"].items()]
            if sum(n for _,n in sizes)!=len(td):
                raise ValueError("Source counts do not cover the true joint minibatch")
            fixed.append((i,h,td,sizes))
    for arm in ARMS:
        with np.load(OUT/"h32"/arm/"draws_u01.npz") as z:
            real={k:z[k] for k in z.files if not k.startswith("actor_")}
            assert_draws(draws,real)
    rows=[]
    for arm in ARMS:
        for node in (0,1,10):
            c=RAW/"h32"/arm/f"checkpoint_{node:06}.pt"
            state=torch.load(c,weights_only=False,map_location="cpu")
            run.dyn.load_state_dict(state["dyn"])
            run.dyn.eval()
            for i,h,td,sizes in fixed:
                learner=run.learners[h]
                rs=run.rep.represent(td["state"])
                aux=run.rep.extract_aux_state(td["state"])
                pred,paux=learner._rollout(rs[:,0],td["action"],aux[:,0],td["sim_ctx"][:,0])
                offset=0
                for name,n in sizes:
                    sl=slice(offset,offset+n)
                    loss,groups=learner._compute_losses(pred[sl],paux[sl],rs[sl,1:],aux[sl,1:])
                    row=dict(arm=arm,node=node,source=name,index=i,horizon=h,samples=n,
                        original_weighted_loss=float(loss),**{k:float(x) for k,x in zip(learner.loss_group_weights,groups,strict=True)})
                    rows.append(row)
                    offset+=n
    folder=OUT/"h32"
    csv_file(folder/"matched_joint_source_losses.csv",rows)
    write(folder/"matched_joint_source_losses.json",dict(rows=len(rows),updates_added=0,
        source="Actual first ten joint WM minibatches. Verified all ordered physical replay and offline indices for both arms",
        frozen_inputs="same registered C20 identity, seed0 live replay and actual first update source ordering for all nodes",
        target="Original H1/H7 loss and raw group MSE by source at the six frozen branch checkpoints"))


if __name__=="__main__":
    main()
