"""The B0-03 proprio actor on a ragged bank of real passive-door references."""
from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td, make_motion_task, make_velocity_task
from supermimic.representations import GOAL_FRAME_STRIDE, NUM_GOAL_FRAMES

from .model import EffortScaledActor, RobotActor, RobotRepresentation, full_state, tensor
from .physics import ActionMap, make_model
from . import endpoint_policy


PRIVILEGED_TRANSLATION = "privileged_reference_translation"
APPROACH_LEG_WHEEL = "privileged_translation_approach_leg_wheel_residual"
APPROACH_WHEEL = "privileged_translation_approach_wheel_residual"
PRIVILEGED_DOOR_ANGLE = "privileged_reference_translation_and_door_angle"


STANCE_ARM = "reference_translation_arm_map"
TRANSLATION_STANCE_ARM = "privileged_reference_translation_with_arm_map"
DOOR_STANCE_ARM = "privileged_reference_translation_and_door_angle_with_arm_map"
ARM_MAP_BASES = {STANCE_ARM: "proprio_motion", TRANSLATION_STANCE_ARM: PRIVILEGED_TRANSLATION,
                 DOOR_STANCE_ARM: PRIVILEGED_DOOR_ANGLE}


def actor_goal_schema(cfg):
    schema = cfg.get("actor_goal_schema", "proprio_motion")
    if schema in endpoint_policy.SCHEMAS:
        return schema
    if ARM_MAP_BASES.get(schema, schema) not in ("proprio_motion", PRIVILEGED_TRANSLATION, PRIVILEGED_DOOR_ANGLE, APPROACH_WHEEL, APPROACH_LEG_WHEEL):
        raise ValueError(f"Unsupported actor goal schema {schema!r}")
    return schema


class DoorMotions:
    """One clock per episode. Partial terminal states stay in the raw record."""
    def __init__(self, paths, rep, device, *, actor_schema="proprio_motion"):
        self.actor_schema = actor_goal_schema({"actor_goal_schema": actor_schema})
        self.ids, self.starts, self.metas = {}, {}, {}
        q, v, starts, ends = [], [], [], []
        approach = []
        endpoint_clock = []
        for path in map(Path, paths):
            meta = json.loads((path / 'metadata.json').read_text())
            if not (meta['finished'] and meta['held_action_replay'] and meta['success'] and meta['wm_split']=='train'
                    and meta.get('eligible_as_reference', True)):
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
            if self.actor_schema in endpoint_policy.SCHEMAS:
                endpoint_clock.append(endpoint_policy.reference_clock(path,meta,n,self.actor_schema))
            if self.actor_schema in (APPROACH_WHEEL, APPROACH_LEG_WHEEL):
                phase = np.load(path / 'phase.npy')[:n]
                eligible = np.asarray(meta['phases'])[phase] == 'approach_base'
                approach.append(np.r_[eligible, False])
        self.base_schema = ARM_MAP_BASES.get(self.actor_schema, self.actor_schema)
        if self.actor_schema in ARM_MAP_BASES:
            from .stance_arm import ReferenceArmMap
            # Only the two given training motions (or the registered segments)
            # enter this table. All roots used during rollout are supplied by aux.
            model = make_model()
            self.reference_arm_map = tensor(np.concatenate([ReferenceArmMap(model, clip).gain for clip in q]), device)
        if endpoint_clock:
            self.endpoint_clock=tensor(np.concatenate(endpoint_clock),device)
        if approach:
            self.approach = tensor(np.concatenate(approach), device)
        self.motion_ends = torch.tensor(ends,device=device)
        self.motion_starts = torch.tensor(starts,device=device)
        self.qpos = tensor(np.concatenate(q),device)
        self.qvel = tensor(np.concatenate(v),device)
        self.root_pos_w = self.qpos[:, :3]
        self.root_quat_w = self.qpos[:, 3:7]
        self.joint_pos = self.qpos[:, 7:31]
        self.joint_vel = self.qvel[:, 6:30]
        self.state = full_state(self.qpos,self.qvel)
        self._body = rep.fk(self.root_pos_w,self.root_quat_w,self.joint_pos,
                            self.state[:,31:34],self.state[:,34:37],self.joint_vel)

    def body_state(self, frames):
        return tuple(a[frames] for a in self._body)

    def goals(self, rep, frames, aux, door_angle=None):
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
        wm = mask(wm,(48,3,6))
        actor = mask(actor,(48,6))
        if self.base_schema in (PRIVILEGED_TRANSLATION, PRIVILEGED_DOOR_ANGLE, APPROACH_WHEEL, APPROACH_LEG_WHEEL):
            # Keep the 540 trained columns in place. WM columns 480:510 are
            # ten reference-root positions expressed in the current root frame.
            actor = torch.cat((actor, wm[:, 480:510]), dim=-1)
        if self.base_schema == PRIVILEGED_DOOR_ANGLE:
            if door_angle is None or door_angle.shape != frames.shape:
                raise ValueError("A current measured or imagined hinge angle is required for each actor observation")
            actor = torch.cat((actor, (door_angle - self.qpos[frames, 31]).unsqueeze(-1)), dim=-1)
        if self.actor_schema in (APPROACH_WHEEL, APPROACH_LEG_WHEEL):
            actor = torch.cat((actor, self.approach[frames, None]), dim=-1)
        if self.actor_schema in ARM_MAP_BASES:
            shift = self.root_pos_w[frames] - aux[..., :3]
            delta = torch.matmul(self.reference_arm_map[frames], shift.unsqueeze(-1)).squeeze(-1)
            actor = torch.cat((actor, delta.clamp(-.05, .05)), dim=-1)
        if self.actor_schema in endpoint_policy.SCHEMAS:
            if door_angle is None or door_angle.shape != frames.shape:
                raise ValueError("Current hinge required for endpoint residual")
            error=(door_angle-self.qpos[frames,31]).unsqueeze(-1)
            actor=torch.cat((actor,error,self.endpoint_clock[frames]),dim=-1)
        return wm, actor


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
        baseline = base + self.standard_action * RobotActor.raw(self,obs_td)
        if hasattr(self, "planar_feedback"):
            yaw = torch.atan2(goal[:, 482], goal[:, 480])
            baseline = self.planar_feedback(baseline, obs_td["history"][:, -1, -23:],
                                            goal[:, 540:542], yaw, self.planar_rate)
        return baseline


    def forward(self, obs_td):
        action = super().forward(obs_td)
        prior = getattr(self, 'training_action_prior', None)
        if self.training and prior is not None:
            self._physical_prior_cost = prior(obs_td, action)
        return action

    def auxiliary_loss(self):
        original = super().auxiliary_loss()
        if getattr(self, 'training_action_prior', None) is None:
            return original
        return original + self._physical_prior_cost

    def auxiliary_stats(self):
        stats = super().auxiliary_stats()
        if getattr(self, 'training_action_prior', None) is not None:
            stats['physical_action_prior'] = self._physical_prior_cost.detach().mean()
        return stats


class HingeFeedbackActor(ReferenceResidualActor):
    def set_servo_units(self,model,mapping,device):
        super().set_servo_units(model,mapping,device)
        self.hinge_coefficients=torch.nn.Parameter(torch.zeros(2*endpoint_policy.KNOTS,7,device=device))

    def raw(self, obs_td):
        base=super().raw(obs_td)
        pa,pj=endpoint_policy.features(obs_td["goal_motion"])
        arm=pa@self.hinge_coefficients[:,:6]
        jaw=pj@self.hinge_coefficients[:,6:7]
        correction=torch.cat((arm,jaw),dim=1)/self.reference_scale
        return torch.cat((base[:,:16],base[:,16:]+correction),dim=1)


class StanceArmActor(ReferenceResidualActor):
    """Apply the fitted support-shift correction in physical arm-angle units."""
    def raw(self, obs_td):
        action = super().raw(obs_td)
        arm = action[..., 16:22] + self.stance_arm_gain * obs_td["goal_motion"][..., -6:] / self.reference_scale[:6]
        return torch.cat((action[..., :16], arm, action[..., 22:]), dim=-1)


class ApproachWheelActor(ReferenceResidualActor):
    """Learn four wheel corrections during the approach of the fixed reference."""
    def set_servo_units(self, model, mapping, device):
        super().set_servo_units(model, mapping, device)
        self.wheel_feedback = torch.nn.Sequential(
            torch.nn.Linear(9, 32), torch.nn.Tanh(),
            torch.nn.Linear(32, 32), torch.nn.Tanh(), torch.nn.Linear(32, 4)).to(device)
        torch.nn.init.zeros_(self.wheel_feedback[-1].weight)
        torch.nn.init.zeros_(self.wheel_feedback[-1].bias)

    def wheel_inputs(self, obs):
        goal, hist = obs["goal_motion"], obs["history"][:, -1]
        xy = goal[:, 540:542]
        yaw = torch.atan2(goal[:, 482], goal[:, 480])
        forward_window = goal[:, 567:569] - xy
        prev = hist[:, -11:-7]  # four preceding logical wheel commands
        features = torch.cat((xy / .05, yaw[:, None] / .10, forward_window / .10,
                              hist[:, 5:6] / .2, prev.mean(1, keepdim=True) / .2,
                              (prev[:, 0:1]-prev[:, 1:2]) / .2,
                              goal[:, 36:40].mean(1, keepdim=True)), dim=-1)
        # Registered nominal root bounds (<0.21 mm and 0.00084 rad) from the
        # frozen seed0 nominal trajectories. Ramp up over the next equal band.
        error = torch.maximum(xy.norm(dim=-1) / .001, yaw.abs() / .002)
        weight = goal[:, -1] * (error - 1).clamp(0, 1)
        return features, weight[:, None]

    def raw(self, obs_td):
        baseline = super().raw(obs_td)
        features, weight = self.wheel_inputs(obs_td)
        delta = weight * self.wheel_feedback(features) / 6.  # fitted in rad/s
        return torch.cat((baseline[:, :12], baseline[:, 12:16] + delta, baseline[:, 16:]), dim=-1)


class ApproachLegWheelActor(ApproachWheelActor):
    """Add one learned yaw-trim rate to the fitted approach wheel feedback."""
    def set_servo_units(self, model, mapping, device):
        super().set_servo_units(model, mapping, device)
        from .approach_legs import yaw_trim_vector
        gain = tensor(yaw_trim_vector(model) / mapping.scale[:12], device)
        self.register_buffer("leg_trim_gain", gain)
        self.register_buffer("leg_trim_projection", gain / gain.square().sum())
        self.trim_rate = torch.nn.Sequential(torch.nn.Linear(10, 32), torch.nn.Tanh(),
                                            torch.nn.Linear(32, 1), torch.nn.Tanh()).to(device)

    def trim_inputs(self, obs):
        x, initial_gate = self.wheel_inputs(obs)
        previous = obs["history"][:, -1, -23:-11] @ self.leg_trim_projection
        return torch.cat((x, previous[:, None] / .1), dim=-1), previous[:, None], initial_gate

    def raw(self, obs_td):
        baseline = super().raw(obs_td)
        x, previous, gate = self.trim_inputs(obs_td)
        active = obs_td["goal_motion"][:, -1:]
        rate = self.trim_rate(x) * .08  # rad/s of body yaw trim
        desired = (previous + active * .02 * rate).clamp(-.27925, .27925)
        # The physical approach teacher retains its final stance after parking.
        carry = (previous.abs() / .002 - 1).clamp(0, 1)
        if self.approach_only:
            carry = carry * active
        enabled = torch.maximum(gate, carry)
        residual = enabled * (desired - (baseline[:, :12] @ self.leg_trim_projection)[:, None])
        return torch.cat((baseline[:, :12] + residual * self.leg_trim_gain, baseline[:, 12:]), dim=-1)


def _mask_normalized_motion_padding(_normalizer, inputs, normalized):
    """Keep the six-dimensional rotation sentinel neutral after normalization."""
    joint_width = NUM_GOAL_FRAMES * 48
    raw_rotation = inputs[0][..., joint_width:].unflatten(-1, (NUM_GOAL_FRAMES, 6))
    # The two columns of a valid rotation matrix cannot both be zero.
    valid = raw_rotation.ne(0).any(-1, keepdim=True)
    joints, rotation = normalized.split((joint_width, NUM_GOAL_FRAMES * 6), dim=-1)
    joints = joints.unflatten(-1, (NUM_GOAL_FRAMES, 48)).masked_fill(~valid, 0)
    rotation = rotation.unflatten(-1, (NUM_GOAL_FRAMES, 6)).masked_fill(~valid, 0)
    return torch.cat((joints.flatten(-2), rotation.flatten(-2)), dim=-1)


def build_actor(rep, cfg, model, device):
    task = make_motion_task(rep,570)
    schema = actor_goal_schema(cfg)
    if schema in (PRIVILEGED_TRANSLATION, PRIVILEGED_DOOR_ANGLE, APPROACH_WHEEL, APPROACH_LEG_WHEEL):
        task = replace(task, goal_dim=570 if schema == PRIVILEGED_TRANSLATION else 571,
                       extract_training_goal=lambda motion, t, aux: motion.goals(rep, t, aux)[1])
    if schema in ARM_MAP_BASES:
        dim = {"proprio_motion": 540, PRIVILEGED_TRANSLATION: 570, PRIVILEGED_DOOR_ANGLE: 571}[ARM_MAP_BASES[schema]]
        task = replace(task, goal_dim=dim+6,
                       extract_training_goal=lambda motion, t, aux: motion.goals(rep, t, aux)[1])
    if schema in endpoint_policy.SCHEMAS:
        task = replace(task, goal_dim=545 if schema==endpoint_policy.TERMINAL else 544, extract_training_goal=lambda motion,t,aux: motion.goals(rep,t,aux)[1])
    velocity = make_velocity_task((-1.5,1.5),(-.5,.5),(-3.14,3.14),25,(.5,.5,.785),device)
    actor_type = {None:EffortScaledActor,REFERENCE_RESIDUAL:ReferenceResidualActor}[cfg.get("actor_parameterization")]
    if schema in (APPROACH_WHEEL, APPROACH_LEG_WHEEL):
        if actor_type is not ReferenceResidualActor:
            raise ValueError("Wheel feedback requires a reference-residual base")
        actor_type = ApproachLegWheelActor if schema == APPROACH_LEG_WHEEL else ApproachWheelActor
    if schema in ARM_MAP_BASES:
        if actor_type is not ReferenceResidualActor:
            raise ValueError("Arm map requires the reference residual base")
        actor_type = StanceArmActor
    if schema in endpoint_policy.SCHEMAS:
        if actor_type is not ReferenceResidualActor:
            raise ValueError("Hinge feedback requires the reference residual Actor")
        actor_type=HingeFeedbackActor
    actor = actor_type(77,23,[task,velocity],{'motion':1.,'velocity':0.},
                              32,tuple(cfg['actor_hidden']),.1,10).to(device)
    actor.set_servo_units(model,ActionMap(model),device)
    if cfg.get("neutral_normalized_goal_padding"):
        if actor_type is not EffortScaledActor or schema != "proprio_motion":
            raise ValueError("Normalized goal padding is defined for the standard 540-column motion actor")
        actor.goal_normalizers["motion"].register_forward_hook(_mask_normalized_motion_padding)
    if "planar_stance_rate" in cfg:
        if schema not in (PRIVILEGED_TRANSLATION, TRANSLATION_STANCE_ARM):
            raise ValueError("Planar feedback needs the ten privileged XYZ slots")
        from .stance_base import PlanarStanceFeedback
        actor.planar_feedback = PlanarStanceFeedback(model).to(device)
        actor.planar_rate = float(cfg["planar_stance_rate"])
    if schema == APPROACH_LEG_WHEEL:
        actor.approach_only = cfg.get("trim_only_in_supervised_phase", False)
    if schema in ARM_MAP_BASES:
        actor.stance_arm_gain = float(cfg["stance_arm_gain"])
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
    cfg = dict(weights['cfg'])
    bank = DoorMotions(episode_paths,rep,device,actor_schema=actor_goal_schema(cfg))
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
            _, goal = bank.goals(rep,torch.tensor([frame],device=device),q[-1:,:7],q[-1:,31])
            obs = build_actor_obs_td({'motion':goal},hist[None])
            return actor.raw(obs)[0].detach().cpu().numpy()
    return action
