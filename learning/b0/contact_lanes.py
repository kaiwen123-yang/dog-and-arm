"""Continuous Warp collection with per-lane, physically integrated RSI prefixes."""
import numpy as np
import torch
from tensordict import TensorDict
from supermimic.tasks.task_spec import build_actor_obs_td

from .contact_model import contact_state


def collect_lanes(run, raw_path=None):
    plant, bank = run.plant, run.bank
    n, device = run.n, run.device
    if run.sampler is None or run.schedule is None or not run.cfg.get('freeze_wm_input_statistics'):
        raise ValueError("The continuous recipe requires ReturnSampler, Ratio and fixed WM statistics")
    if not hasattr(run, 'lanes'):
        run.last_episode = getattr(run, 'last_episode', 0)
        run.lanes = dict(frame=torch.zeros(n, device=device, dtype=torch.long),
                         episode=torch.zeros(n, device=device, dtype=torch.long),
                         prefix=torch.zeros(n, device=device, dtype=torch.long),
                         reset=torch.ones(n, device=device, dtype=torch.bool),
                         rejected=torch.zeros(n, device=device, dtype=torch.bool),
                         previous=torch.zeros(n,23, device=device),
                         history=torch.zeros(n,10,77, device=device),
                         noisy=torch.zeros(n,10,77, device=device))
    lane = run.lanes
    rows, compact, raw = [], [], []
    starts = torch.zeros(len(run.eligible),device=device,dtype=torch.long)
    run.actor.eval()
    for tick in range(run.steps):
        ids = torch.where(lane['reset'])[0]
        if len(ids):
            start = run.sampler.sample(len(ids))
            starts += torch.bincount(torch.searchsorted(bank.motion_ends,start,right=True),minlength=len(starts))
            frame = start-10
            plant.reset(bank.qpos[frame],bank.qvel[frame],ids)
            lane['frame'][ids] = frame
            lane['episode'][ids] = run.last_episode + torch.arange(1,len(ids)+1,device=device)
            run.last_episode += len(ids)
            lane['prefix'][ids] = 10
            lane['previous'][ids] = run.actions[frame-1]
            lane['history'][ids] = 0
            lane['noisy'][ids] = 0
            lane['rejected'][ids] = False
        frame = lane['frame']
        side = run.sides[frame]
        ctx = run.ctx[side]
        previous = lane['previous']
        q, v = plant.data.qpos[:].clone(), plant.data.qvel[:].clone()
        state = contact_state(q,v)
        clean = run.sense(q,v,previous)
        hist = torch.cat([lane['history'][:,1:],clean[:,None]],1)
        noisy = torch.cat([lane['noisy'][:,1:],run.robot.add_proprio_noise(clean)[:,None]],1)
        policy = lane['prefix'] == 0
        _,goal = bank.goals(run.rep,frame,state[:,:7],q[:,31])
        obs = build_actor_obs_td({'motion':goal},noisy)
        raw_cmd = run.actor.raw(obs) + torch.randn_like(previous)*run.cfg['collection_noise']*run.exploration_scale
        action = torch.where(policy[:,None],raw_cmd.clamp(-1,1),run.actions[frame])
        evidence = plant.step_contact(action,side,run.phases[frame],record=raw_path is not None,
                                      capture_first_failure_state=True,measure_peak_force=True,measure_grip=True)
        q1,v1 = plant.data.qpos[:].clone(),plant.data.qvel[:].clone()
        ns = contact_state(q1,v1)
        fail = evidence['first_fail_substep']
        valid = policy & evidence['valid_full_interval']
        measured = policy & (valid | evidence['stop_valid'])
        end = bank.motion_ends[torch.searchsorted(bank.motion_ends,frame,right=True)]
        clip_end = policy & (frame+1 >= end-1)
        terminal = policy & (fail>0)
        if valid.any() and not run.cfg.get('freeze_actor_statistics',False):
            run.actor.train()
            run.actor.update_normalization(obs[valid])
            run.actor.eval()
        rr = run.rep.represent(ns)
        reward = run.rep.compute_wm_reward_from_reference(rr,ns[:,:7],run.rep.joint_state(rr),
                                                         action,previous,*bank.body_state(frame+1))
        actual = run.sampler_reference.rewards(run.rep,reward,frame,measured,fail,
                     evidence['stop_qpos'],evidence['stop_qvel'],action,previous)
        # No physical return flows through the prefix. A measured terminal uses
        # the first failed substep's state, dt and reference.
        sampler = run.sampler
        sampler.valid[:,sampler._step] = measured
        dist = sampler.record(frame,torch.where(measured,actual,0.),terminal,clip_end & ~terminal,
                              ~measured)
        if dist is not None:
            sampler.probabilities = dist
        episode = lane['episode'].clone()
        rows.append(TensorDict(dict(state=state,next_state=ns,prev_action=previous.clone(),action=action,
                  sim_ctx=ctx,history=hist.flatten(1),motion_time=frame.clone(),episode=episode,valid=valid,
                  terminated=terminal,truncated=clip_end & ~terminal,reward=reward),batch_size=(n,)))
        lane['rejected'] |= ~policy & ((fail>0) | ~evidence['valid_full_interval'])
        bad_prefix = (lane['prefix']==1) & lane['rejected']
        compact.append(dict(episode=episode, frame=frame.clone(), phase=run.phases[frame,0],side=side,
                prefix=~policy, rejected_prefix=bad_prefix, valid=valid, fail=fail, reason=evidence['reason'],
                peak_force=evidence['peak_force_n'],finger_min=evidence['finger_min'], clip_end=clip_end))
        if raw_path is not None:
            fields=dict(qpos=q,qvel=v,next_qpos=q1,next_qvel=v1,raw=raw_cmd,clipped=action,
                        active=policy,valid=valid,prev_action=previous.clone(),frame=frame.clone(),episode=episode,
                        first_fail_substep=fail,reason=evidence['reason'],physics_steps=evidence['physics_steps'])
            fields.update({'sub_'+key:value for key,value in evidence['substeps'].items()})
            raw.append({k:v.cpu().numpy() for k,v in fields.items()})
        lane.update(frame=frame+1,previous=action.clone(),history=hist.clone(),noisy=noisy,
                    prefix=(lane['prefix']-1).clamp_min(0),reset=terminal | clip_end | (policy & ~valid) | bad_prefix)
    if raw:
        raw_path.mkdir(parents=True,exist_ok=False)
        for key in raw[0]:
            np.save(raw_path/(key+'.npy'), np.stack([r[key] for r in raw]))
    arrays = {k:torch.stack([r[k] for r in compact]).cpu().numpy() for k in compact[0]}
    block = run.schedule.cohorts+1
    if hasattr(run,'compact_directory'):
        np.savez_compressed(run.compact_directory/f'lanes_{block:06}.npz',**arrays)
    counts = arrays['valid'].sum(axis=1).tolist()
    run.replay.append(rows)
    run.schedule.add_cohort(run.total,counts)
    run.total += sum(counts)
    run.simulated += n*run.steps
    return dict(valid_transitions=sum(counts),cumulative_valid_transitions=run.total,
                simulated_lane_intervals=n*run.steps,starts_per_motion=starts.tolist(),
                prefix_intervals=int(arrays['prefix'].sum()),prefix_invalid=int(arrays['rejected_prefix'].sum()),
                failed_lanes=int(((arrays['fail']>0)&~arrays['prefix']).sum()),
                post_failure_diagnostic_substeps=int(np.where((arrays['fail']>0)&~arrays['prefix'],10-arrays['fail'],0).sum()),
                waiting_intervals=0,last_episode=run.last_episode)
