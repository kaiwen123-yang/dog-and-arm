"""Exercise the same hinge feedback in real collection and in a frozen-WM H32 forward pass."""
import json
from pathlib import Path

import numpy as np
import torch
from tensordict import TensorDict

from learning.b0.contact_model import contact_state
from learning.b0.contact_training import ContactRun
from learning.b0.model import tensor
from scripts.b0.fit_endpoint_policy import FROZEN,REF,RUN,TEACHER


def main():
    dev="cuda:0"
    torch.manual_seed(0)
    w=torch.load(RUN/"checkpoint_000000.pt",map_location="cpu",weights_only=False)
    cfg=dict(w["cfg"],worlds=4,wm_batch=4,actor_batch=1,cohort_steps=8,
             freeze_actor_statistics=True,reference_directory=str(FROZEN))
    cfg.pop("physical_action_prior",None)
    refs=[FROZEN/name for name in cfg["references"]]
    run=ContactRun(cfg,refs,refs,w,w,dev)
    cohort=Path("results/raw_large/b0/recovery_endpoint_hinge_chain_r2")
    with torch.no_grad():
        measured=run.collect(cohort)
    env=run.policy.wm_env
    env.dynamics.eval().requires_grad_(False)
    env.representation.eval().requires_grad_(False)
    run.actor.eval()
    q,v,prev=[tensor(np.load(TEACHER/(name+".npy")),dev) for name in ("qpos","qvel","last_action")]
    phase=np.load(TEACHER/"phase.npy")
    names=json.loads((TEACHER/"metadata.json").read_text())["phases"]
    points=np.flatnonzero(phase==names.index("grasp"))
    k=int(points[len(points)//2])
    hist=run.sense(q[k-9:k+1],v[k-9:k+1],prev[k-9:k+1])[None]
    batch=TensorDict(dict(state=contact_state(q[k:k+1],v[k:k+1]),prev_action=prev[k:k+1],
                     sim_ctx=run.ctx[1:2],motion_time=torch.tensor([run.bank.starts[REF["push"]]+k],device=dev),
                     sensor_window=hist,pad_mask=torch.zeros(1,10,dtype=torch.bool,device=dev)),batch_size=[1])
    obs=env.reset(batch)
    residuals=[]
    reward=0.
    for i in range(32):
        correct=env.rep_state[:,58]-run.bank.qpos[env.motion_times,31]
        torch.testing.assert_close(obs["goal_motion"][:,540],correct)
        residuals.append(float(correct.detach().item()))
        a=run.actor(obs)
        if i==0:first=a
        obs,r,_,_=env.step(a)
        reward=reward+r
    grads=torch.autograd.grad(reward.sum(),(first,run.actor.hinge_coefficients))
    data=dict(seed=0,real_collection=measured,teacher_episode=TEACHER.name,push_initial_frame=k,
              source="current 58th zero-based contact-state representation component = current hinge angle (rad); future hinge from learned dynamics only",
              deployed_actor_goal_dim=obs["goal_motion"].shape[-1],imagination_steps=32,hinge_error_rad=residuals,
              immediate_sum_gradient_first_action_l2=grads[0].norm().item(),
              immediate_sum_gradient_fitted_coefficients_l2=grads[1].norm().item(),
              frozen_wm=True,new_wm_updates=0,new_actor_updates=0,new_critic_updates=0)
    with (RUN/"hinge_chain.json").open("x") as f:
        f.write(json.dumps(data,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    main()
