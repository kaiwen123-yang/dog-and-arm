"""The B0-03 proprio actor on a ragged bank of real passive-door references."""
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td, make_motion_task, make_velocity_task
from supermimic.representations import GOAL_FRAME_STRIDE, NUM_GOAL_FRAMES

from .model import EffortScaledActor, RobotActor, RobotRepresentation, full_state, tensor
from .physics import ActionMap, make_model


class DoorMotions:
    """One clock per episode. Partial terminal states stay in the raw record."""
    def __init__(self, paths, rep, device):
        self.ids, self.starts, self.metas = {}, {}, {}
        q, v, acts, starts, ends = [], [], [], [], []
        for path in map(Path, paths):
            meta = json.loads((path / 'metadata.json').read_text())
            if not (meta['finished'] and meta['held_action_replay'] and meta['success'] and meta['wm_split']=='train'):
                raise ValueError(f'Expected complete successful held-target training reference: {path}')
            valid = np.load(path/'valid_full_interval.npy')
            n = int(valid.sum())
            if not valid[:n].all() or valid[n:].any() or n < 1:
                raise ValueError(f'Noncontiguous reference at {path}')
            if path.name in self.ids:
                raise ValueError(f'Duplicate reference ID {path.name}')
            start = ends[-1] if ends else 0
            self.ids[path.name], self.starts[path.name] = len(ends), start
            self.metas[path.name] = meta
            starts.append(start)
            ends.append(start+n+1)
            q.append(np.load(path/'qpos.npy',mmap_mode='r')[:n+1])
            v.append(np.load(path/'qvel.npy',mmap_mode='r')[:n+1])
            acts.append(np.load(path/'action_clipped.npy',mmap_mode='r')[:n])
        self.motion_ends = torch.tensor(ends,device=device)
        self.motion_starts = torch.tensor(starts,device=device)
        self.qpos = tensor(np.concatenate(q),device)
        self.qvel = tensor(np.concatenate(v),device)
        self.actions = [tensor(a,device) for a in acts]
        self.root_pos_w = self.qpos[:, :3]
        self.root_quat_w = self.qpos[:, 3:7]
        self.joint_pos = self.qpos[:, 7:31]
        self.joint_vel = self.qvel[:, 6:30]
        self.state = full_state(self.qpos,self.qvel)
        self._body = rep.fk(self.root_pos_w,self.root_quat_w,self.joint_pos,
                            self.state[:,31:34],self.state[:,34:37],self.joint_vel)

    def body_state(self, frames):
        return tuple(a[frames] for a in self._body)

    def goals(self, rep, frames, aux):
        wm, actor = rep.compute_wm_goal(self, frames, aux)
        ends = self.motion_ends[torch.searchsorted(self.motion_ends,frames,right=True)]
        offsets = torch.arange(NUM_GOAL_FRAMES,device=frames.device)*GOAL_FRAME_STRIDE
        valid = frames[:,None]+offsets < ends[:,None]
        # The pretrained encoder keeps its 10-frame shape. Invalid future slots
        # contain zero features, with no observations drawn from adjacent clips.
        def mask(values, widths):
            chunks = values.split([NUM_GOAL_FRAMES*w for w in widths],-1)
            return torch.cat([(chunk.unflatten(-1,(NUM_GOAL_FRAMES,w))*valid[:,:,None]).flatten(1)
                              for chunk,w in zip(chunks,widths)],-1)
        return mask(wm,(48,3,6)), mask(actor,(48,6))


REFERENCE_RESIDUAL = "motion_reference_arm_jaw_residual"


class ReferenceResidualActor(EffortScaledActor):
    """Leg and wheel commands retain their home base. Arm and jaw track the given motion."""
    def set_servo_units(self, model, mapping, device):
        super().set_servo_units(model,mapping,device)
        self.register_buffer("reference_offset",tensor(mapping.offset[16:],device))
        self.register_buffer("reference_scale",tensor(mapping.scale[16:],device))

    def raw(self, obs_td):
        # Official motion slot: current joint positions are the first 24 entries.
        # Cache-free so physical feedback and H32 imagination use the same clock.
        goal = obs_td["goal_motion"]
        pose = torch.cat((goal[...,16:22],goal[...,22:23]-goal[...,23:24]),-1)
        base = torch.cat((self.home_action[:16].expand_as(goal[...,:16]),
                          (pose-self.reference_offset)/self.reference_scale),-1)
        return base + self.standard_action * RobotActor.raw(self,obs_td)


def build_actor(rep, cfg, model, device):
    task = make_motion_task(rep,570)
    velocity = make_velocity_task((-1.5,1.5),(-.5,.5),(-3.14,3.14),25,(.5,.5,.785),device)
    actor_type = {None:EffortScaledActor,REFERENCE_RESIDUAL:ReferenceResidualActor}[cfg.get("actor_parameterization")]
    actor = actor_type(77,23,[task,velocity],{'motion':1.,'velocity':0.},
                              32,tuple(cfg['actor_hidden']),.1,10).to(device)
    actor.set_servo_units(model,ActionMap(model),device)
    return actor, task


def sensor(rep, state, previous):
    physical = rep.represent(state)
    return rep.compute_actor_sensor(physical,None,aux_state=state[..., :7],
                                    joint_state=rep.joint_state(physical),last_action=previous)


@torch.no_grad()
def load_policy(checkpoint, episode_paths, device):
    weights = torch.load(checkpoint,map_location=device,weights_only=False)
    model = make_model()
    rep = RobotRepresentation(model,device)
    bank = DoorMotions(episode_paths,rep,device)
    cfg = dict(weights['cfg'])
    if 'actor_parameterization' in weights:
        cfg['actor_parameterization'] = weights['actor_parameterization']
    actor, _ = build_actor(rep,cfg,model,device)
    actor.load_state_dict(weights['actor'],strict=True)
    actor.eval()

    def action(episode_path, absolute_policy_frame, history_q, history_v, history_prev):
        name = Path(episode_path).name
        i = bank.ids[name]
        frame = bank.starts[name] + int(absolute_policy_frame)
        if frame >= int(bank.motion_ends[i]) or absolute_policy_frame < 0:
            raise IndexError(f'Reference exhausted: {name} frame {absolute_policy_frame}')
        q, v = tensor(history_q,device), tensor(history_v,device)
        hist = sensor(rep,full_state(q,v),tensor(history_prev,device))
        if hist.shape != (10,77):
            raise ValueError(f'Expected 10 real history frames, got {hist.shape}')
        with torch.no_grad():
            _, goal = bank.goals(rep,torch.tensor([frame],device=device),q[-1:,:7])
            obs = build_actor_obs_td({'motion':goal},hist[None])
            return actor.raw(obs)[0].detach().cpu().numpy()
    return action
