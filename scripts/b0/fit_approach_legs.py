"""Fit the remaining stance-yaw command from the registered physical teacher episodes."""
import argparse
import json
from pathlib import Path

import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import APPROACH_LEG_WHEEL, DoorMotions, build_actor
from learning.b0.model import RobotRepresentation
from learning.b0.physics import make_model
from scripts.b0.recovery_bc import AUGMENT, DESIGN, REF, REFERENCE, dump, episode, merge


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--wheel", type=Path, default=Path("results/b0/recovery_approach_wheel_r1/checkpoint_000000.pt"))
    ap.add_argument("--restrict-existing", type=Path, help="Use unchanged fitted weights and remove carry outside the supervised approach")
    args = ap.parse_args()
    if Path(args.run).name != args.run:
        ap.error("Expected a fresh run name")
    out=Path("results/b0")/args.run
    out.mkdir(exist_ok=False)
    if args.restrict_existing:
        source=torch.load(args.restrict_existing,map_location="cpu",weights_only=False)
        if source["cfg"]["actor_goal_schema"]!=APPROACH_LEG_WHEEL:
            raise ValueError("Expected a learned leg/wheel feedback policy")
        source["cfg"]=dict(source["cfg"],trim_only_in_supervised_phase=True)
        dump(out/"actual_config.json",dict(source=str(args.restrict_existing),changes="remove stance carry outside the fitted approach only; all parameters identical",
              additional_optimization=0,source_leg_bc=source["additional_leg_bc_updates"],h32_updates=0))
        torch.save(source,out/"checkpoint_000000.pt")
        return
    device="cuda:0"
    torch.manual_seed(231123)
    torch.set_float32_matmul_precision("highest")
    source=torch.load(args.wheel,map_location="cpu",weights_only=False)
    cfg=dict(source["cfg"],actor_goal_schema=APPROACH_LEG_WHEEL,additional_bc_run=args.run)
    model=make_model()
    rep=RobotRepresentation(model,device)
    bank=DoorMotions([REFERENCE/n for n in REF.values()],rep,device,actor_schema=APPROACH_LEG_WHEEL)
    actor,_=build_actor(rep,cfg,model,device)
    missing,extra=actor.load_state_dict(source["actor"],strict=False)
    if extra or set(missing)!={"leg_trim_projection","leg_trim_gain", *("trim_rate."+n for n in actor.trim_rate.state_dict())}:
        raise ValueError(f"Unexpected migration: {missing}, {extra}")
    actor.eval().requires_grad_(False)
    actor.trim_rate.requires_grad_(True)
    sets={"train":[],"validation":[]}
    with torch.no_grad():
        for c in json.loads(DESIGN.read_text())["cases"]:
            g,h,a=episode(AUGMENT/c["episode_id"],c["split"],bank,rep,device)
            keep=g[:,-1].bool()
            obs=build_actor_obs_td({"motion":g[keep]},h[keep])
            x,previous,_=actor.trim_inputs(obs)
            rate=((a[keep,:12] @ actor.leg_trim_projection)[:,None]-previous)/.02
            sets[c["split"]].append((x,rate))
    (x,y),(vx,vy)=[merge(sets[k]) for k in ("train","validation")]
    opt=torch.optim.Adam(actor.trim_rate.parameters(),lr=.002)
    for step in range(1200):
        ix=torch.randint(len(x),(128,),device=device)
        opt.zero_grad(set_to_none=True)
        loss=(actor.trim_rate(x[ix]) - y[ix]/.08).square().mean()
        loss.backward()
        opt.step()
    with torch.no_grad():
        rmse=lambda a,b: (actor.trim_rate(a)*.08-b).square().mean().sqrt().item()
        dump(out/"actual_config.json",dict(wheel_source=str(args.wheel),variant=cfg["actor_goal_schema"],
             fit="only 10-32-1 yaw trim rate, predeclared 1200 Adam updates; wheel and trunk frozen",
             rate_limit_rad_s=.08,trim_bound_rad=.27925,train_frames=len(x),val_frames=len(vx),
             target_abs_max_rad_s=y.abs().max().item(),train_rmse_rad_s=rmse(x,y),val_rmse_rad_s=rmse(vx,vy),
             validation_zero_rate_rmse=vy.square().mean().sqrt().item(),reference=str(REFERENCE),
             leg_trim_gain=actor.leg_trim_gain.tolist(),h32_updates=0))
    torch.save(dict(source,cfg=cfg,actor=actor.state_dict(),additional_bc_variant="approach_leg_wheel",
                    additional_leg_bc_updates=1200),out/"checkpoint_000000.pt")
    torch.save(dict(optimizer=opt.state_dict(),rng=torch.cuda.get_rng_state(),updates=1200),out/"bc_optimizer_rng.pt")


if __name__=="__main__":
    main()
