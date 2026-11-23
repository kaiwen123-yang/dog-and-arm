"""One-step real TD auxiliary updates on measured Warp successors and physical hard failures."""
import torch
from supermimic.learners.learner_utils import _optimize_step


def add_measured_grip_target(run, raw):
    """Extra real critic target in open/hold. No force/occupancy from the future enters imagination."""
    import numpy as np
    from learning.b0.contact_warp import PHASE_ID
    data,starts=run.replay.chunks[-1]
    frames=data["motion_time"]
    def measured(name):
        return torch.as_tensor(np.load(raw/(name+".npy")),device=run.device).transpose(0,1)
    grip=torch.isin(run.phases[frames],torch.tensor([PHASE_ID["open"],PHASE_ID["hold"]],device=run.device)).all(-1)
    fg=measured("sub_finger_load_N")
    both=(fg>run.plant.cfg["contact_threshold_n"]).all(-1)
    legal=measured("sub_unexpected_contact_N")<=run.plant.cfg["contact_threshold_n"]
    occ=(both & legal).float().mean(-1)
    distance=measured("sub_grip_error_m").amax(-1)
    peak=measured("sub_door_robot_force_N").norm(dim=-1).amax(-1)
    dtheta=data["next_state"][...,61]-run.bank.qpos[frames+1,31]
    geom=(1+(distance/run.plant.cfg["grasp_error_m"]).square()).reciprocal()
    force=(1+torch.relu(peak/run.plant.cfg["grip_net_force_limit_n"]-1).square()).reciprocal()
    progress=(1+(dtheta/np.deg2rad(2.)).square()).reciprocal()
    quality=occ*geom*force*progress
    data["measured_task_reward"]=torch.where(grip,data["reward"]*quality,data["reward"])
    iv=starts[1]
    selected=grip[iv[:,0],iv[:,1]]
    q=quality[iv[:,0],iv[:,1]][selected]
    return dict(measured_grip_intervals=int(selected.sum()),mean_grip_successor_quality=float(q.mean()) if len(q) else None)


def fit_real_critic(run, terminal_mask, batches=8, task_reward=False):
    """Matched sampling; only terminal_mask differs between the two real-TD variants."""
    env=run.policy.wm_env
    pool=[]
    for data,indices in run.replay.chunks:
        starts=indices[1]
        if len(starts):
            pool.append(data[starts[:,0],starts[:,1]])
    records=torch.cat(pool)
    terminal=records["terminated"]
    pos=terminal.nonzero().flatten()
    neg=(~terminal).nonzero().flatten()
    if not len(neg) or not len(pos):
        return {"actual_td_minibatches":0,"eligible_hard_terminals":len(pos)}
    total=0
    losses=[]
    true_terminal_values=[]
    nonterminal_values=[]
    run.critic.requires_grad_(True)
    for _ in range(batches):
        n=run.cfg["actor_batch"]
        idx=torch.cat([group[torch.randint(len(group),(size,),device=run.device)]
                       for group,size in ((pos,n//2),(neg,n-n//2))])
        row=records[idx]
        def inputs(s,t):
            rep=run.rep.represent(s)
            goal,_=run.bank.goals(run.rep,t,s[:,:7],s[:,61])
            return torch.cat((rep,goal,row["sim_ctx"]),-1)
        with torch.no_grad():
            before=inputs(row["state"],row["motion_time"])
            after=inputs(row["next_state"],row["motion_time"]+1)
            next_value=run.critic(after).squeeze(-1)
            continuation=(~row["terminated"]).float() if terminal_mask else torch.ones_like(next_value)
            # At a collection horizon a valid measured successor is available; its value bootstraps normally.
            reward=row["measured_task_reward"] if task_reward else row["reward"]
            target=(reward+run.policy.cfg.gamma*continuation*next_value).clamp(max=run.policy._v_max)
        predicted=run.critic(before).squeeze(-1)
        loss=(target-predicted).square().mean()
        _optimize_step(run.policy.critic_optimizers,loss,run.critic.parameters(),max_norm=1.)
        total+=len(idx)
        true_terminal_values.append(float(predicted[row["terminated"]].detach().mean()))
        nonterminal_values.append(float(predicted[~row["terminated"]].detach().mean()))
        losses.append(float(loss.detach()))
    return dict(actual_td_minibatches=batches,eligible_hard_terminals=len(pos),eligible_nonterminal=len(neg),
                real_td_samples=total,terminal_sample_fraction=.5,real_td_mse=sum(losses)/batches,
                mean_predicted_v_terminal=sum(true_terminal_values)/batches,
                mean_predicted_v_nonterminal=sum(nonterminal_values)/batches)
