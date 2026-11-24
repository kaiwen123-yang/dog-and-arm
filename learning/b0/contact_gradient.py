"""Observe the eager first official update on its actual starts and noise graph."""
from collections import Counter, defaultdict
import json
import numpy as np
import torch
from .contact_reward import reward_terms
from .contact_warp import PHASES
from .physics import ActionMap


def trace_first_update(run,out,raw):
    policy=run.policy
    env=policy.wm_env
    sample,step,bootstrap=env.sample_initial_states,env.step,policy._bootstrap
    parts=defaultdict(list)
    rewards=[]
    weights=[]
    full_aux=[]
    ids={}
    first=[]
    survival=None

    def observed_start():
        start=sample()
        for key in ("episode","motion_time","draw_phase","draw_mode","terminated","sim_ctx","history","prev_action","state"):
            ids[key]=start[key].detach().cpu().numpy()
        return start

    def observed_step(action):
        nonlocal survival
        prev=env.last_actions
        target=env._ref_body_state
        obs,r,done,info=step(action)
        if not first:
            first.append(action)
            survival=torch.ones_like(r)
        discount=policy.cfg.gamma**len(rewards)
        terms=reward_terms(run.rep,env.rep_state,env.aux_state,action,prev,target,coordinates="fixed_effort")
        for key,value in terms.items():
            parts[key].append(discount*survival.detach()*value)
        parts["survival"].append(discount*survival*r.detach())
        weights.append(survival.detach())
        rewards.append(discount*survival*r)
        full_aux.append(run.actor.auxiliary_loss())
        survival=survival*(1-done)
        return obs,r,done,info

    def observed_bootstrap(obs,alive,done):
        value=bootstrap(obs,alive,done)
        critic=policy.critic(obs["critic"]).clamp(max=policy._v_max).squeeze(-1)*policy.cfg.gamma**policy.cfg.horizon
        parts["critic"].append(critic*alive.detach())
        parts["survival"].append(critic.detach()*alive)
        parts["negative_auxiliary"]=[-x for x in full_aux]
        pieces={k:sum(v) for k,v in parts.items()}
        pieces["complete"]=sum(rewards)+value-sum(full_aux)
        a=first[0]
        def grad(x):
            g=torch.autograd.grad(x.sum(),a,allow_unused=True,retain_graph=True)[0] if x.requires_grad else None
            return torch.zeros_like(a) if g is None else g
        matrix={key:grad(x).detach() for key,x in pieces.items()}
        residual=matrix["complete"]-sum(v for k,v in matrix.items() if k!="complete")
        scale=a.new_tensor(ActionMap(run.model).scale)
        physical={k:(v/scale).cpu().numpy() for k,v in matrix.items()}
        np.savez_compressed(raw/"u1_true_actor_batch.npz",**ids,first_command=a.detach().cpu().numpy(),
            survival=torch.stack(weights).cpu().numpy(),**{"dreturn_dphysical_"+k:v for k,v in physical.items()})
        modes=("free","other_contact","two_finger","loss_or_slip","release")
        counts=Counter(f"{('pull','push')[int(s)]}/{PHASES[p]}/{modes[m]}" for s,p,m in zip(
            ids["sim_ctx"][:,0],ids["draw_phase"],ids["draw_mode"]))
        targets=[16,17,18,19,20,21,22]
        result=dict(objective="ascent of return minus auxiliary; per-sample derivative w.r.t. first clipped command in radians or metres",
            update=1,batch=len(a),distinct_online_episodes=len(np.unique(ids["episode"])),terminal=int(ids["terminated"].sum()),
            side_phase_mode=dict(counts),source="actual online replay, single original eager actor rollout",
            survival_mean_by_step=[float(w.mean()) for w in weights],channels=targets,
            mean_by_channel={k:v[:,targets].mean(0).tolist() for k,v in physical.items()},
            residual_max_canonical=float(residual.abs().max()),complete_max_canonical=float(matrix["complete"].abs().max()),
            return_mean=float(pieces["complete"].detach().mean()),critic_value_cap=policy._v_max)
        (out/"gradient_u1.json").write_text(json.dumps(result,indent=2,allow_nan=False))
        env.step=step
        env.sample_initial_states=sample
        policy._bootstrap=bootstrap
        return value

    env.sample_initial_states=observed_start
    env.step=observed_step
    policy._bootstrap=observed_bootstrap
