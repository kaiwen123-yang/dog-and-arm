from __future__ import annotations

"""Replay the actual ten minibatches, with fixed physical probes and parameter-source attribution."""

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

import numpy as np
import torch
from supermimic.learners import wm_learner

from scripts.b0.dynamics_h32_pilot import (
    DEVICE, OUT as OLD, RAW as ORIGINAL, atomic_torch, build, load_common, optimizer_steps, write,
)
from scripts.b0.dynamics_h32_probe import assert_draws, observed_draws
from scripts.b0.dynamics_h32_source_vjp import per_window_loss
from scripts.b0.score_temporal_wm import csv_file, score_long, validation_episodes

OUT = Path("results/b0/standard_joint_contact_20261124/replay")
RAW = Path("results/raw_large/b0/joint_contact_20261124/replay")


def materialize(run, arm):
    batches, groups = {}, {}
    with observed_draws(run) as draws:
        for i, h in enumerate([7] * 8 + [1] * 2):
            batch, online_count = run.registered_wm.draw(h, i, run.b, run.replay)
            batches[i] = batch.select("state", "action", "sim_ctx").clone()
            counts = run.registered_wm.rows[-1]["sources"]
            groups[i] = [(k, v["samples"]) for k, v in counts.items()]
            if sum(v for _, v in groups[i]) != len(batch) or online_count != 192:
                raise ValueError("Changed joint minibatch shares")
    with np.load(OLD / "h32" / arm / "u1_actual_wm_draws.npz") as archive:
        assert_draws(draws, dict(archive))
    return batches, groups, draws


def pack(run):
    return dict(dyn=run.dyn.state_dict(), wm_optimizers=[o.state_dict() for o in run.learners[7].optimizers],
                optimizer_steps=optimizer_steps(run), cfg=run.cfg)


def tree_max(a, b):
    if isinstance(a, dict):
        assert set(a) == set(b)
        return max((tree_max(a[k], b[k]) for k in a), default=0.)
    if isinstance(a, (list, tuple)):
        assert len(a) == len(b)
        return max((tree_max(x, y) for x,y in zip(a,b,strict=True)), default=0.)
    if torch.is_tensor(a):
        return float((a.double().cpu()-b.double().cpu()).abs().max()) if a.numel() else 0.
    assert a == b
    return 0.


def replay(run, name, arm, batches, groups, draws):
    folder, raw = OUT/name, RAW/name
    folder.mkdir(exist_ok=True, parents=True)
    raw.mkdir(exist_ok=True, parents=True)
    if (raw/"step00.pt").exists():
        raise FileExistsError(raw)
    np.savez_compressed(folder/"ordered_indices.npz", **draws)
    atomic_torch(dict(batches={i:{key:td[key].cpu() for key in td.keys()} for i,td in batches.items()},
                      groups=groups),raw/"materialized.pt")
    order=list(range(10)) if name!="experiment_h1_first" else [8,9,*range(8)]
    write(folder/"registration.json",dict(historical_branch=arm, chronological_original_batch_indices=order,
          group_counts=groups, original_draw_archive=str(OLD/"h32"/arm/"u1_actual_wm_draws.npz"),
          all_index_groups_identical=len(draws), matmul_precision=torch.get_float32_matmul_precision(),
          drift_rule="first post-update fixed four-way validation H32 score above max(1.25 * own E0, own E0 + 2 mm)",
          updates=10, actor=0, critic=0, optimizer_initialization="archive common empty Muon and Adam",
          parameter_gradient="all five semantic sources, original sample shares, same complete parameter vector; norm before clipping, gradient descent projection onto actual step"))
    atomic_torch(pack(run),raw/"step00.pt")
    chron=[]
    original_step=wm_learner._optimize_step
    params=list(run.dyn.parameters())

    def measured(opts, loss, ps, max_norm):
        i=len(chron)
        before=[p.detach().clone() for p in params]
        norm=original_step(opts,loss,ps,max_norm=max_norm)
        delta=torch.cat([(p.detach()-old).flatten() for p,old in zip(params,before,strict=True)])
        counts=optimizer_steps(run)
        if counts!={"wm":i+1,"actor":0,"critic":0} or not torch.isfinite(delta).all() or not torch.isfinite(norm):
            raise ValueError("Nonfinite update or changed optimizer counts")
        chron.append(dict(step=i+1,original_batch=order[i],horizon=batches[order[i]].shape[1]-1,
                     original_loss=float(loss.detach()),preclip_norm=float(norm),clip_threshold=max_norm,
                     clipped=bool(norm>max_norm),parameter_delta_l2=float(delta.double().norm()),
                     parameter_delta_max=float(delta.abs().max()),**counts))
        atomic_torch(pack(run),raw/f"step{i+1:02}.pt")
        return norm

    with patch.object(wm_learner,"_optimize_step",measured):
        for h in ((1,7) if name=="experiment_h1_first" else (7,1)):
            run.learners[h].update([batches[i] for i in order if batches[i].shape[1]-1==h])
    torch.cuda.synchronize()
    csv_file(folder/"updates.csv",chron)
    ref=torch.load(ORIGINAL/"h32"/arm/"u1_after_wm_before_actor.pt",map_location="cpu",weights_only=False)
    stats=dict(dyn_max_abs=tree_max(run.dyn.state_dict(),ref["dyn"]),
               wm_optimizer_max_abs=tree_max([o.state_dict() for o in run.learners[7].optimizers],ref["wm_optimizers"]),
               expected_identical=name!="experiment_h1_first", repeat="historically recorded independent original execution")
    write(folder/"reproduction.json",stats)
    if stats["expected_identical"] and max(stats["dyn_max_abs"],stats["wm_optimizer_max_abs"])!=0:
        raise ArithmeticError(f"Unexplained nonidentical original replay: {stats}")
    print(name, "finished actual updates",stats,flush=True)


@torch.no_grad()
def physical_probe(run, episodes, raw, folder, signed_only=False):
    fixed={}
    for key,eps in episodes.items():
        for side in ("pull","push"):
            for h in (1,7):
                samples=[]
                for ep in eps:
                    if ep.side==side:
                        valid=ep.starts(h)
                        ids=valid[ep.modes[valid]=="two_finger"]
                        samples.extend((ep,int(t)) for t in ids)
                if not samples:
                    raise ValueError((key,side,h))
                picks=np.random.default_rng(621).choice(len(samples),min(32,len(samples)),replace=False)
                epsel=[samples[i] for i in picks]
                fixed[key,side,h]=dict(state=torch.stack([ep.state[t:t+h+1] for ep,t in epsel]),
                    action=torch.stack([ep.action[t:t+h] for ep,t in epsel]),ctx=torch.stack([ep.context for ep,t in epsel]),
                    ids=[(ep.group,t) for ep,t in epsel])
    write(folder/"small_probe_windows.json",{f"{k}/{s}/H{h}":td["ids"] for (k,s,h),td in fixed.items()})
    rows, full_scores=[],[]
    signed={}
    first=None
    reference=None
    for step in range(11):
        run.dyn.load_state_dict(torch.load(raw/f"step{step:02}.pt",map_location=DEVICE,weights_only=False)["dyn"])
        run.dyn.eval()
        for (source,side,h),td in fixed.items():
            state=td["state"][:,0]
            r=run.rep.represent(state)
            a=run.rep.extract_aux_state(state)
            for t in range(h):
                a,r=run.dyn(r,td["action"][:,t],a,td["ctx"])
                truth=td["state"][:,t+1]
                pred=run.rep.reconstruct_full_state(a,r)
                tcp=run.rep.tcp_pose(pred[:,:7],pred[:,7:31])[0]
                target=run.rep.tcp_pose(truth[:,:7],truth[:,7:31])[0]
                mixed=run.rep.tcp_pose(pred[:,:7],truth[:,7:31])[0]
                vals=dict(j2_q_error_rad=pred[:,24]-truth[:,24],j2_v_error_rad_s=pred[:,54]-truth[:,54],
                         tcp_error_mm=1000*(tcp-target).norm(dim=1),base_component_mm=1000*(mixed-target).norm(dim=1),
                         joint_component_mm=1000*(tcp-mixed).norm(dim=1))
                for metric,value in vals.items():
                    key=f"{source}_{side}_h{h}_t{t+1}_{metric}"
                    signed.setdefault(key,[]).append(value.cpu().numpy())
                rows.append(dict(step=step,source=source,side=side,h=h,transition=t+1,samples=len(pred),
                                 **{k+"_mean":float(v.mean()) for k,v in vals.items()},
                                 **{k+"_rmse":float(v.square().mean().sqrt()) for k,v in vals.items()}))
        if signed_only:
            continue
        scores=[]
        for source,eps in episodes.items():
            val=score_long(source,eps,run.model,run.rep,run.dyn,DEVICE)
            scores.extend(dict(step=step,**r) for r in val if r["mode"]=="two_finger" and r["metric"]=="tcp_mm")
        four={(r["source"],r["side"]):r["p95"] for r in scores if r["h"]==32}
        if len(four)!=4 or not all(np.isfinite(v) for v in four.values()):
            raise ValueError(four)
        if reference is None:
            reference=four
        if first is None and any(four[key]>max(1.25*v,v+2.) for key,v in reference.items()):
            first=step
        full_scores.extend(scores)
        print(f"validation {folder.name} {step}",four,flush=True)
    np.savez_compressed(raw/"per_window_physical_probes.npz",**{key:np.stack(v) for key,v in signed.items()})
    if signed_only:
        return None
    csv_file(folder/"fixed_physical_probes.csv",rows)
    csv_file(folder/"fixed_long.csv",full_scores)
    write(folder/"drift.json",dict(first_drift=first,score="two_finger/TCP P95, fixed original windows",per_step_all_four=True))
    return first


def gradient_coordinates(run, batches, groups, raw, folder, step):
    state=torch.load(raw/f"step{step:02}.pt",map_location=DEVICE,weights_only=False)
    run.dyn.load_state_dict(state["dyn"])
    run.dyn.requires_grad_(True)
    run.dyn.train()
    named=dict(run.dyn.named_parameters())
    bases=[p for p in named.values()]
    direction={}
    for k in {step-1,step+1}&set(range(11)):
        peer=torch.load(raw/f"step{k:02}.pt",map_location=DEVICE,weights_only=False)["dyn"]
        direction["prev_to_node" if k<step else "node_to_next"]=torch.cat([
            ((state["dyn"][n]-peer[n]) if k<step else (peer[n]-state["dyn"][n])).reshape(-1) for n in named]).double()
    weighted={}
    draws=[]
    for i,td in batches.items():
        h=td.shape[1]-1
        learner=run.learners[h]
        rep=run.rep.represent(td["state"])
        aux=run.rep.extract_aux_state(td["state"])
        r,a=learner._rollout(rep[:,0],td["action"],aux[:,0],td["sim_ctx"][:,0])
        per,_=per_window_loss(learner,(r,a),(rep[:,1:],aux[:,1:]))
        total=learner._compute_losses(r,a,rep[:,1:],aux[:,1:])[0]
        torch.testing.assert_close(per.mean(),total,atol=1e-6,rtol=1e-5)
        full=torch.cat([v.detach().reshape(-1) for v in torch.autograd.grad(total,bases,retain_graph=True)]).double()
        reconstructed=torch.zeros_like(full)
        start=0
        for idx,(source,n) in enumerate(groups[i]):
            objective=per[start:start+n].sum()/len(td)
            grad=torch.autograd.grad(objective,bases,retain_graph=idx<len(groups[i])-1)
            vec=torch.cat([p.detach().reshape(-1) for p in grad]).double()
            reconstructed+=vec
            for which in ("all",f"H{h}"):
                dest=weighted.setdefault(which,{})
                if source in dest:
                    dest[source]+=vec/10
                else:
                    dest[source]=vec/10
            draws.append(dict(original_batch=i,h=h,source=source,samples=n,
                 weighted_source_l2=float(vec.norm()),source_mean_gradient_l2=float(vec.norm()*len(td)/n),
                 source_normalized_loss=float(per[start:start+n].mean().detach()),batch_gradient_norm=float(full.norm())))
            start+=n
        resid=(reconstructed-full).norm()/full.norm().clamp(min=1e-30)
        for row in draws[-len(groups[i]):]:
            row["relative_sum_residual"]=float(resid)
    pairs, projections=[],[]
    eps=1e-30
    for which, vectors in weighted.items():
        for source,g in vectors.items():
            for other,j in vectors.items():
                dot=float(g@j)
                cos=float(torch.clamp((g@j)/(g.norm()*j.norm()).clamp(min=eps),-1,1))
                pairs.append(dict(group=which,source=source,other=other,norm=float(g.norm()),weighted_dot=dot,
                                cosine=cos,angle_degrees=float(np.rad2deg(np.arccos(cos)))))
            for name,d in direction.items():
                dn=float(d.norm())
                proj=float(g@d)/dn if dn else None
                projections.append(dict(group=which,source=source,direction=name,actual_step_l2=dn,
                        weighted_gradient_dot_step=float(g@d),gradient_on_unit_step=proj,
                        descent_alignment=None if not dn else -proj/float(g.norm().clamp(min=eps))))
    csv_file(folder/f"source_gradient_batches_step{step:02}.csv",draws)
    csv_file(folder/f"source_gradient_pairs_step{step:02}.csv",pairs)
    csv_file(folder/f"source_gradient_projections_step{step:02}.csv",projections)
    write(folder/f"source_gradient_info_step{step:02}.json",dict(
        parameter_order=[dict(name=k,shape=list(v.shape),elements=v.numel()) for k,v in named.items()],
        optimizer_groups=[[k for k,p in named.items() if any(p is t for g in opt.param_groups for t in g["params"])]
                          for opt in run.learners[7].optimizers],
        loss_weights=run.learners[7].loss_group_weights, counts_by_original_batch=groups,
        block_scaling="Each source gradient is the sum over its samples / 256, averaged over all 10 batches. H1,H7 columns also use /10 so H1 + H7 = all. Missing source in a horizon has no samples.",
        absent_sources={scope:sorted(set(weighted["all"])-set(v)) for scope,v in weighted.items()},
        residual="Per-batch relative L2 of sum of separately differentiated components vs direct original full gradient; reduced-precision FP32 GEMM may differ by association."))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("name",choices=["control","experiment","experiment_h1_first"])
    mode=ap.add_mutually_exclusive_group()
    mode.add_argument("--analyze-only",action="store_true")
    mode.add_argument("--signed-only",action="store_true",help="Export signed window trajectories from existing snapshots without any updates")
    args=ap.parse_args()
    name=args.name
    arm=name.split("_")[0]
    run=build(arm)
    load_common(run)
    batches,groups,draws=materialize(run,arm)
    if not (args.analyze_only or args.signed_only):
        replay(run,name,arm,batches,groups,draws)
    folder,raw=OUT/name,RAW/name
    if not (folder/"reproduction.json").exists():
        raise ValueError("Need archived replay first")
    if name in ("control","experiment"):
        exact=json.loads((folder/"reproduction.json").read_text())
        if max(exact["dyn_max_abs"],exact["wm_optimizer_max_abs"])!=0:
            raise ArithmeticError("Replay did not reproduce")
    torch.set_float32_matmul_precision("highest")
    sources=run.cfg["wm_data_recipe"]["sources"]
    episodes={k:validation_episodes(str(Path(sources[k]["directory"]).resolve()),run.model,run.rep,DEVICE)
              for k in ("grip","multimode")}
    first=physical_probe(run,episodes,raw,folder,args.signed_only)
    if args.signed_only:
        return
    torch.set_float32_matmul_precision("high")
    for step in sorted({0,10,first}-{None}):
        gradient_coordinates(run,batches,groups,raw,folder,step)
    print(name,"complete",flush=True)


if __name__=="__main__":
    main()
