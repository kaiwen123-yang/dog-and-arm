"""O1 GenCoord extension for a free robot and an independent passive hinge."""
from dataclasses import dataclass

import mujoco as mj
import numpy as np
import torch
from mjlab.utils.lab_api.math import quat_apply, quat_apply_inverse, quat_mul
from supermimic.utils.gencoord_helpers import compute_gencoord_state

from .model import B0WorldModelCfg, RobotRepresentation, full_state, tensor
from .physics import ARM


SCHEMA = 'b0_contact_gencoord_v1'
CONTEXT_NAMES = ('back_side', 'ground_friction', 'finger_friction', 'hinge_frictionloss', 'hinge_damping')


def contact_state(qpos, qvel):
    if qpos.shape[-1] != 32 or qvel.shape[-1] != 31:
        raise ValueError('Expected free robot and independent passive door nq=32, nv=31')
    return torch.cat((full_state(qpos, qvel), qpos[..., 31:], qvel[..., 30:]), -1)


def contact_context(model, side, device):
    if side not in ('mobile', 'pull', 'push'):
        raise ValueError(f'Unknown door side {side}')
    adr = model.joint('door_single_hinge').dofadr.item()
    return tensor([float(side == 'push'), model.geom('preview_floor').friction[0],
                   model.geom('piper_gripper_link1_collision_0').friction[0],
                   model.dof_frictionloss[adr], model.dof_damping[adr]], device)


@dataclass
class ContactWorldModelCfg(B0WorldModelCfg):
    nominal_error_door_angle: float = np.deg2rad(2.)
    nominal_error_door_speed: float = .10


class ContactRepresentation(RobotRepresentation):
    """Robot 58, door angle/speed 2, and 15 m or unit-vector coordinates.

    The frozen hinge/handle and neutral arm transforms live in model buffers,
    shared by front and back geometries. Per-episode friction lives in sim_ctx.
    The proprio sensor, joint state and tracking reward retain the robot layout.
    """
    LOSS_WEIGHT_CONFIG = {**RobotRepresentation.LOSS_WEIGHT_CONFIG,
                          'door_angle': 'nominal_error_door_angle',
                          'door_speed': 'nominal_error_door_speed'}

    def __init__(self, model, device):
        super().__init__(model, device)
        self.full_state_dim = 63
        self.rep_state_dim = 75
        self.prediction_dim = 31
        # Compute space-frame screw axes and neutral displacements from the
        # actual compiled model. Only the six arm hinges move the grasp site
        # relative to the free root. No wheel/leg or passive-door parentage.
        d = mj.MjData(model)
        mj.mj_forward(model, d)
        arm = np.array([model.joint(n).id for n in ARM])
        root = model.body('m1_base_link').id
        root_R = d.xmat[root].reshape(3, 3)
        tcp = model.site('p4_grasp').id
        origins = np.vstack([d.xpos[root], d.xanchor[arm], d.site_xpos[tcp]])
        joint_q = model.jnt_qposadr[arm]
        self.register_buffer('arm_joint_cols', torch.as_tensor(joint_q-7, dtype=torch.long, device=device))
        def constant(name, value):
            self.register_buffer(name, tensor(value, device))
        constant('arm_axes', d.xaxis[arm] @ root_R)
        constant('arm_displacements', np.diff(origins, axis=0) @ root_R)
        constant('arm_neutral_q', model.qpos0[joint_q])
        tcp_quat = np.empty(4)
        mj.mju_mat2Quat(tcp_quat, (root_R.T @ d.site_xmat[tcp].reshape(3, 3)).ravel())
        constant('tcp_quat0', tcp_quat)
        hinge = model.joint('door_single_hinge')
        constant('hinge_world', d.xanchor[hinge.id])
        constant('hinge_axis', d.xaxis[hinge.id])
        constant('door_q0', model.qpos0[hinge.qposadr])
        handles = [model.site(f'door_single_{side}_handle').id for side in ('front', 'back')]
        constant('handle_offsets', d.site_xpos[handles] - d.xanchor[hinge.id])
        # Site local Z points along opposing handle normals. The vertical rod
        # axis and one face normal determine the orientation for both sides.
        constant('front_normal0', d.site_xmat[handles[0]].reshape(3, 3)[:, 2].copy())

    def tcp_pose(self, aux, joint_pos):
        xyz, quat = aux[..., :3], aux[..., 3:7]
        half = .5 * (joint_pos.index_select(-1, self.arm_joint_cols) - self.arm_neutral_q)
        turns = torch.cat((half.cos().unsqueeze(-1), half.sin().unsqueeze(-1) * self.arm_axes), -1)
        for j in range(6):
            xyz = xyz + quat_apply(quat, self.arm_displacements[j].expand_as(xyz))
            quat = quat_mul(quat, turns[..., j, :])
        xyz = xyz + quat_apply(quat, self.arm_displacements[-1].expand_as(xyz))
        return xyz, quat_mul(quat, self.tcp_quat0.expand_as(quat))

    def geometry(self, aux, joint_pos, theta):
        """Hinge in base, front/back rod centers in TCP, hinge axis and face normal in TCP."""
        tcp, tcp_quat = self.tcp_pose(aux, joint_pos)
        half = .5 * (theta - self.door_q0)
        turn = torch.cat((half.cos(), half.sin() * self.hinge_axis), -1)
        world_front = self.hinge_world + quat_apply(turn, self.handle_offsets[0].expand_as(tcp))
        world_back = self.hinge_world + quat_apply(turn, self.handle_offsets[1].expand_as(tcp))
        normal = quat_apply(turn, self.front_normal0.expand_as(tcp))
        return torch.cat((quat_apply_inverse(aux[..., 3:7], self.hinge_world - aux[..., :3]),
                          quat_apply_inverse(tcp_quat, world_front - tcp),
                          quat_apply_inverse(tcp_quat, world_back - tcp),
                          quat_apply_inverse(tcp_quat, self.hinge_axis.expand_as(tcp)),
                          quat_apply_inverse(tcp_quat, normal)), -1)

    def _combined(self, aux, robot_rep, angle, speed):
        features = self.geometry(aux, robot_rep[..., 10:34], angle)
        return torch.cat((robot_rep, angle, speed, features), -1)

    def represent(self, state):
        if state.shape[-1] != self.full_state_dim:
            raise ValueError('Contact state needs 61 robot coordinates, door angle and speed')
        robot_rep = compute_gencoord_state(state[..., :61].reshape(-1, 61)).reshape(*state.shape[:-1], 58)
        return self._combined(state[..., :7], robot_rep, state[..., 61:62], state[..., 62:63])

    def apply_prediction(self, aux_state, curr_rep_state, prediction, dt):
        aux, robot_rep = super().apply_prediction(aux_state, curr_rep_state[..., :58], prediction[..., :30], dt)
        angle, speed = curr_rep_state[..., 58:59], curr_rep_state[..., 59:60]
        # Network output measured in 0.1 rad/s increments at the passive hinge.
        dv = .1 * prediction[..., 30:31]
        next_angle = angle + dt * (speed + self.substep_coeff * dv)
        return aux, self._combined(aux, robot_rep, next_angle, speed + dv)

    def reconstruct_full_state(self, aux_state, rep_state):
        robot = super().reconstruct_full_state(aux_state, rep_state[..., :58])
        return torch.cat((robot, rep_state[..., 58:60]), -1)

    def joint_state(self, rep_state):
        return super().joint_state(rep_state[..., :58])

    def compute_wm_obs(self, rep_state, aux_state, joint_state, sim_ctx):
        return super().compute_wm_obs(rep_state[..., :58], aux_state, joint_state, sim_ctx)

    def world_frame_bodies(self, aux_state, rep_state):
        return super().world_frame_bodies(aux_state, rep_state[..., :58])

    def loss_blocks(self, rep_state, aux_state):
        blocks = super().loss_blocks(rep_state[..., :58], aux_state)
        blocks.update(door_angle=rep_state[..., 58:59], door_speed=rep_state[..., 59:60])
        return blocks


def transfer_wm(dynamics, old_state):
    """Warm start only identical hidden blocks and the 30 robot output rows.

    Input normalization is newly measured on held-action training episodes.
    Reusing first-layer coefficients with new statistics would change their
    meaning. Both the new input layer and the door velocity row start fresh.
    """
    current = dynamics.state_dict()
    copied = []
    output = f'mlp.{len(dynamics.mlp)-1}'
    for name, dest in current.items():
        if name.startswith(output + '.'):
            source = old_state[name]
            if dest.shape[0] != 31 or source.shape[0] != 30 or source.shape[1:] != dest.shape[1:]:
                raise ValueError(f'Mismatched B0-03 output {name}')
            dest[:30].copy_(source)
            copied.append(name + '[:30]')
        elif name.startswith('mlp.') and not name.startswith('mlp.0.'):
            dest.copy_(old_state[name])
            copied.append(name)
    dynamics.load_state_dict(current)
    return copied
