"""Trace the frozen pilot WMs' physical sensitivities and source loss to registered train trajectories."""
import argparse
import json
from collections import defaultdict

import numpy as np
import torch
import yaml
from supermimic.learners.wm_learner import WorldModelLearner
from learning.b0.contact_model import ContactWorldModelCfg
from learning.b0.contact_warp import PHASES
from scripts.b0 import train_temporal_pair as prior
from scripts.b0.dynamics_c20_pair import (DEVICE, NAMES, OUT, RAW, build, digest, load_registration,
                                          model_and_rep, new_wm, open_draws, write)
from scripts.b0.score_temporal_wm import csv_file


def per_window_loss(learner, prediction, truth):
    estimate = learner.representation.loss_blocks(*prediction)
    target = learner.representation.loss_blocks(*truth)
    width = sum(x.shape[-1] for x in estimate.values())
    costs = {key:(val-target[key]).square().sum(-1).mean(-1)*learner.loss_group_weights[key]/width
             for key,val in estimate.items()}
    return torch.stack(list(costs.values())).sum(0),costs


def compare(learner, rep, dyn, td, source, epids, group):
    h = td["state"].shape[1]-1
    x = td["state"][:,0].detach().requires_grad_()
    a = td["action"].detach().requires_grad_()
    target = td["state"][:,1:]
    rs,aux = learner._rollout(rep.represent(x),a,x[:,:7],td["sim_ctx"][:,0])
    truth = rep.represent(target), target[...,:7]
    modeled = rs,aux
    direct = learner._compute_losses(*modeled,*truth)[0]
    per, costs = per_window_loss(learner,modeled,truth)
    torch.testing.assert_close(per.mean(),direct,rtol=1e-5,atol=1e-7)
    # The per-row sum recovers each window's own VJP without dividing by its source batch size.
    gx,ga = torch.autograd.grad(per.sum(),(x,a))
    dp = ga[:,:h]/dyn.action_scale
    full = rep.reconstruct_full_state(aux[:,-1],rs[:,-1])
    truth_end=target[:,-1]
    jq = (full[:,29]-full[:,30] - truth_end[:,29]+truth_end[:,30])*1000
    tcp = rep.tcp_pose(full[:,:7],full[:,7:31])[0]
    tcp_ref = rep.tcp_pose(truth_end[:,:7],truth_end[:,7:31])[0]
    # An exact positional decomposition along one declared FK evaluation order.
    mixed = rep.tcp_pose(full[:,:7],truth_end[:,7:31])[0]
    base_error = mixed-tcp_ref
    joint_error = tcp-mixed
    torch.testing.assert_close(base_error+joint_error,tcp-tcp_ref,rtol=1e-5,atol=1e-7)
    values = {"tcp_base_pose_component_mm":base_error.norm(dim=-1)*1000,
              "tcp_joint_position_component_mm":joint_error.norm(dim=-1)*1000,
              "j2_end_error_rad":full[:,24]-truth_end[:,24],"j4_end_error_rad":full[:,26]-truth_end[:,26],
              "j6_end_error_rad":full[:,28]-truth_end[:,28],
              "weighted_loss":per, "weighted_finger_q_loss":costs["finger_pos"],"weighted_finger_v_loss":costs["finger_vel"],
              "end_jaw_error_mm":jq,"end_tcp_error_mm":(tcp-tcp_ref).norm(dim=-1)*1000,
              "state_loss_vjp_l2":gx.double().norm(dim=-1), "all_cmd_loss_vjp_l2":dp.double().flatten(1).norm(dim=-1),
              "first_jaw_cmd_loss_vjp_per_m":dp[:,0,22], "first_j2_cmd_loss_vjp_per_rad":dp[:,0,17],
              "initial_finger_q_loss_vjp_l2":gx[:,29:31].double().norm(dim=-1),
              "initial_finger_speed_loss_vjp_l2":gx[:,59:61].double().norm(dim=-1)}
    data={k:v.detach().cpu().numpy() for k,v in values.items()}
    if not all(np.isfinite(v).all() for v in data.values()):
        raise FloatingPointError("Nonfinite at the matched offline source probe")
    trajectory = np.searchsorted(group.base,epids,side="right")-1
    records = []
    for i,epi in enumerate(trajectory):
        idx=int(epids[i])
        ep=group.episodes[epi]
        records.append(dict(source=source,episode=ep.group,side=ep.side,
                            physical_input_index=int(idx-group.base[epi]),absolute_source_index=idx,
                            phase=PHASES[group.phase[idx]],mode=str(group.mode[idx]),
                            **{k:float(v[i]) for k,v in data.items()}))
    summary = dict(source=source,h=h,samples=len(td),unique_inputs=len(np.unique(epids)),
                   unique_episodes=len(np.unique(trajectory)),original_weighted_loss=float(direct.detach()),
                   source_mean_loss_state_vjp_l2=float(gx.double().norm()/len(td)),
                   source_mean_loss_processed_command_vjp_l2=float(dp.double().norm()/len(td)),
                   mean_tcp_mm=float(data["end_tcp_error_mm"].mean()),
                   mean_base_tcp_component_mm=float(data["tcp_base_pose_component_mm"].mean()),
                   mean_joint_tcp_component_mm=float(data["tcp_joint_position_component_mm"].mean()),
                   mean_abs_j2_error_rad=float(abs(data["j2_end_error_rad"]).mean()),
                   mean_abs_j4_error_rad=float(abs(data["j4_end_error_rad"]).mean()),
                   mean_abs_j6_error_rad=float(abs(data["j6_end_error_rad"]).mean()),
                   mean_abs_opening_mm=float(np.abs(data["end_jaw_error_mm"]).mean()),
                   mean_finger_q_loss=float(data["weighted_finger_q_loss"].mean()),
                   mean_finger_v_loss=float(data["weighted_finger_v_loss"].mean()))
    return summary,records


def node(arm, step, pool, info, model, rep, src, ids):
    checkpoint = RAW/"h32"/arm/f"checkpoint_{step:06}.pt"
    weights = torch.load(checkpoint, map_location="cpu", weights_only=False)
    cfg=weights["cfg"]
    if cfg.get("physics_dt",.002) != info["physics_dt"]:
        raise ValueError("Unexpected numerical identity for the joint checkpoint")
    if "hidden" not in weights:
        weights["hidden"] = cfg["wm_hidden"]
    dyn = new_wm(model,rep,weights).eval()
    node_rows, trajectories, raw = [],[],[]
    for h,k in ((1,0),(7,2)):
        td=prior.replay_batch(pool,NAMES,src[k],ids[k],h)
        learner=WorldModelLearner(dyn,rep,ContactWorldModelCfg(batch_size=256,horizon=h+1),DEVICE)
        for i,name in enumerate(NAMES):
            mask=src[k]==i
            summary,samples=compare(learner,rep,dyn,td[torch.as_tensor(mask,device=DEVICE)],name,ids[k,mask],pool.pools[name,h])
            prefix=dict(arm=arm,u=step,h=h)
            totals=defaultdict(list)
            for row in samples:
                totals[row["episode"]].append(row)
                raw.append(prefix | row)
            records=[]
            for group,rr in totals.items():
                loss=sum(r["weighted_loss"] for r in rr)
                row=dict(**prefix,source=name,episode=group,side=rr[0]["side"],samples=len(rr),
                         unique_starts=len({r["physical_input_index"] for r in rr}),
                         weighted_loss_sum=loss,share_of_source_sample_loss=loss / max(1e-20,summary["original_weighted_loss"]*len(samples)),
                         state_vjp_sq_sum=sum(r["state_loss_vjp_l2"]**2 for r in rr),
                         command_vjp_sq_sum=sum(r["all_cmd_loss_vjp_l2"]**2 for r in rr),
                         max_abs_jaw_cmd_derivative=max(abs(r["first_jaw_cmd_loss_vjp_per_m"]) for r in rr))
                trajectories.append(row)
                records.append(row)
            summary["top_episode_by_loss"]=max(records,key=lambda r:r["weighted_loss_sum"])["episode"]
            summary["top_loss_share"]=max(r["share_of_source_sample_loss"] for r in records)
            node_rows.append(prefix | summary)
    base=OUT/"h32"/arm
    vals=RAW/"h32"/arm/f"fixed_offline_attribution_u{step:02}.csv"
    csv_file(vals,raw)
    csv_file(base/f"fixed_offline_trajectories_u{step:02}.csv",trajectories)
    write(base/f"fixed_offline_vjp_u{step:02}.json",dict(
          inputs="First registered four-source offline H1 and H7 draws, equal physical samples at every node; outside the separate actual joint-first-minibatch test. Train-only.",
          physical_vjp="VJP of original source mean loss in full initial physical state and all processed command coordinates. Values combine native units. Per-window and trajectory entries preserve actual draw multiplicities.",
          tcp_decomposition="True base/true joints -> predicted base/true joints -> predicted base/predicted joints. The two signed XYZ vectors sum to full TCP error; their reported Euclidean norms need not add.",
          estimated_effect="This is trajectory attribution for the measured loss and VJP on two saved training minibatches. It does not establish the source of closed-loop policy changes.",
          registered_indices=info["indices"], checkpoint=str(checkpoint), checkpoint_sha256=digest(checkpoint),
          training_updates=0, rows=node_rows, per_window=str(vals)))
    print(arm,step,[(v["source"],v["h"],round(v["original_weighted_loss"],4)) for v in node_rows],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node",type=int,choices=(0,1,10),required=True)
    p.add_argument("--arm",choices=("control","experiment"),action="append")
    args=p.parse_args()
    info=load_registration()
    model,rep=model_and_rep(info["physics_dt"])
    pool=build(yaml.safe_load(open(info["data_recipe"]).read()),model,rep)
    src,ids=open_draws(info,pool)
    torch.set_float32_matmul_precision("highest")
    for arm in args.arm or ("control","experiment"):
        node(arm,args.node,pool,info,model,rep,src,ids)


if __name__=="__main__":
    main()
