"""Reference-conditioned interaction and O1 learner bindings for free motion."""
from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np
import torch
from tensordict import TensorDict
from mjlab.tasks.tracking.mdp.commands import MotionLoader
from supermimic.envs.multi_task_world_model_env import MultiTaskWorldModelEnv
from supermimic.learners.wm_learner import WorldModelLearner
from supermimic.learners.policy_learner import ActorCriticPolicyLearner, ActorCriticPolicyLearnerCfg
from supermimic.models import Dynamics, build_mlp
from supermimic.replay_buffer import ReplayBuffer, FieldSpec
from supermimic.runners.reset_sampling import ReturnSampler, ReturnSamplerCfg
from supermimic.tasks.task_spec import make_motion_task, make_velocity_task, build_actor_obs_td

from .model import RobotRepresentation, RobotActor, B0WorldModelCfg, full_state, native_state, tensor
from .physics import make_model, ActionMap, ROOT
from .reference import load_episode


class MotionBank(MotionLoader):
    def __init__(self, refs, fk, folder, device):
        folder.mkdir(parents=True, exist_ok=False)
        arrays = {k: np.concatenate([d[k] for d in refs.values()]) for k in
                  ('qpos', 'qvel', 'root_linvel_world', 'root_angvel_world')}
        q, v = arrays['qpos'], arrays['qvel']
        fields = dict(root_pos_w=q[:, :3], root_quat_w=q[:, 3:7], joint_pos=q[:, 7:31],
                      root_ang_vel_w=arrays['root_angvel_world'], root_lin_vel_w=arrays['root_linvel_world'],
                      joint_vel=v[:, 6:30], motion_ends=np.cumsum([len(d['t']) for d in refs.values()]))
        for name, a in fields.items():
            np.save(folder / (name+'.npy'), a, allow_pickle=False)
        (folder/'joint_names.json').write_text(json.dumps(fk.joint_names))
        (folder/'motion_names.json').write_text(json.dumps(list(refs)))
        super().__init__(str(folder), fk, device)
        frames = torch.arange(self.time_step_total, device=device)
        self.bodies = super().body_state(frames)
        self.qpos, self.qvel = tensor(q, device), tensor(v, device)
        self.prev = tensor(np.concatenate([d['last_action'] for d in refs.values()]), device)

    def body_state(self, frames):
        return tuple(field[frames] for field in self.bodies)


class MotionCommand:
    def __init__(self, motion):
        self.motion, self.motion_anchor_body_index = motion, 0

    def get_term(self, name):
        if name != 'motion':
            raise KeyError(name)
        return self


class FreeRun:
    def __init__(self, cfg, run_id, seed=0, device='cuda:0'):
        self.cfg, self.seed, self.device = cfg, seed, device
        torch.manual_seed(seed)
        np.random.seed(seed)
        self.updates = self.collected = 0
        self.model = make_model()
        self.map = ActionMap(self.model)
        self.refs = {name: load_episode(Path(cfg['reference_root'])/name)
                     for name in ('support', 'moving_arm', 'park')}
        self.validation = load_episode(Path(cfg['reference_root'])/'moving_arm_wm_validation')
        self.raw = ROOT/'results/raw_large/b0'/run_id
        self.raw.mkdir(exist_ok=False)
        self.rep = RobotRepresentation(self.model, device)
        self.motion = MotionBank(self.refs, self.rep.fk, self.raw/'motion', device)
        self.starts = torch.nn.functional.pad(self.motion.motion_ends[:-1], (1, 0))
        self.ctx_dim = 1  # fixed nominal model, all samples have the same context
        self.dyn = Dynamics(self.rep, 23, self.ctx_dim, tensor(self.map.scale, device),
                            tensor(self.map.offset, device), tuple(cfg['wm_hidden'])).to(device)
        goal_width = 10 * (2 * 24 + 9)
        motion_task = make_motion_task(self.rep, goal_width)
        velocity_task = make_velocity_task((-1.5, 1.5), (-.5, .5), (-3.14, 3.14),
                                           25, (.5, .5, .785), device)
        self.actor = RobotActor(77, 23, [motion_task, velocity_task], {'motion': 1., 'velocity': 0.},
                      32, tuple(cfg['actor_hidden']), .1, 10).to(device)
        self.critic = build_mlp(self.rep.rep_state_dim + goal_width + 1,
                                tuple(cfg['critic_hidden']), 1).to(device)
        self.n = cfg['worlds']
        self.wmc = B0WorldModelCfg(batch_size=cfg['wm_batch'], num_batches=cfg['wm_batches'])
        self.pc = ActorCriticPolicyLearnerCfg(batch_size=cfg['actor_batch'], horizon=32)
        self.wml = WorldModelLearner(self.dyn, self.rep, self.wmc, device)
        widths = dict(state=61, next_state=61, action=23, prev_action=23, actor_obs=77, sim_ctx=1)
        schema = {k: FieldSpec(v) for k, v in widths.items()}
        schema.update({k: FieldSpec(dtype=torch.bool) for k in ('terminated', 'truncated', 'teacher')})
        schema['motion_time'] = FieldSpec(dtype=torch.long)
        self.replay = ReplayBuffer(schema, cfg['buffer_size'], self.n, device)
        terms = {k: SimpleNamespace(params={'threshold': val}) for k, val in
                 [('anchor_pos', .10), ('anchor_ori', .12)]}
        env = SimpleNamespace(num_actions=23, unwrapped=SimpleNamespace(step_dt=.02,
                              command_manager=MotionCommand(self.motion)),
                              cfg=SimpleNamespace(rewards={'tracking': SimpleNamespace(weight=5.)},
                                                  terminations=terms))
        self.wenv = MultiTaskWorldModelEnv(self.dyn, self.rep, env, self.pc.batch_size, self.replay,
                                           [motion_task], 10, .05, device)
        self.policy = ActorCriticPolicyLearner(self.actor, self.critic, self.wenv, self.pc, device)
        self.sampler = ReturnSampler(ReturnSamplerCfg(), 21, self.motion.time_step_total, self.n,
                                     self.wenv.max_step_reward, device)
        self.weights = torch.ones(21, device=device)
        self.ref_states = full_state(self.motion.qpos, self.motion.qvel)
        self.ref_sensor = self.sensor(self.ref_states, self.motion.prev)
        self.plant = None

    def sensor(self, state, prev):
        rep = self.rep.represent(state)
        return self.rep.compute_actor_sensor(rep, None, aux_state=state[..., :7],
                              joint_state=self.rep.joint_state(rep), last_action=prev)

    def actor_obs(self, state, clock, history):
        _, goal = self.rep.compute_wm_goal(self.motion, clock, state[..., :7])
        return build_actor_obs_td({'motion': goal}, history)

    def transition(self, s, ns, prev, a, clock, terminal, truncated, teacher):
        return TensorDict(dict(state=s, next_state=ns, prev_action=prev, action=a, motion_time=clock,
                 actor_obs=self.sensor(s, prev), sim_ctx=torch.ones_like(s[:, :1]), terminated=terminal,
                 truncated=truncated, teacher=torch.full_like(terminal, teacher)), batch_size=[self.n])

    @torch.no_grad()
    def warmstart(self):
        # Each lane sees a single complete teacher episode; no validation frames enter replay.
        datasets = list(self.refs.values())
        length = len(datasets[0]['action_clipped'])
        if any(len(d['action_clipped']) != length for d in datasets):
            raise ValueError('teacher warmstart requires equal free clip lengths')
        lanes = torch.arange(self.n, device=self.device) % len(datasets)
        begin = self.starts[lanes]
        A = tensor(np.stack([d['action_clipped'] for d in datasets]), self.device)
        for i in range(length):
            clock = begin + i
            term = torch.zeros_like(clock, dtype=torch.bool)
            td = self.transition(self.ref_states[clock], self.ref_states[clock+1], self.motion.prev[clock],
                                 A[lanes, i], clock, term, term | (i == length-1), True)
            self.replay.insert(td)
        idx = torch.cat([torch.arange(start, end-1, device=self.device)
                         for start, end in zip(self.starts.tolist(), self.motion.motion_ends.tolist())])
        self.wml.update_normalization(self.ref_states[idx], A.flatten(0, 1))
        self.actor.train()
        sensor = self.ref_sensor[idx]
        self.actor.update_normalization(self.actor_obs(self.ref_states[idx], idx, sensor[:,None,:].expand(-1,10,-1)))
        self.actor.eval()

    def reference_history(self, frames):
        ids = torch.searchsorted(self.motion.motion_ends, frames, right=True)
        past = frames[:, None] + torch.arange(-9, 1, device=self.device)
        past = past.maximum(self.starts[ids, None])
        clean = self.ref_sensor[past]
        return self.rep.add_proprio_noise(clean)

    @torch.no_grad()
    def start_plant(self):
        from .research_env import ResearchPlant
        self.plant = ResearchPlant(make_model(), self.n, self.device)
        self.frames = self.starts[torch.arange(self.n, device=self.device) % len(self.refs)].clone()
        self.plant.reset(self.motion.qpos[self.frames], self.motion.qvel[self.frames])
        self.prev = self.motion.prev[self.frames].clone()
        self.history = self.reference_history(self.frames)
        self.episode_id = torch.arange(self.n, device=self.device)

    @torch.no_grad()
    def collect(self, count, save=False):
        self.actor.eval()
        records = []
        rewards, fail_count = [], 0
        plant = self.plant
        for _ in range(count):
            q0, v0 = plant.data.qpos[:].clone(), plant.data.qvel[:].clone()
            s = full_state(q0, v0)
            obs = self.actor_obs(s, self.frames, self.history)
            raw = self.actor.raw(obs) + torch.randn_like(self.prev) * self.pc.noise
            a = raw.clamp(-1, 1)
            bad = plant.step(a, record_substeps=save)
            q1, v1 = plant.data.qpos[:].clone(), plant.data.qvel[:].clone()
            ns = full_state(q1, v1)
            nr = self.rep.represent(ns)
            bodies = self.motion.body_state(self.frames)
            reward = self.rep.compute_wm_reward_from_reference(nr, ns[:, :7], self.rep.joint_state(nr),
                                                              a, self.prev, *bodies)
            ends = self.motion.motion_ends[torch.searchsorted(self.motion.motion_ends, self.frames, right=True)]
            end = self.frames + 1 >= ends - 1
            td = self.transition(s, ns, self.prev, a, self.frames, bad, end, False)
            self.replay.insert(td)
            weights = self.sampler.record(self.frames, reward, bad, end, torch.zeros_like(end))
            if weights is not None:
                self.weights = weights
            if save:
                records.append({k: v.detach().cpu().numpy().copy() for k,v in dict(
                    qpos=q0, qvel=v0, next_qpos=q1, next_qvel=v1, raw=raw, clipped=a,
                    physical_target=self.dyn.proc(a), last_ctrl=plant.data.ctrl[:], last_force=plant.data.actuator_force[:],
                    substeps=plant.substeps, prev_action=self.prev, frame=self.frames, episode_id=self.episode_id,
                    terminated=bad, truncated=end, reward=reward).items()})
            self.wml.update_normalization(s, a)
            self.actor.train()
            self.actor.update_normalization(obs)
            self.actor.eval()
            self.prev = a
            self.frames = self.frames + 1
            sensor = self.rep.add_proprio_noise(self.sensor(ns, a))
            self.history = torch.cat([self.history[:, 1:], sensor[:, None]], 1)
            ids = torch.where(bad | end)[0]
            if len(ids):
                bins = torch.multinomial(self.weights, len(ids), replacement=True)
                new = ((bins + torch.rand(len(ids), device=self.device)) * self.motion.time_step_total /
                       len(self.weights)).long().clamp_max(self.motion.time_step_total-1)
                near_end = self.motion.motion_ends[torch.searchsorted(self.motion.motion_ends, new, right=True)] - 2
                new = new.minimum(near_end)
                plant.reset(self.motion.qpos[new], self.motion.qvel[new], ids)
                self.frames[ids] = new
                self.prev[ids] = self.motion.prev[new]
                self.history[ids] = self.reference_history(new)
                self.episode_id[ids] += self.n
            rewards.append(reward.mean())
            fail_count += int(bad.sum())
        if save:
            out = self.raw/f'policy_transitions_{self.collected:09d}'
            out.mkdir()
            for name in records[0]:
                np.save(out/(name+'.npy'), np.stack([row[name] for row in records]))
        self.collected += count * self.n
        return dict(transitions=self.collected, mean_step_reward=torch.stack(rewards).mean().item(),
                    physical_failures=fail_count)

    def update(self):
        batches = [self.replay.sample(self.wmc.horizon, self.wmc.batch_size) for _ in range(self.wmc.num_batches)]
        for td in batches:
            # No one-tick or cross-reset shifts are admissible in the supervised targets.
            if not torch.equal(td['next_state'][:, :-1], td['state'][:, 1:]):
                raise ValueError('replay successor mismatch')
        wm = self.wml.update(batches)
        before = self.actor.decoder[-1].weight.detach().clone()
        pol = self.policy.update()
        delta = (before-self.actor.decoder[-1].weight).abs().max()
        self.updates += 1
        stats = {k: float(v) for k,v in (wm | pol).items()}
        stats.update(actor_weight_max_delta=float(delta.detach()),
                     frozen_wm=all(not p.requires_grad for p in self.dyn.parameters()),
                     sampled_teacher_fraction=float(torch.stack([td['teacher'].float().mean() for td in batches]).mean()))
        if not all(np.isfinite(x) for x in stats.values()):
            raise FloatingPointError(f'nonfinite learning update {self.updates}: {stats}')
        return stats

    def policy_factory(self, reference_id, episode):
        index = self.motion.motion_names.index(reference_id)
        start = int(self.starts[index])
        prev = self.motion.prev[start:start+1].clone()
        history = None
        self.actor.eval()
        @torch.no_grad()
        def action(q, v, frame):
            nonlocal prev, history
            s = full_state(tensor(q[None], self.device), tensor(v[None], self.device))
            sensor = self.sensor(s, prev)[:, None]
            history = sensor.expand(-1, 10, -1) if history is None else torch.cat([history[:, 1:], sensor], 1)
            clock = torch.tensor([start+frame], device=self.device)
            prev = self.actor(self.actor_obs(s, clock, history))
            return prev[0].cpu().numpy()
        return action

    @torch.no_grad()
    def rollout(self, qpos, qvel, actions):
        q, v = tensor(qpos, self.device), tensor(qvel, self.device)
        s = full_state(q,v)
        r, aux, ctx = self.rep.represent(s), s[:, :7], torch.ones_like(s[:, :1])
        qq, vv = [], []
        for a in tensor(actions, self.device).unbind(1):
            aux, r = self.dyn(r, a, aux, ctx)
            # B0-03 omits passive door dynamics while physically out of contact.
            nq, nv = native_state(self.rep.reconstruct_full_state(aux, r), q[:, -1], v[:, -1])
            qq.append(nq)
            vv.append(nv)
        return torch.stack(qq,1).cpu().numpy(), torch.stack(vv,1).cpu().numpy()
