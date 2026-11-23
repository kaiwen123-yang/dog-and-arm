"""Measure frozen Actor inputs and its first second of closed-loop actions on development starts."""
import argparse
import json
from pathlib import Path

import mujoco as mj
import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions, build_actor, sensor
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import ActionMap, build, make_model, settings
from scripts.b0.eval_contact_segments import WarpSingleWorld, continuous_initial

PARENT = Path("results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt")
FROZEN = Path("results/raw_large/b0/full_warp_hold_park_r1")
OUT = Path("results/b0/recovery_a_observation_r1")
REGRESSION = Path("results/b0/full_warp_hold_park_u0_warp_r1")
CASES = (1,2,3,4,5,6,7,8,9,18,19,20)


@torch.no_grad()
def audit(side, actor, rep, bank, frames, case, cfg, model, integrator, count):
    folder = REGRESSION/side/"full"/("nominal" if case == 1 else f"C{case:02d}")
    result = json.loads((folder/"result.json").read_text())
    d,(hq,hv,ha,prev),_ = continuous_initial(model,cfg,integrator)
    np.testing.assert_array_equal(d.qpos, result["initial_geometry"]["initial_qpos"])
    np.testing.assert_array_equal(d.qvel, result["initial_geometry"]["initial_qvel"])
    mapping = ActionMap(model)
    initial = None
    actions = []
    xy = []
    for k in range(count):
        hq = np.concatenate([hq[1:],d.qpos[None]])
        hv = np.concatenate([hv[1:],d.qvel[None]])
        ha = np.concatenate([ha[1:],prev[None]])
        q, v = tensor(hq,"cpu"), tensor(hv,"cpu")
        obs = sensor(rep,full_state(q,v),tensor(ha,"cpu"))
        wm,goal = bank.goals(rep,frames+k,q[-1:,:7])
        raw = actor.raw(build_actor_obs_td({"motion":goal},obs[None]))[0].numpy()
        if k == 0:
            rel = d.site(cfg["handle_site"]).xpos - d.site("p4_grasp").xpos
            initial = dict(hist=obs.numpy().copy(),actor_goal=goal.numpy().copy(),
                           wm_goal=wm.numpy().copy(), handle_minus_tcp_world_m=rel.copy(),
                           raw=raw.copy(), clipped=raw.clip(-1,1))
        actions.append(raw.copy())
        xy.append(d.qpos[:2].copy())
        if k+1 == count:
            break
        prev=raw.clip(-1,1)
        servo=(mapping.offset + mapping.scale*prev)*mapping.finger_factor
        for _ in range(10):
            integrator.step(d,servo)
    return initial,np.array(actions),np.array(xy),result["first_failure"]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--frames",type=int,default=51)
    args=p.parse_args()
    if args.frames < 1:
        p.error("at least one measured action required")
    OUT.mkdir(parents=True, exist_ok=True)
    weights=torch.load(PARENT,map_location="cpu",weights_only=False)
    m=make_model()
    rep=RobotRepresentation(m,"cpu")
    actor,_=build_actor(rep,weights["cfg"],m,"cpu")
    actor.load_state_dict(weights["actor"])
    actor.eval()
    for side,goal in (("pull",60),("push",25)):
        bank=DoorMotions([FROZEN/f"{side}_{goal}_train"],rep,"cpu")
        rows=[]
        for case in CASES:
            cfg=settings("mobile" if side == "pull" else "push",case)
            # Each compiled model contains the registered friction/damping factors.
            model=build(cfg)
            integrator=WarpSingleWorld(model,"cuda:0")
            initial,actions,xy,failure=audit(side,actor,rep,bank,torch.zeros(1,dtype=torch.long),
                                             case,cfg,model,integrator,args.frames)
            if case == 1:
                baseline=initial,actions,xy
            base,bact,bxy=baseline
            diffs={key:float(np.abs(value-base[key]).max()) for key,value in initial.items()}
            rows.append(dict(case=f"C{case:02d}",perturbation=cfg["perturbation"],
                initial_max_abs=diffs, first_action_max_abs_by_group=
                [float(np.abs(initial["raw"][sl]-base["raw"][sl]).max())
                 for sl in (slice(0,12),slice(12,16),slice(16,22),slice(22,23))],
                compared_policy_frames=len(actions), physical_substeps=10*(len(actions)-1),
                window_raw_action_max_abs=float(np.abs(actions-bact).max()),
                window_relative_xy_drift_m=float(np.linalg.norm(xy-bxy-(xy[0]-bxy[0]),axis=1).max()),
                previous_full_task_first_failure=failure,warp_capacity=integrator.capacity()))
            print(side,case,diffs,flush=True)
            del integrator
        with (OUT/f"{side}.json").open("x") as f:
            json.dump(dict(checkpoint=str(PARENT),references=str(FROZEN),side=side,
                           physics="Warp3.16, independent closed-loop history and 10x2ms per action",
                           inference="frozen u0 Torch CPU, initial history10 repeated with zero previous action",
                           source_full_scores=str(REGRESSION), groups=["legs12","wheels4","arm6","jaw1"],
                           rows=rows),f,indent=2,allow_nan=False)
            f.write("\n")


if __name__ == "__main__":
    main()
