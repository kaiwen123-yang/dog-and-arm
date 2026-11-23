"""Fit a push hinge-feedback arm/jaw residual on the single frozen-clock-compatible teacher."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions,build_actor,sensor
from learning.b0.endpoint_policy import KNOTS,SCHEMA,TERMINAL,features
from learning.b0.model import RobotRepresentation,full_state,tensor
from learning.b0.physics import ActionMap,make_model
from scripts.b0.recovery_teacher import FROZEN

SOURCE=Path("results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt")
TEACHER=Path("results/raw_large/b0/recovery_endpoint_release_teacher_r2/endpoint_aug_push_06_train_door")
RUN=Path("results/b0/recovery_endpoint_hinge_bc_r1")
REF={"pull":"pull_60_train","push":"push_25_train"}


def extend_weights(old,actor):
    dst=actor.state_dict()
    extra="hinge_coefficients"
    if set(dst)-set(old)!={extra}:
        raise ValueError("Unexpected parameters")
    for key,val in old.items():
        if dst[key].shape==val.shape:
            dst[key]=val
        else:
            fill={"encoders.motion.0.weight":0., "goal_normalizers.motion._mean":0.,
                  "goal_normalizers.motion._var":1., "goal_normalizers.motion._std":1.}[key]
            if val.shape[-1]!=540 or dst[key].shape[-1] not in (544,545):
                raise ValueError(f"Unexpected source {key}")
            dst[key].fill_(fill)
            dst[key][...,:540]=val
    actor.load_state_dict(dst)


@torch.no_grad()
def batch(path,actor,bank,rep,mapping):
    meta=json.loads((path/"metadata.json").read_text())
    ref=REF[meta["task"]]
    n=min(int(np.load(path/"valid_full_interval.npy").sum()),int(bank.motion_ends[bank.ids[ref]])-bank.starts[ref]-1)
    q,v,prev=[tensor(np.load(path/(k+".npy"))[:n],"cpu") for k in ("qpos","qvel","last_action")]
    hist=sensor(rep,full_state(q,v),prev)
    k=torch.arange(n)
    h=hist[(k[:,None]+torch.arange(-9,1)[None]).clamp_min(0)]
    _,g=bank.goals(rep,k+bank.starts[ref],q[:,:7],q[:,31])
    labels=torch.as_tensor(np.load(path/"action_clipped.npy")[:n],dtype=torch.float64)
    pred=torch.cat([actor.raw(build_actor_obs_td({"motion":x},y)) for x,y in zip(g.split(128),h.split(128))])
    delta=(labels[:,16:]-pred[:,16:])*torch.as_tensor(mapping.scale[16:],dtype=torch.float64)
    return tuple(x.double() for x in features(g)),delta


def fit(phi,y):
    # Fixed per-phase piecewise linear feedback gains. A second-difference prior
    # suppresses oscillation in the gain curve; no C episodes enter this solve.
    reg=torch.eye(2*KNOTS,dtype=torch.float64)*.002
    d=torch.eye(KNOTS,dtype=torch.float64).diff(n=2,dim=0)
    l=torch.block_diag(d,d)
    reg+=.06*(l.T@l)
    return torch.linalg.solve(phi.T@phi+reg,phi.T@y)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--terminal-feedback",action="store_true",help="use the frozen hold equilibrium as the terminal open-phase command")
    args=p.parse_args()
    out=RUN.with_name("recovery_endpoint_hinge_bc_tail_r2") if args.terminal_feedback else RUN
    schema=TERMINAL if args.terminal_feedback else SCHEMA
    torch.manual_seed(0)
    out.mkdir(exist_ok=False)
    cfg_source=torch.load(SOURCE,map_location="cpu",weights_only=False)
    cfg=dict(cfg_source["cfg"],actor_goal_schema=schema)
    m=make_model()
    rep=RobotRepresentation(m,"cpu")
    bank=DoorMotions([FROZEN/r for r in REF.values()],rep,"cpu",actor_schema=schema)
    actor,_=build_actor(rep,cfg,m,"cpu")
    extend_weights(cfg_source["actor"],actor)
    actor.eval()
    mapping=ActionMap(m)
    nominal=[batch(FROZEN/r,actor,bank,rep,mapping) for r in REF.values()]
    teacher_verdict=json.loads(Path("results/b0/recovery_endpoint_release_teacher_r2/endpoint_aug_push_06_train_door_frozen_judge.json").read_text())
    if not teacher_verdict["frozen_judge_pass"]:
        raise ValueError("Frozen-clock compatible teacher required")
    teacher=batch(TEACHER,actor,bank,rep,mapping)
    sets=nominal+[teacher]
    a,j=[torch.cat([s[0][i] for s in sets]) for i in (0,1)]
    y=torch.cat([s[1] for s in sets])
    coef=torch.cat((fit(a,y[:,:6]),fit(j,y[:,6:])),dim=1)
    with torch.no_grad():
        actor.hinge_coefficients.copy_(coef)
    metrics={}
    for name,(ph,orig) in zip(("nominal_pull","nominal_push","perturbed_push"),sets):
        pred=torch.cat((ph[0]@coef[:,:6],ph[1]@coef[:,6:]),dim=1)
        active=ph[0].abs().sum(1)>0
        metrics[name]=dict(frames=len(orig),conditioned_frames=int(active.sum()),
                           max_abs_added_rad_m=pred.abs().max(0).values.tolist())
        if active.any():
            metrics[name].update(active_rms_before_rad_m=orig[active].square().mean(0).sqrt().tolist(),
                                 active_rms_after_rad_m=(orig-pred)[active].square().mean(0).sqrt().tolist())
    metrics["design"]=dict(anchor=str(SOURCE),teacher=str(TEACHER),frozen_reference=str(FROZEN),seed=0,
        schema="original 540 reference features + measured or predicted hinge minus frozen hinge, push grasp, push open, progress through named reference phase",
        nominal_guard="both nominal trajectories included; zero residual for error <= 0.2 deg, ramp 0.2–0.4 deg; negative errors outside single positive training support remain inactive",
        labels="all full 20ms supervised teacher intervals with a frozen judge pass; includes legal early hold on the frozen open clock",
        fit="one full-batch physical-unit smooth ridge solve. 25 linear spline knots per reference phase; second-difference penalty .06 plus .002 ridge",
        channels="six arm angles in rad with response linear in measured hinge error; jaw width in m with a saturated gain. No leg/wheel changes",
        nonlinear_scaling="arm scaling capped at 2 x 2.8deg; jaw reaches full delayed-close command from 1deg, then saturates",
        source_reference_bc_updates=3000,new_actor_parameters=coef.numel(),new_solve_count=1,wm_updates=0,h32_updates=0,
        clock="one common nominal library per side; no perturbed or C-specific reference; zero pull residual")
    metrics["design"]["terminal_feedback"]=args.terminal_feedback
    (out/"fit.json").write_text(json.dumps(metrics,indent=2,allow_nan=False)+"\n")
    torch.save(dict(cfg_source,cfg=cfg,actor=actor.state_dict(),additional_bc_variant=schema,supervised_ridge_solves=1),out/"checkpoint_000000.pt")
    print(metrics)


if __name__=="__main__":
    main()
