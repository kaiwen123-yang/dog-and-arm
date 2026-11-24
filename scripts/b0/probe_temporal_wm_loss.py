"""Measure the old ordinary u1 WM parameter displacement and fixed-draw original losses.

Uses matched diagnostic windows from the historical training sources; no optimizer step.
"""
import json
import os
from collections import Counter
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
import yaml
from supermimic.learners.wm_learner import WorldModelLearner
from tensordict import TensorDict

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg, contact_context, contact_state
from learning.b0.contact_sources import RegisteredWM, native_episodes
from learning.b0.physics import make_model
from scripts.b0.score_temporal_wm import BASE, OUT, load_wm


def online_batch(model, h, device):
    directory=Path("results/raw_large/b0/response_s0_v1")
    raw=directory/"cohort_000001"
    compact=np.load(directory/"lanes_000001.npz")
    def read(k):
        return np.load(raw/(k+".npy"),mmap_mode="r")
    valid=compact["valid"]
    np.testing.assert_array_equal(valid,read("valid"))
    legal=np.lib.stride_tricks.sliding_window_view(valid,h,axis=0).all(-1)
    if h>1:
        no_terminal=((compact["fail"]==0)&~compact["clip_end"])[:-1]
        legal &= np.lib.stride_tricks.sliding_window_view(no_terminal,h-1,axis=0).all(-1)
        legal &= compact["episode"][:len(legal)]==compact["episode"][h-1:]
    rng=np.random.default_rng(2400+h)
    lanes=rng.choice(np.flatnonzero(legal.any(0)),256)
    times=np.array([rng.choice(np.flatnonzero(legal[:,b])) for b in lanes])
    ts, bs=times[:,None]+np.arange(h)[None,:],lanes[:,None]
    def ten(x):
        return torch.as_tensor(np.array(x),device=device)
    q,v,q1,v1=[read(k)[ts,bs] for k in ("qpos","qvel","next_qpos","next_qvel")]
    np.testing.assert_array_equal(q[:,1:],q1[:,:-1]); np.testing.assert_array_equal(v[:,1:],v1[:,:-1])
    st=contact_state(ten(np.concatenate([q,q1[:,-1:]],1)),ten(np.concatenate([v,v1[:,-1:]],1)))
    action=ten(read("clipped")[ts,bs])
    sides=compact["side"][times,lanes]
    ctx=torch.stack([contact_context(model,s,device) for s in ("pull","push")])[ten(sides)]
    fp=compact["finger_min"][times,lanes]
    counts=dict(side=Counter("push" if s else "pull" for s in sides),initial_dual=int((fp>.01).all(-1).sum()),
                initial_open_hold=int(np.isin(compact["phase"][times,lanes],[5,6]).sum()))
    return TensorDict(dict(state=st,action=torch.cat((action,action[:,-1:]),1),sim_ctx=ctx[:,None].expand(-1,h+1,-1)),
                      batch_size=st.shape[:2]),counts


def loss_row(learner,td,displacements):
    rep=learner.representation
    xs,ac,ctx=td["state"],td["action"],td["sim_ctx"][:,0]
    true_r=rep.represent(xs)
    true_a=rep.extract_aux_state(xs)
    pf,pa=learner._rollout(true_r[:,0],ac,true_a[:,0],ctx)
    loss,groups=learner._compute_losses(pf,pa,true_r[:,1:],true_a[:,1:])
    gradients=torch.autograd.grad(loss,tuple(learner.dynamics.parameters()))
    grad_norm=sum(g.float().square().sum() for g in gradients).sqrt()
    dot=sum((g.float()*d).sum() for g,d in zip(gradients,displacements,strict=True))
    rel=rep.loss_blocks(pf,pa)
    widths={k:t.shape[-1] for k,t in rel.items()}
    den=sum(widths.values())
    # Use loss_blocks order, same as _compute_losses; avoid relying on config mapping order.
    terms={k:float(m.detach())*learner.loss_group_weights[k]*widths[k]/den for k,m in zip(rel,groups,strict=True)}
    assert abs(sum(terms.values())-float(loss.detach()))<1e-4*max(1,float(loss.detach()))
    rn=learner.dynamics.state_normalizer(true_r[:,:-1]).abs().flatten()
    an=learner.dynamics.action_normalizer(learner.dynamics.proc(ac[:,:-1])).abs().flatten()
    return dict(original_weighted_loss=float(loss.detach()),group_contributions=terms,
        gradient_l2=float(grad_norm),grad_dot_actual_total_wm_delta=float(dot),state_abs_z_p99=float(torch.quantile(rn,.99)),
        state_abs_z_max=float(rn.max()),action_abs_z_p99=float(torch.quantile(an,.99)),action_abs_z_max=float(an.max()))


def main():
    device="cuda:0"
    model=make_model()
    rep=ContactRepresentation(model,device)
    run=BASE/"response_s0_v1"
    old,_=load_wm(run/"checkpoint_000000.pt",model,rep,device)
    new,_=load_wm(run/"checkpoint_000001.pt",model,rep,device)
    w0,_=load_wm(BASE/"response_wm_v1/wm_000000.pt",model,rep,device)
    assert all(torch.equal(x,w0.state_dict()[k]) for k,x in old.state_dict().items())
    b0=dict(old.named_buffers()); b1=dict(new.named_buffers())
    matches={k:torch.equal(x,b1[k]) for k,x in b0.items()}
    delta=[(q-p).detach() for p,q in zip(old.parameters(),new.parameters(),strict=True)]
    sizes={k:float(d.norm()) for (k,_),d in zip(old.named_parameters(),delta,strict=True)}
    recipe=yaml.safe_load(Path("config/b0/standard_response_v1.yaml").read_text())
    previous=json.loads((BASE/"lanes_wm_v1/config.json").read_text())
    native=native_episodes([Path(ep["path"]) for ep in previous["sources"] if ep["split"]=="train"],device)
    pool=RegisteredWM(recipe,model,rep,native,device)
    result=[]
    for h in (1,7):
        L=[WorldModelLearner(d,rep,ContactWorldModelCfg(batch_size=256,horizon=h+1),device) for d in (old,new)]
        for j,source in enumerate(("native","grip","multimode","response","online")):
            torch.manual_seed(112400+10*h+j)
            batch,meta=online_batch(model,h,device) if source=="online" else pool.pools[source,h].draw(256)
            losses=[loss_row(l,batch,delta) for l in L]
            result.append(dict(h=h,source=source,draw=meta,u0=losses[0],u1=losses[1]))
    train_draws=[json.loads(line) for line in (run/"wm_draws.jsonl").read_text().splitlines()[:10]]
    counts={h:{} for h in (1,7)}
    for d in train_draws:
        for source,values in d["sources"].items():
            dest=counts[d["h"]].setdefault(source,Counter())
            dest["all"]+=values["samples"]
            for key,n in values["side_phase_mode"].items():
                side,phase,mode=key.split("/")
                dest["open_hold"]+=n*(phase in ("open","hold"))
                dest["two_finger"]+=n*(mode=="two_finger")
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"historical_u1_loss.json").write_text(json.dumps(dict(u0_u1_run=str(run),initializer_tensor_equal=True,
        buffers_unchanged=matches,parameter_displacement_l2=sizes,actual_10_batch_counts=counts,
        reloaded_historical_train_inventory=pool.inventory,draws=result,
        interpretation="Each source/horizon uses one frozen, train-only, 256-window diagnostic draw, matched across u0/u1. These are not the original update's sampled row indices. Gradient projections are local in parameter space, not isolated causal effects. Historical online data and response have the pre-correction solver/cache identity; no data from this script enter training.",
        official_loss="sum over group (MSE*group width/total width/nominal_error^2), scored at every original 20 ms successor",
        parameter_updates=0,original_u1_order=[d["h"] for d in train_draws],grad_clip=1.0),indent=2)+"\n")


if __name__=="__main__":
    main()
