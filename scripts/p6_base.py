"""Finite wheel/leg references for the M1 on level ground.

World XY destinations use body origin m1_base_link. Positive v points along
body +X. Positive yaw rate is about world +Z. Only the caller writes ctrl.
"""
from __future__ import annotations

import math

import mujoco as mj
import numpy as np

from p4_fixed_door import ARM


def wheel_geometry(data, root_body, wheel_joints):
    """Signed lateral axle directions and wheel offsets, both in body axes."""
    lateral_axis = data.xmat[root_body].reshape(3, 3)[:, 1]
    axle_sign = np.sign(data.xaxis[wheel_joints] @ lateral_axis)
    offset = (data.xanchor[wheel_joints] - data.xpos[root_body]) @ lateral_axis
    return axle_sign, offset


def wheel_rates(axle_sign, lateral_offset, radius, speed, turn):
    """Fixed axle, skid-steer allocation. Lateral motion is not actuated."""
    return axle_sign * (speed - turn * lateral_offset) / radius


def signed_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


class BaseDrive:
    def __init__(self, model, data, cfg):
        self.model = model
        self.cfg = cfg
        self.body = model.body('m1_base_link').id
        root = model.joint('m1_floating_base')
        self.root_q = int(root.qposadr[0])
        self.root_v = int(root.dofadr[0])
        joints = model.actuator_trnid[:, 0]
        names = [model.joint(j).name for j in joints]
        self.wheels = np.array([i for i, n in enumerate(names) if n.endswith('_FOOT_JOINT')])
        self.legs = np.array([i for i, n in enumerate(names) if n.startswith('m1_') and not n.endswith('_FOOT_JOINT')])
        self.arms = np.array([names.index(n) for n in ARM])
        self.grip = names.index('piper_gripper_joint1')
        self.wheel_joints = joints[self.wheels]
        self.leg_dofs = model.jnt_dofadr[joints[self.legs]]
        self.leg_kp = model.actuator_gainprm[self.legs, 0]
        self.leg_rest = data.qpos[model.jnt_qposadr[joints[self.legs]]].copy()
        self.radius = cfg['rolling_radius_m']
        self.leg_yaw = 0.
        self.leg_yaw_gain = np.zeros_like(self.leg_rest)
        root_R = data.xmat[self.body].reshape(3, 3)
        jac = np.empty((3, model.nv))
        for wheel in self.wheels:
            body = model.jnt_bodyid[joints[wheel]]
            label = names[wheel].split('_')[1]
            indices = [k for k, i in enumerate(self.legs) if names[i].split('_')[1] == label]
            wheel_geom = next(g for g in range(model.ngeom) if model.geom_bodyid[g] == body and model.geom_contype[g])
            point = data.geom_xpos[wheel_geom] - np.array([0., 0., self.radius])
            lever_x = (root_R.T @ (point-data.xpos[self.body]))[0]
            mj.mj_jac(model, data, jac, None, point, body)
            # Opposite fore/aft lateral stance offsets let the body yaw on
            # the four contacts. Hold contact height; wheels supply rolling X.
            self.leg_yaw_gain[indices] = np.linalg.solve(
                root_R.T @ jac[:,self.leg_dofs[indices]], [0., -lever_x, 0.])
        self.mode = None
        self.yaw_integral = 0.
        self.last_speed = 0.
        self.last_turn = 0.

    def state(self, data):
        q = self.root_q
        v = self.root_v
        rotation = np.empty(9)
        mj.mju_quat2Mat(rotation, data.qpos[q+3:q+7])
        rotation = rotation.reshape(3, 3)
        world_linear = data.qvel[v:v+3]
        world_angular = rotation @ data.qvel[v+3:v+6]
        return dict(xy=data.qpos[q:q+2].copy(),
                    roll=math.atan2(rotation[2, 1], rotation[2, 2]),
                    pitch=math.asin(np.clip(-rotation[2, 0], -1., 1.)),
                    yaw=math.atan2(rotation[1, 0], rotation[0, 0]),
                    speed=float(np.linalg.norm(world_linear[:2])),
                    yaw_rate=float(world_angular[2]),
                    linear_world=world_linear.copy(), angular_world=world_angular)

    def leg_commands(self, data):
        return self.leg_rest + self.leg_yaw*self.leg_yaw_gain + data.qfrc_bias[self.leg_dofs] / self.leg_kp

    def wheel_commands(self, data, target_xy, target_yaw_rad, mode='hold'):
        if mode not in ('approach', 'retreat', 'hold', 'grip'):
            raise ValueError(f'Unknown base mode {mode!r}')
        if mode != self.mode:
            self.yaw_integral = 0.
            self.mode = mode
            self.aligned = False
            self.arrived = False

        cfg = self.cfg
        state = self.state(data)
        delta = target_xy - state['xy']
        yaw = state['yaw']
        forward = np.array([math.cos(yaw), math.sin(yaw)])
        along = float(delta @ forward)
        distance = float(np.linalg.norm(delta))
        desired_yaw = target_yaw_rad
        moving = mode in ('approach', 'retreat')
        if moving and distance <= cfg.get('base_arrival_radius_m', .009):
            self.arrived = True
        if moving and not self.arrived:
            # Point towards the target (away from it while reversing). Reduce
            # speed if the chassis still needs to turn to acquire its line.
            direction = -1 if mode == 'retreat' else 1
            desired_yaw = math.atan2(direction * delta[1], direction * delta[0])
            pointing_error = abs(signed_angle(desired_yaw-yaw))
            speed = direction * min(cfg['straight_speed_m_s'], 1.2 * distance)
            if pointing_error < math.radians(1.):
                self.aligned = True
            if pointing_error > math.radians(4.):
                self.aligned = False
            if not self.aligned:
                speed = 0.
        else:
            # Let the velocity servos brake close to target. During parked
            # manipulation yaw and longitudinal corrections can re-engage.
            limit = cfg.get('base_grip_speed_m_s', .012) if mode == 'grip' else .022
            speed = float(np.clip(1.3 * along, -limit, limit))
            if abs(along) <= .001:
                speed = 0.

        heading_error = signed_angle(desired_yaw-yaw)
        max_rate = cfg['yaw_rate_rad_s']
        turn_limit = cfg['max_differential_yaw_command_rad_s']
        if mode == 'grip':
            max_rate = cfg.get('base_grip_yaw_rate_rad_s', .035)
            turn_limit = cfg.get('base_grip_turn_limit_rad_s', .12)
        requested_rate = np.clip(cfg.get('heading_gain_per_s', 2.5)*heading_error,
                                 -max_rate, max_rate)
        rate_error = requested_rate - state['yaw_rate']
        if abs(heading_error) <= math.radians(cfg.get('base_heading_deadband_deg', .30)):
            self.yaw_integral = 0.
            turn = 0.
        else:
            self.yaw_integral = np.clip(self.yaw_integral + rate_error*self.model.opt.timestep, -.30, .30)
            turn = requested_rate + cfg['yaw_rate_kp']*rate_error + cfg['yaw_rate_ki']*self.yaw_integral
            if moving:
                turn_limit = cfg['travel_turn_limit_rad_s']
                trim_limit = math.radians(cfg['stance_yaw_limit_deg'])
                self.leg_yaw = np.clip(self.leg_yaw + requested_rate*self.model.opt.timestep,
                                       -trim_limit, trim_limit)
            turn = np.clip(turn, -turn_limit, turn_limit)
        self.last_speed, self.last_turn = float(speed), float(turn)
        sign, lateral = wheel_geometry(data, self.body, self.wheel_joints)
        return wheel_rates(sign, lateral, self.radius, speed, turn)
