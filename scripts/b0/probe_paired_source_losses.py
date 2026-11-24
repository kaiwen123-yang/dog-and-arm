"""Recheck each source at the initial/final paired temporal WMs on saved training indices.

These extra original-loss and gradient evaluations never execute an optimizer update.
"""
import json
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from supermimic.learners.wm_learner import WorldModelLearner

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg
from learning.b0.physics import make_model
from scripts.b0.score_temporal_wm import OUT, load_wm
from scripts.b0.train_temporal_pair import OUT as ROUND, RAW, build_pool, replay_batch


def score(learner,td):
    rep=learner.representation
    states,actions=td["state"],td["action"]
    true_r=rep.represent(states)
    true_a=rep.extract_aux_state(states)
    pred,aux=learner._rollout(true_r[:,0],actions,true_a[:,0],td["sim_ctx"][:,0])
    loss,group_mses=learner._compute_losses(pred,aux,true_r[:,1:],true_a[:,1:])
    grads=torch.autograd.grad(loss,tuple(learner.dynamics.parameters()))
    dt,rr,aa,xx=(v.detach() for v in (pred,aux,true_r[:,1:],true_a[:,1:]))
    err_by_t=[float(learner._compute_losses(dt[:,t:t+1],rr[:,t:t+1],aa[:,t:t+1],xx[:,t:t+1])[0])
              for t in range(dt.shape[1])]
    if not np.allclose(loss.detach().cpu(),np.mean(err_by_t),rtol=1e-5):
        raise ValueError("Original WM loss differs from the mean of per-boundary original losses")
    blocks=rep.loss_blocks(pred,aux)
    den=sum(v.shape[-1] for v in blocks.values())
    groups={k:float(m.detach())*learner.loss_group_weights[k]*v.shape[-1]/den for (k,v),m in zip(blocks.items(),group_mses,strict=True)}
    return dict(loss=float(loss.detach()),loss_per_20ms_boundary=err_by_t,group_contributions=groups,
        parameter_grad_l2=float(sum(g.square().sum() for g in grads).sqrt()))


def main():
    device="cuda:0"
    model=make_model()
    rep=ContactRepresentation(model,device)
    pool=build_pool(model,rep)
    ids=np.load(ROUND/"paired_indices.npz")
    names=json.loads((ROUND/"paired_sources.json").read_text())["names"]
    batches={}
    for h,k in [(1,0),(7,2)]:
        src=ids["source"][k]
        batch=replay_batch(pool,names,src,ids["start"][k],h)
        for i,label in enumerate(names):
            batches[h,k,label]=batch[torch.as_tensor(src==i,device=device)]
    result=[]
    for arm in ["C20","T2"]:
        for node in [0,1000]:
            dyn,_=load_wm(RAW/arm/f"wm_{node:06}.pt",model,rep,device)
            learner=WorldModelLearner(dyn,rep,ContactWorldModelCfg(batch_size=256),device)
            for (h,k,source),td in batches.items():
                result.append(dict(arm=arm,node=node,source=source,h=h,registered_batch_zero_based=k,windows=len(td),
                                   **score(learner,td)))
    dst=OUT/"paired_source_loss.json"
    dst.write_text(json.dumps(dict(samples="First H1 and first H7 of actual paired initialization-registered minibatches; identical real windows at all four evaluations. One batch per horizon, selected by position prior to inspecting losses.",
        endpoint_definition="All H7 coarse boundaries and original weighted channel mean. Split-restricted train windows. No update, no altered solver/data/gradient targets.",
        interpret="Finite matched-batch measures and individual per-source gradient norms do not isolate the causal share of each source.",
        data_indices=str(ROUND/"paired_indices.npz"),rows=result,extra_diagnostic_gradients=32,optimizer_updates=0),indent=2,allow_nan=False)+"\n")
    for r in result:
        print(r["arm"],r["node"],r["source"],r["h"],f'{r["loss"]:.5g}',f'{r["parameter_grad_l2"]:.5g}')


if __name__=="__main__":
    main()
