"""One-step real TD auxiliary updates on measured Warp successors and physical hard failures."""
import torch
from supermimic.learners.learner_utils import _optimize_step


def fit_real_critic(run, terminal_mask, batches=8):
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
            goal,_=run.bank.goals(run.rep,t,s[:,:7])
            return torch.cat((rep,goal,row["sim_ctx"]),-1)
        with torch.no_grad():
            before=inputs(row["state"],row["motion_time"])
            after=inputs(row["next_state"],row["motion_time"]+1)
            next_value=run.critic(after).squeeze(-1)
            continuation=(~row["terminated"]).float() if terminal_mask else torch.ones_like(next_value)
            # At a collection horizon a valid measured successor is available; its value bootstraps normally.
            target=(row["reward"]+run.policy.cfg.gamma*continuation*next_value).clamp(max=run.policy._v_max)
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
