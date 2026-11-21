"""O1 GenCoord and research FK with the two physical prismatic fingers."""
from dataclasses import dataclass

import numpy as np
import torch
from mjlab.utils.forward_kinematics import ForwardKinematics
from mjlab.utils.lab_api.math import quat_apply, quat_apply_inverse, quat_mul
from supermimic.learners.wm_learner import WorldModelLearnerCfg
from supermimic.representations import GenCoordRepresentation
from supermimic.models import MultiEncoderAE

from .physics import FINGERS, LIMBS, WHEELS


def tensor(array, device):
    return torch.tensor(np.asarray(array), device=device, dtype=torch.float32)


def full_state(qpos, qvel):
    # MuJoCo free joint uses world translation and body-frame angular velocity.
    return torch.cat([qpos[..., :31], qvel[..., :3], quat_apply(qpos[..., 3:7], qvel[..., 3:6]),
                      qvel[..., 6:30]], dim=-1)


def native_state(state, door_q, door_v):
    q = torch.cat([state[..., :31], door_q[..., None]], dim=-1)
    v = torch.cat([state[..., 31:34], quat_apply_inverse(q[..., 3:7], state[..., 34:37]),
                   state[..., 37:], door_v[..., None]], dim=-1)
    return q, v


class RobotFK:
    """Extend the pinned hinge FK at the gripper parent with measured model transforms."""
    def __init__(self, model, device):
        self.names = ['m1_base_link', *[f'm1_{limb}_FOOT_LINK' for limb in LIMBS],
                      'piper_link3', 'piper_link5', 'piper_gripper_base']
        rows = torch.tensor([model.body(n).id for n in self.names])
        joints = [j for j in range(model.njnt) if 7 <= model.jnt_qposadr[j] < 31]
        self.joint_names = [model.joint(j).name for j in joints]
        self.hinges = ForwardKinematics(model, rows, torch.tensor(model.jnt_qposadr[joints]),
                                        torch.arange(len(rows)), device=device)
        self.wheel_mask = tensor([float(n not in WHEELS) for n in self.joint_names], device)
        finger_bodies = [model.body(f'piper_gripper_link{i}') for i in (1, 2)]
        self.local_pos = tensor([b.pos for b in finger_bodies] + [model.site('p4_grasp').pos], device)
        self.local_quat = tensor([b.quat for b in finger_bodies] + [[1, 0, 0, 0]], device)
        self.local_axis = tensor([model.joint(n).axis for n in FINGERS] + [[0, 0, 0]], device)
        self.finger_zero = tensor([model.qpos0[model.joint(n).qposadr.item()] for n in FINGERS], device)
        self.names += ['piper_gripper_link1', 'piper_gripper_link2', 'site:p4_grasp']

    def __call__(self, root, quat, q, lin, ang, v):
        # Wheel centers have zero hinge-anchor offsets. Remove phase for reward
        # orientation, keep actual angular speed for the wheel velocity target.
        p, r, u, w = self.hinges(root, quat, q * self.wheel_mask, lin, ang, v)
        palm = r[..., -1:, :].expand(*r.shape[:-2], 3, 4)
        orientation = quat_mul(palm, self.local_quat.expand_as(palm))
        axis = quat_apply(orientation, self.local_axis.expand_as(orientation[..., :3]))
        displacement = torch.nn.functional.pad(q[..., -2:] - self.finger_zero, (0, 1))
        speed = torch.nn.functional.pad(v[..., -2:], (0, 1))
        delta = quat_apply(palm, self.local_pos.expand_as(axis)) + axis * displacement.unsqueeze(-1)
        omega = w[..., -1:, :].expand_as(delta)
        return (torch.cat([p, p[..., -1:, :] + delta], -2), torch.cat([r, orientation], -2),
                torch.cat([u, u[..., -1:, :] + torch.linalg.cross(omega, delta) + axis * speed.unsqueeze(-1)], -2),
                torch.cat([w, omega], -2))


@dataclass
class B0WorldModelCfg(WorldModelLearnerCfg):
    nominal_error_finger_pos: float = .002
    nominal_error_finger_vel: float = .05


class RobotRepresentation(GenCoordRepresentation):
    LOSS_WEIGHT_CONFIG = {**GenCoordRepresentation.LOSS_WEIGHT_CONFIG,
                          'finger_pos': 'nominal_error_finger_pos', 'finger_vel': 'nominal_error_finger_vel'}

    def __init__(self, model, device):
        super().__init__(24, tensor(model.key('home').qpos[7:31], device))
        self.fk = RobotFK(model, device)
        self.actor_obs_mode = 'proprio'
        self.dt, self.substep_coeff = .02, .55
        bounds = self.proprio_noise_bounds(23, device)
        bounds[6+22:6+24] = .0001
        bounds[6+24+22:6+48] = .005
        self.register_buffer('_proprio_noise_bounds', bounds)
        # Output expressed in rad/s for hinge increments and m/s for fingers.
        self.register_buffer('velocity_units', tensor([1.] * 28 + [.02, .02], device))
        limits = model.jnt_range[[model.joint(n).id for n in self.fk.joint_names]]
        self._soft_joint_pos_limits = tensor(limits, device)

    def apply_prediction(self, aux_state, curr_rep_state, prediction, dt):
        return super().apply_prediction(aux_state, curr_rep_state, prediction * self.velocity_units, dt)

    def loss_blocks(self, rep_state, aux_state):
        blocks = super().loss_blocks(rep_state, aux_state)
        for quantity in ('pos', 'vel'):
            name = 'joint_' + quantity
            blocks['finger_' + quantity] = blocks[name][..., -2:]
            blocks[name] = blocks[name][..., :-2]
        return blocks


class RobotActor(MultiEncoderAE):
    """Clamp the command at the same boundary in imagination and physics."""
    def forward(self, obs_td):
        return self.raw(obs_td).clamp(-1., 1.)

    def raw(self, obs_td):
        return super().forward(obs_td)


class EffortScaledActor(RobotActor):
    """Use O1 effort/gain network-output units, preserving the physical replay schema."""
    def set_servo_units(self, model, mapping, device):
        home = model.key('home').qpos[mapping.q].copy()
        home[12:16] = 0.
        home[-1] *= 2
        forces = model.actuator_forcerange[mapping.actuator_ids, 1]
        gains = model.actuator_gainprm[mapping.actuator_ids, 0]
        units = .25 * forces / gains
        # The policy commands full opening, while the motor servo uses one finger.
        units[-1] *= 2.
        self.register_buffer('standard_action', tensor(units / mapping.scale, device))
        self.register_buffer('home_action', tensor((home-mapping.offset)/mapping.scale, device))

    def raw(self, obs_td):
        return self.home_action + self.standard_action * super().raw(obs_td)
