"""Retest an observed large H7 gradient at frozen +200, with no parameter update."""
import json
import os

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from supermimic.learners.wm_learner import WorldModelLearner

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg
from learning.b0.physics import make_model
from scripts.b0.score_temporal_wm import OUT, load_wm
from scripts.b0.train_temporal_pair import OUT as ROUND, RAW, build_pool, replay_batch


def length(ts):
    return float(sum(t.detach().double().square().sum() for t in ts).sqrt())


def boundary(learner, r, aux, ctx, actions, targets):
    pred,pa=learner._rollout(r,actions,aux,ctx)
    return learner._compute_losses(pred,pa,*targets)[0],torch.cat([pred,pa],-1)


def inputs(learner,batch,dtype):
    state=batch["state"].to(dtype)
    rep=learner.representation
    rs=rep.represent(state)
    return (rs[:,0].detach().requires_grad_(),state[:,0,:7].detach().requires_grad_(),
            batch["sim_ctx"][:,0].to(dtype),batch["action"].to(dtype),(rs[:,1:],state[:,1:,:7]))


def explicit(wm,r,aux,action,ctx,rep,ratio,dt):
    state=wm.state_normalizer(r)
    norm_action=wm.action_normalizer(wm.proc(action))
    raw=wm.mlp(torch.cat((state,norm_action,ctx),-1))
    # Dispatch the platform representation directly: a single ratio, then existing physical velocity units and hinge .1.
    pa,pr=ContactRepresentation.apply_prediction(rep,aux,r,raw*ratio,dt)
    return pa,pr,raw


def norm_blocks(aux,r):
    return dict(root_pose=length([aux]),root_rep=length([r[...,:10]]),joint_positions=length([r[...,10:34]]),
        joint_velocities=length([r[...,34:58]]),door=length([r[...,58:60]]),geometry=length([r[...,60:]]))


def trace(learner,xx,arm):
    r,a,c,acts,targets=xx
    wm=learner.dynamics
    inner=wm._apply_prediction.__self__
    ratio,n=(.1,10) if arm=="T2" else (1.,1)
    assert inner.dt==wm.dt and inner.substep_coeff==(1. if n==10 else .55)
    states=[(a,r)]
    rays=[]
    for j in range(7):
        for _ in range(n):
            a,r,y=explicit(wm,r,a,acts[:,j],c,inner,ratio,inner.dt)
            # Independent output ports: r already contains geometry computed from the same step's aux.
            # Identity copies prevent counting internal geometry paths twice in boundary cotangents.
            a,r=a.clone(),r.clone()
            states.append((a,r))
            rays.append(y)
    predicted=torch.stack([s[1] for s in states[n::n]],1)
    ax=torch.stack([s[0] for s in states[n::n]],1)
    loss=learner._compute_losses(predicted,ax,*targets)[0]
    final=learner._compute_losses(predicted[:,-1:],ax[:,-1:],targets[0][:,-1:],targets[1][:,-1:])[0]
    return loss,final,states,rays,torch.cat([predicted,ax],-1)


def owned_model(model,arm,dtype):
    rep=ContactRepresentation(model,"cuda:0").to(dtype=dtype)
    wm,_=load_wm(RAW/arm/"wm_000200.pt",model,rep,"cuda:0")
    wm=wm.to(dtype=dtype)
    wm._apply_prediction.__self__.to(dtype=dtype)
    return WorldModelLearner(wm,rep,ContactWorldModelCfg(batch_size=256,horizon=8),"cuda:0")


def source_gradient(learner,batch):
    xx=inputs(learner,batch,torch.float32)
    loss,output=boundary(learner,*xx)
    grad=torch.autograd.grad(loss,(*xx[:2],*learner.dynamics.parameters()))
    gin=torch.cat([g.detach() for g in grad[:2]],-1).double().norm(dim=1)
    return dict(full_batch_loss=float(loss.detach()),parameter_gradient_l2=length(grad[2:]),max_initial_adjoint=float(gin.max()),
                nonfinite=int((~output.isfinite()).sum())),gin


def local_decomposition(learner,xx,states,adjs,j,arm):
    wm=learner.dynamics
    inner=wm._apply_prediction.__self__
    n=10 if arm=="T2" else 1
    ratio=.1 if n==10 else 1.
    a,r=[t.detach().requires_grad_() for t in states[j]]
    c,action=xx[2],xx[3][:,j//n]
    dest_a,dest_r,raw=explicit(wm,r,a,action,c,inner,ratio,inner.dt)
    cot=[t.detach() for t in adjs[j+1]]
    norm=length(cot)
    unit=[t/norm for t in cot]
    def obj(pa,pr): return (pa*unit[0]).sum()+(pr*unit[1]).sum()
    total=torch.autograd.grad(obj(dest_a,dest_r),(a,r),retain_graph=True)
    fixed=ContactRepresentation.apply_prediction(inner,a,r,raw.detach()*ratio,inner.dt)
    direct=torch.autograd.grad(obj(*fixed),(a,r))
    via=[v-u for v,u in zip(total,direct)]
    blocks={}
    for label,cut in [("root_aux",None),("root_rep",(0,10)),("joints",(10,58)),("door",(58,60)),("geometry",(60,75))]:
        term=(dest_a*unit[0]).sum() if cut is None else (dest_r[...,slice(*cut)]*unit[1][...,slice(*cut)]).sum()
        blocks[label]=torch.autograd.grad(term,(a,r),allow_unused=True,retain_graph=True)
    summed=[sum(ts[i] for ts in blocks.values() if ts[i] is not None) for i in range(2)]
    # A local double-precision directional difference tests the actual observed cotangent orientation.
    direction=[v.detach()/length(total) for v in total]
    differ=[]
    with torch.no_grad():
        for eps in [1e-5,1e-6,1e-7]:
            scores=[]
            for sign in [-1,1]:
                a1=a+sign*eps*direction[0]
                r1=r+sign*eps*direction[1]
                pa,pr,_=explicit(wm,r1,a1,action,c,inner,ratio,inner.dt)
                scores.append(float(obj(pa,pr)))
            differ.append(dict(epsilon=eps,centered_directional_derivative=(scores[1]-scores[0])/(2*eps)))
    zn=wm.state_normalizer(r)
    wt=wm.mlp(torch.cat((zn,wm.action_normalizer(wm.proc(action)),c),-1))
    pa,pr=ContactRepresentation.apply_prediction(inner,a,r.detach(),wt*ratio,inner.dt)
    model_grad=torch.autograd.grad(obj(pa,pr),zn)[0]
    denom=wm.state_normalizer._std+wm.state_normalizer.eps
    return dict(inner_j=j+1,local_total_vjp_norm=length(total),fixed_increment_integrator_vjp=length(direct),
        state_dependent_network_vjp=length(via),network_vjp_before_inverse_std=float(model_grad.norm()),
        network_vjp_after_inverse_std=float((model_grad/denom).norm()),
        next_state_block_vjps={k:length([x for x in v if x is not None]) for k,v in blocks.items()},
        sum_block_residual_l2=length([u-v for u,v in zip(total,summed)]),
        centered_fp64_derivatives=differ,unit_cotangent="final-boundary loss adjoint at next inner step; norms unweighted in mixed native coordinates")


def inspect_one(model,arm,batch,dtype):
    l=owned_model(model,arm,dtype)
    xx=inputs(l,batch,dtype)
    y,out=boundary(l,*xx)
    ordinary=torch.autograd.grad(y,tuple(l.dynamics.parameters()))
    loss,last,states,rays,explicit_out=trace(l,xx,arm)
    recomputed=torch.autograd.grad(loss,tuple(l.dynamics.parameters()),retain_graph=True)
    gg=torch.autograd.grad(last,[v for pair in states for v in pair],retain_graph=True,allow_unused=True)
    adjs=[tuple((g if g is not None else torch.zeros_like(s)) for g,s in zip(gg[i*2:(i+1)*2],pair))
          for i,pair in enumerate(states)]
    result=dict(loss=float(y.detach()),endpoint_only_loss=float(last.detach()),ordinary_grad_l2=length(ordinary),
        manual_grad_l2=length(recomputed),max_abs_boundary_diff=float((out-explicit_out).detach().abs().max()),
        abs_loss_difference=float((y-loss).abs().detach()),relative_grad_difference=length([u-v for u,v in zip(ordinary,recomputed)])/max(1e-20,length(ordinary)),
        max_quaternion_norm_error=max(abs(float(v[0][0,3:7].detach().norm())-1) for v in states),
        dt=l.dynamics.dt,substep_coeff=l.dynamics._apply_prediction.__self__.substep_coeff,
        ten_step_loop=(arm=="T2"),decode_factor=(.1 if arm=="T2" else 1.))
    if dtype==torch.float64:
        adj=[length(pair) for pair in adjs]
        growth=np.divide(adj[:-1],adj[1:],out=np.zeros(len(adj)-1),where=np.asarray(adj[1:])>0)
        result["endpoint_only_adjoint_by_inner_step"]=[dict(inner=i,norm=v,components=norm_blocks(*adjs[i])) for i,v in enumerate(adj)]
        result["local_amplification"]=[local_decomposition(l,xx,states,adjs,int(i),arm) for i in np.argsort(-growth)[:3]]
    return result


def main():
    torch.set_float32_matmul_precision("highest")
    records=[json.loads(line) for line in (ROUND/"T2_training.jsonl").read_text().splitlines()]
    peak=max((r for r in records if r["h"]==7 and r["k"]<=200),key=lambda r:r["grad_norm"])
    k=peak["k"]-1
    ids=np.load(ROUND/"paired_indices.npz")
    names=json.loads((ROUND/"paired_sources.json").read_text())["names"]
    model=make_model()
    pool=build_pool(model,ContactRepresentation(model,"cuda:0"))
    batch=replay_batch(pool,names,ids["source"][k],ids["start"][k],7)
    observed_precision={}
    torch.set_float32_matmul_precision("high")
    for arm in ("C20","T2"):
        observed_precision[arm],_ = source_gradient(owned_model(model,arm,torch.float32),batch)
    torch.set_float32_matmul_precision("highest")
    whole={}
    for arm in ("C20","T2"):
        whole[arm],weights=source_gradient(owned_model(model,arm,torch.float32),batch)
    idx=int(weights.argmax())
    results={a:{str(t):inspect_one(model,a,batch[idx:idx+1],t) for t in (torch.float32,torch.float64)} for a in ("C20","T2")}
    identity=dict(source=names[int(ids["source"][k,idx])],absolute_start=int(ids["start"][k,idx]),batch_row=idx)
    report=dict(checkpoint=200,actual_training_step_of_selected_batch=k+1,observed_training_grads_at_step=peak["grad_norm"],
        draw_rule="Largest logged T2 H7 preclip norm through +200. At the frozen +200 endpoints choose the row with largest initial-state adjoint in the T2 batch; use identical row for C20. This is targeted diagnosis, not a prevalence estimate.",
        chosen=identity,whole_batch_frozen=whole,whole_batch_frozen_train_precision=observed_precision,selected_row=results,optimizer_updates=0,
        precision="FP32 highest-vs-FP64 diagnostic evaluation; historical training used high FP32 matmul precision",
        autograd="Pinned learner eager path versus explicit net→ratio→existing ContactRepresentation integration. Both paths retain all successors for original loss; terminal-boundary-only VJPs diagnose amplification without modifying the original objective.",
        interpretation="Magnitudes depend on mixed-coordinate units. Adjoint neighbor ratios are gains for the measured cotangent, not spectral norms; block and direct/network norms are not additive. Three local FP64 finite differences test the derivative at the actual trajectory states.")
    (OUT/"recurrence_u200.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("Observed batch and chosen row",k+1,identity,whole)
    for a,r in results.items():
        fp64=r["torch.float64"]
        print(a,fp64["ordinary_grad_l2"],fp64["relative_grad_difference"],[v["norm"] for v in fp64["endpoint_only_adjoint_by_inner_step"][::10 if a=="T2" else 1]])
        print("Local",fp64["local_amplification"][0])


if __name__=="__main__":
    main()
