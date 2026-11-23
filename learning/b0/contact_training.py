"""Online Warp interaction and pinned O1 learners for two-sided contact segments."""
from collections import deque
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import torch
from tensordict import TensorDict
from supermimic.models import Dynamics, build_mlp
from supermimic.envs.multi_task_world_model_env import MultiTaskWorldModelEnv
from supermimic.learners.policy_learner import ActorCriticPolicyLearner, ActorCriticPolicyLearnerCfg
from supermimic.learners.wm_learner import WorldModelLearner

from .contact_model import ContactRepresentation, ContactTcpLoss, ContactWorldModelCfg, contact_context, contact_state
from .contact_policy import DoorMotions, actor_goal_schema, build_actor, sensor
from .contact_replay import ContactEpisode, ContactWindows
from .model import EffortScaledActor, RobotRepresentation, full_state, tensor
from .physics import ActionMap, make_model
from .training import MotionCommand
from supermimic.tasks.task_spec import build_actor_obs_td


class PhysicalActionPrior:
    """Training-only auxiliary loss; deployment runs just the updated Actor."""
    def __init__(self, actor, mapping, cfg, device):
        self.anchor = deepcopy(actor).eval().requires_grad_(False)
        units = np.repeat(cfg['physical_units'], [12, 4, 6, 1])
        self.scale = tensor(mapping.scale / units, device)
        self.weight = cfg['weight']

    def __call__(self, obs, action):
        with torch.no_grad():
            target = self.anchor(obs)
        error = (action - target) * self.scale
        cost = torch.nn.functional.smooth_l1_loss(error, torch.zeros_like(error), reduction='none')
        groups = [part.mean(-1) for part in cost.split((12, 4, 6, 1), -1)]
        return self.weight * torch.stack(groups, -1).mean(-1)


class OnlineContactReplay:
    """Store complete, synchronously started cohorts, with a measured successor per row.

    A failed lane contributes its valid 20 ms terminal interval, then leaves the
    sampling pool. Remaining lanes continue to the end of this collection cohort.
    """
    def __init__(self, capacity, device):
        self.chunks = deque(maxlen=capacity)
        self.device = device

    def append(self, rows):
        data = torch.stack(rows,1)
        valid = data.pop('valid')
        starts = {}
        for steps in (1,7):
            if valid.shape[1] < steps:
                starts[steps] = torch.empty((0,2),device=valid.device,dtype=torch.long)
            else:
                starts[steps] = valid.unfold(1,steps,1).all(-1).nonzero()
        if len(starts[1]):
            self.chunks.append((data,starts))

    def pick(self, steps, batch):
        available = [(data,idx[steps]) for data,idx in self.chunks if len(idx[steps])]
        if not available:
            return None
        counts = np.array([len(idx) for _,idx in available])
        data, starts = available[np.random.choice(len(counts),p=counts/counts.sum())]
        ij = starts[torch.randint(len(starts),(batch,),device=self.device)]
        return data, ij[:,0], ij[:,1]

    def windows(self, steps, batch):
        picked = self.pick(steps,batch)
        if picked is None:
            return None
        data,i,t = picked
        ix = t[:,None]+torch.arange(steps,device=self.device)
        s = data['state'][i[:,None],ix]
        a = data['action'][i[:,None],ix]
        ctx = data['sim_ctx'][i,t][:,None]
        ns = data['next_state'][i,ix[:,-1]]
        return TensorDict(dict(state=torch.cat((s,ns[:,None]),1),
                               action=torch.cat((a,a[:,-1:]),1),
                               sim_ctx=ctx.expand(-1,steps+1,-1)),batch_size=(batch,steps+1))


class DoorImagination(MultiTaskWorldModelEnv):
    def contact_reward(self, robot_reward, rep, next_frames, ctx):
        if self.task_scales is None:
            return robot_reward
        target = self.reference_rep[next_frames]
        # Target geometry comes only from the given reference. Actual/predicted
        # geometry uses the corresponding current state at this same successor.
        def relative_rod(x):
            return torch.where(ctx[:, :1].bool(), x[:, 66:69], x[:, 63:66])

        angle = (rep[:, 58] - target[:, 58]) / self.task_scales['angle_rad']
        delta = (relative_rod(rep) - relative_rod(target)) / self.task_scales['tcp_handle_m']
        joint, _ = self.representation.joint_state(rep).chunk(2, -1)
        q_ref = self.motion.joint_pos[next_frames]
        jaw_error = (joint[:, -2] - joint[:, -1]) - (q_ref[:, -2] - q_ref[:, -1])
        jaw = jaw_error / self.task_scales['jaw_m']
        score = (1 / (1 + angle.square()) + 1 / (1 + delta.square().sum(-1))
                 + 1 / (1 + jaw.square()))
        return robot_reward + self.representation.dt * score

    def force_adjusted_reward(self, reward, peak_force, frames):
        # Use identical bounds and phase clock in real and imagined transitions.
        weight = (1 + (peak_force / self.force_limit_n).pow(4)).reciprocal()
        return torch.where(self.grip_frames[frames], reward * weight, reward)

    def _wm_step(self, rep_state, aux_state, action, last_action, sim_ctx):
        aux, rep, joints, term, tracking = super()._wm_step(
            rep_state, aux_state, action, last_action, sim_ctx)
        reward = self.contact_reward(tracking, rep, self.motion_times+1, sim_ctx)
        if self.force_head is not None:
            force = self.force_head(rep_state, action, sim_ctx)
            reward = self.force_adjusted_reward(reward, force, self.motion_times)
        return aux, rep, joints, term, reward

    def sample_initial_states(self):
        data,i,t = self.replay_buffer.pick(1,self.num_envs)
        batch = data[i,t].clone()
        batch['sensor_window'] = batch['history'].unflatten(-1,(10,77))
        batch['pad_mask'] = torch.zeros((self.num_envs,10),device=self.device,dtype=torch.bool)
        return batch

    def _update_goal(self):
        # Measured successor and predicted successor both score against t+1.
        self._ref_body_state = self.motion.body_state(self.motion_times+1)
        self._wm_goal_obs,self._actor_goal_obs = self.motion.goals(
            self.representation,self.motion_times,self.aux_state,self.rep_state[:,58])
        self._build_task_goals()


@torch.no_grad()
def rescale_standard_arm_jaw(actor, gain):
    """Change decoder update units while preserving pretrained physical commands."""
    if type(actor) is not EffortScaledActor or not np.isfinite(gain) or gain <= 0:
        raise ValueError("Expected a standard EffortScaledActor and a finite positive gain")
    final = actor.decoder[-1]
    actor.standard_action[16:].mul_(gain)
    final.weight[16:].div_(gain)
    final.bias[16:].div_(gain)


class ContactRun:
    def __init__(self,cfg,refs,teachers,actor_checkpoint,wm_checkpoint,device,*,from_free_anchor=False):
        from .contact_warp import ContactPlant, PHASE_ID
        self.device,self.cfg = device,cfg
        self.model = model = make_model()
        mapping = ActionMap(model)
        self.h32_teacher_batches = 2 if cfg.get('long_horizon_tcp_wm') else 0
        self.seven_batches = 8 - self.h32_teacher_batches
        rep_type = ContactTcpLoss if self.h32_teacher_batches else ContactRepresentation
        self.rep = rep = rep_type(model,device)
        self.robot = RobotRepresentation(model,device)
        self.bank = bank = DoorMotions(refs,rep,device,actor_schema=actor_goal_schema(cfg))
        self.actor, task = build_actor(rep,cfg,model,device)
        # Keep the original physical exploration magnitude when a calibrated
        # arm/jaw decoder uses a larger unit to represent nominal poses.
        self.exploration_scale=self.actor.standard_action.clone()
        self.actor.load_state_dict(actor_checkpoint['actor'])
        if from_free_anchor and 'arm_jaw_output_gain' in cfg:
            if cfg.get('calibrated_actor') or actor_checkpoint.get('schema') is not None:
                raise ValueError("Arm/jaw unit change requires a fresh B0-03 standard initialization")
            rescale_standard_arm_jaw(self.actor, cfg['arm_jaw_output_gain'])
        if 'physical_action_prior' in cfg:
            if cfg.get('actor_parameterization') != 'motion_reference_arm_jaw_residual':
                raise ValueError('The contact action prior requires the calibrated reference-residual actor')
            self.actor.training_action_prior = PhysicalActionPrior(
                self.actor, mapping, cfg['physical_action_prior'], device)
        self.dyn = Dynamics(rep,23,5,tensor(mapping.scale,device),tensor(mapping.offset,device),
                            tuple(cfg['wm_hidden'])).to(device)
        self.dyn.load_state_dict(wm_checkpoint['dyn'])
        self.b = cfg['wm_batch']
        horizons = [(1, 2), (7, self.seven_batches)]
        if self.h32_teacher_batches:
            horizons.append((32, self.h32_teacher_batches))
        self.learners = {n: WorldModelLearner(self.dyn,rep,ContactWorldModelCfg(
            batch_size=self.b,horizon=n+1,num_batches=b),device)
            for n,b in horizons}
        for learner in self.learners.values():
            learner.optimizers = self.learners[7].optimizers
        eps=[ContactEpisode.read(p,device) for p in teachers]
        if len(set(e.group for e in eps)) != len(eps):
            raise ValueError('Duplicate teacher episode group')
        self.offline={n:ContactWindows(eps,n) for n in self.learners}
        self.replay=OnlineContactReplay(cfg['replay_cohorts'],device)
        self.n=cfg['worlds']
        self.steps=cfg['cohort_steps']
        pc=ActorCriticPolicyLearnerCfg(batch_size=cfg['actor_batch'],horizon=32,noise=cfg['collection_noise'])
        scales=cfg.get('task_reward_scales')
        spec=SimpleNamespace(num_actions=23,unwrapped=SimpleNamespace(step_dt=.02,command_manager=MotionCommand(bank)),
                cfg=SimpleNamespace(rewards={'tracking':SimpleNamespace(weight=5. if scales is None else 8.)},
                terminations={k:SimpleNamespace(params={'threshold':v}) for k,v in [('anchor_pos',.1),('anchor_ori',.12)]}))
        env=DoorImagination(self.dyn,rep,spec,pc.batch_size,self.replay,[task],10,.05,device)
        env.task_scales=scales
        env.reference_rep=(rep.represent(contact_state(bank.qpos,bank.qvel)) if scales is not None else None)
        self.critic=build_mlp(rep.rep_state_dim+570+5,tuple(cfg['critic_hidden']),1).to(device)
        # Input width changed. Hidden and final layer carry unchanged semantics.
        old=actor_checkpoint['critic']
        for name,w in self.critic.named_parameters():
            if name not in ('0.weight','0.bias') and name in old and old[name].shape==w.shape:
                w.data.copy_(old[name])
        self.policy=ActorCriticPolicyLearner(self.actor,self.critic,env,pc,device)
        if 'calibrated_actor_lr' in cfg:
            for opt in self.policy.actor_optimizers:
                for group in opt.param_groups:
                    if torch.is_tensor(group['lr']):
                        group['lr'].fill_(cfg['calibrated_actor_lr'])
                    else:
                        group['lr']=cfg['calibrated_actor_lr']
        self.plant=ContactPlant(model,self.n,device)
        self.ctx=torch.stack([contact_context(model,side,device) for side in ('pull','push')])
        phase,side,eligible,actions=[],[],[],[]
        for path in refs:
            name=path.name
            start=bank.starts[name]
            n = int(bank.motion_ends[bank.ids[name]]) - start - 1
            meta=bank.metas[name]
            labels=np.load(path/'substeps/phase.npy',mmap_mode='r')[:n*10]
            idx=np.array([PHASE_ID[p] for p in meta['phases']])[labels].reshape(n,10)
            phase.append(np.concatenate([idx,idx[-1:]]))
            side.extend([int(meta['task']=='push')]*(n+1))
            # Each sampled world has a complete 200 ms physical prefix plus
            # a contiguous H32 after any online step used for imagination.
            use=np.isin(idx[:,0],[PHASE_ID[p] for p in cfg['rsi_phases']])
            ii=np.flatnonzero(use & (np.arange(n)>=11) & (np.arange(n)<n-33-self.steps))
            if not len(ii):
                raise ValueError(f'{path} has no valid RSI starts')
            eligible.append(torch.as_tensor(ii+start,device=device))
            acts = tensor(np.load(path / "action_clipped.npy", mmap_mode="r")[:n], device)
            actions.append(torch.cat((acts,acts[-1:])))
        self.phases=torch.as_tensor(np.concatenate(phase),device=device,dtype=torch.long)
        env.force_head = None
        if 'peak_force_checkpoint' in cfg:
            from .contact_force import PeakDoorForce
            env.force_head = PeakDoorForce(mapping, device)
            env.force_head.load_state_dict(torch.load(cfg['peak_force_checkpoint'], map_location=device, weights_only=True))
            env.force_head.eval().requires_grad_(False)
            env.force_limit_n = self.plant.cfg['grip_net_force_limit_n']
            env.grip_frames = ((self.phases == PHASE_ID['open']) | (self.phases == PHASE_ID['hold'])).all(1)
        self.sides=torch.tensor(side,device=device,dtype=torch.long)
        self.eligible=eligible
        self.actions=torch.cat(actions)
        self.total=self.simulated=0

    def sense(self,q,v,prev):
        return sensor(self.robot,full_state(q,v),prev)

    def optimizer_list(self):
        return [*self.learners[7].optimizers,*self.policy.actor_optimizers,*self.policy.critic_optimizers]

    @torch.no_grad()
    def collect(self,raw_path=None,*,training=True):
        bank,plant=self.bank,self.plant
        frames=torch.cat([x[torch.randint(len(x),((self.n+j)//len(self.eligible),),device=self.device)]
                          for j,x in enumerate(self.eligible)])
        frames=frames[torch.randperm(len(frames),device=self.device)]
        start=frames.clone()
        side=self.sides[frames]
        ctx=self.ctx[side]
        plant.reset(bank.qpos[frames-10],bank.qvel[frames-10])
        hist=[]
        alive=torch.ones(self.n,device=self.device,dtype=torch.bool)
        for k in range(-10,0):
            hist.append(self.sense(plant.data.qpos[:],plant.data.qvel[:],self.actions[frames+k-1]))
            result=plant.step_contact(self.actions[frames+k],side,self.phases[frames+k])
            alive &= result['valid_full_interval'] & (result['first_fail_substep']==0)
        prev=self.actions[frames-1]
        hist=torch.stack(hist[1:]+[self.sense(plant.data.qpos[:],plant.data.qvel[:],prev)],1)
        noisy=self.robot.add_proprio_noise(hist)
        rows,records=[],[]
        self.actor.eval()
        failures=torch.zeros(self.n,device=self.device,dtype=torch.long)
        prefixes_invalid=int((~alive).sum())
        for k in range(self.steps):
            q,v=plant.data.qpos[:].clone(),plant.data.qvel[:].clone()
            s=contact_state(q,v)
            _,goal=bank.goals(self.rep,frames,s[:,:7],q[:,31])
            obs=build_actor_obs_td({'motion':goal},noisy)
            raw=self.actor.raw(obs)+torch.randn_like(prev)*self.cfg['collection_noise']*self.exploration_scale
            action=raw.clamp(-1,1)
            force_reward = self.policy.wm_env.force_head is not None
            evidence=plant.step_contact(action,side,self.phases[frames],record=raw_path is not None,
                                        measure_peak_force=force_reward)
            q1,v1=plant.data.qpos[:].clone(),plant.data.qvel[:].clone()
            ns=contact_state(q1,v1)
            valid=alive & evidence['valid_full_interval']
            if training and valid.any() and not self.cfg.get('freeze_actor_statistics',False):
                self.actor.train()
                self.actor.update_normalization(obs[valid])
                self.actor.eval()
            terminal=evidence['first_fail_substep']>0
            rr=self.rep.represent(ns)
            reward=self.rep.compute_wm_reward_from_reference(rr,ns[:,:7],self.rep.joint_state(rr),
                                       action,prev,*bank.body_state(frames+1))
            reward=self.policy.wm_env.contact_reward(reward, rr, frames+1, ctx)
            if force_reward:
                reward = self.policy.wm_env.force_adjusted_reward(reward, evidence['peak_force_n'], frames)
            rows.append(TensorDict(dict(state=s,next_state=ns,prev_action=prev,action=action,sim_ctx=ctx,
                         history=hist.flatten(1),motion_time=frames,valid=valid,terminated=terminal,
                         truncated=torch.full_like(valid,k==self.steps-1),reward=reward),batch_size=(self.n,)))
            if raw_path is not None:
                fields=dict(qpos=q,qvel=v,next_qpos=q1,next_qvel=v1,raw=raw,clipped=action,
                            physical_target=self.dyn.proc(action),valid=valid,active=alive,frame=frames,
                            prev_action=prev,first_fail_substep=evidence['first_fail_substep'],reason=evidence['reason'],
                            physics_steps=evidence['physics_steps'],overflow=evidence['overflow'])
                fields.update({'sub_'+key:value for key,value in evidence['substeps'].items()})
                records.append({n:t.detach().cpu().numpy().copy() for n,t in fields.items()})
            failures+=alive & terminal
            alive=valid & ~terminal
            clean=self.sense(q1,v1,action)
            hist=torch.cat([hist[:,1:],clean[:,None]],1)
            noisy=torch.cat([noisy[:,1:],self.robot.add_proprio_noise(clean)[:,None]],1)
            prev,frames=action,frames+1
            if not alive.any():
                break
        if raw_path is not None:
            raw_path.mkdir(parents=True,exist_ok=False)
            for n in records[0]:
                np.save(raw_path/(n+'.npy'),np.stack([r[n] for r in records]))
        valid_count=sum(int(r['valid'].sum()) for r in rows)
        if training and valid_count:
            for r in rows:
                ix=r['valid']
                if ix.any():
                    self.learners[7].update_normalization(r['state'][ix],r['action'][ix])
        if training:
            self.replay.append(rows)
        self.total+=valid_count
        self.simulated+=self.n*len(rows)
        return dict(valid_transitions=valid_count,cumulative_valid_transitions=self.total,
                    simulated_lane_intervals=self.n*len(rows),prefix_steps_per_lane=100,
                    prefix_invalid=prefixes_invalid,failed_lanes=int(failures.sum()),
                    start_ref_min=int(start.min()),start_ref_max=int(start.max()))

    def update(self):
        online_long=0
        if self.h32_teacher_batches:
            long_windows = [self.offline[32].sample(self.b) for _ in range(self.h32_teacher_batches)]
            metrics = self.learners[32].update(long_windows)
            if not all(torch.isfinite(value).all() for value in metrics.values()):
                raise FloatingPointError('nonfinite long-horizon world model update')
        for n in (7,1):
            batches=[]
            for _ in range(self.seven_batches if n==7 else 2):
                take=(3*self.b//4 if n==7 else self.b)
                batch=self.replay.windows(n,take)
                count=take if batch is not None else 0
                if n==7:
                    online_long+=count
                if count<self.b:
                    teacher=self.offline[n].sample(self.b-count)
                    batch=teacher if batch is None else torch.cat([batch,teacher])
                batches.append(batch)
            metrics=self.learners[n].update(batches)
            if not all(torch.isfinite(value).all() for value in metrics.values()):
                raise FloatingPointError('nonfinite world model update')
        prev=self.actor.decoder[-1].weight.detach().clone()
        stats=self.policy.update()
        out={k:float(v) for k,v in stats.items()}
        out.update(actor_max_weight_change=float((self.actor.decoder[-1].weight.detach()-prev).abs().max()),
                   wm_frozen=all(not p.requires_grad for p in self.dyn.parameters()),
                   online_seven_step_windows=online_long,total_seven_step_windows=self.seven_batches*self.b)
        if self.h32_teacher_batches:
            out['teacher_thirtytwo_step_windows'] = self.h32_teacher_batches*self.b
        if not all(np.isfinite(x) for x in out.values()):
            raise FloatingPointError(out)
        return out
