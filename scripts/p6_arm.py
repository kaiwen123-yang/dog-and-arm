"""Arm references for the free-base P6 experiment. Physical data is read-only here."""
import mujoco as mj
import numpy as np
from scipy.spatial.transform import Rotation

from p4_fixed_door import IK, smooth


# +Z approaches the bar, +Y closes the two fingers across it.
HORIZONTAL_TOOL = np.array([[0., 0., 1.], [0., 1., 0.], [-1., 0., 0.]])


class Arm:
    def __init__(self, model, data, cfg):
        self.cfg = cfg
        pitch = Rotation.from_euler('y', cfg.get('tool_pitch_deg', 0.), degrees=True).as_matrix()
        self.tool = HORIZONTAL_TOOL @ pitch
        self.ik = IK(model)
        self.grasp_id = self.ik.site
        self.handle_id = model.site(cfg['handle_site']).id
        self.hinge = model.joint('door_single_hinge').id
        self.hinge_q = model.jnt_qposadr[self.hinge]
        self.home = data.qpos[self.ik.q].copy()
        self.home_width = float(data.joint('piper_gripper_joint1').qpos[0]
                                - data.joint('piper_gripper_joint2').qpos[0])
        self.command = self.home.copy()
        self.seed = np.array(cfg['ik_seed_rad'], dtype=float)
        self.phase = None
        self.time = float(data.time)
        self.width = self.home_width
        self.position = data.site_xpos[self.grasp_id].copy()
        self.rotation = data.site_xmat[self.grasp_id].reshape(3, 3).copy()
        self.raw_position = self.position.copy()
        self.raw_rotation = self.rotation.copy()
        self.angle_deg = float(np.rad2deg(data.qpos[self.hinge_q]))
        self.raw_angle_deg = self.angle_deg
        self.ik_position_error = self.ik_rotation_error = 0.

    def _tool_pose(self, data, angle_deg, clearance=0., retreat_fraction=0.):
        # Using the measured handle and the angle increment also handles trials
        # that begin with an already-open door. Both poses are world poses.
        actual_deg = np.rad2deg(data.qpos[self.hinge_q])
        hinge = data.xanchor[self.hinge]
        delta = Rotation.from_euler('z', angle_deg - actual_deg, degrees=True)
        position = hinge + delta.apply(data.site_xpos[self.handle_id] - hinge)
        start_yaw = self.cfg['tool_yaw_start_deg']
        tool_yaw = start_yaw + self.cfg['tool_yaw_door_ratio'] * angle_deg
        rotation = Rotation.from_euler('z', tool_yaw, degrees=True).as_matrix() @ self.tool
        direction = rotation[:, 2]
        if retreat_fraction and self.cfg['handle_site'].endswith('front_handle'):
            direction = np.array(self.cfg['pull_retreat_world_direction'])
        position -= clearance * direction
        if retreat_fraction:
            position[2] += self.cfg['retreat_lift_m'] * retreat_fraction
            # The P4 retreat yaw was established for 60 degrees front pull,
            # or 25 degrees back push. Scale it for the smaller diagnostic arc.
            full_arc = 25. if self.cfg['handle_site'].endswith('back_handle') else 60.
            final_yaw = start_yaw + (self.cfg['retreat_yaw_deg'] - start_yaw) * np.clip(angle_deg/full_arc, 0., 1.)
            yaw = tool_yaw + (final_yaw-tool_yaw)*retreat_fraction
            rotation = Rotation.from_euler('z', yaw, degrees=True).as_matrix() @ self.tool
        return position, rotation

    def _command_fk(self):
        self.ik.d.qpos[self.ik.q] = self.command
        mj.mj_kinematics(self.ik.m, self.ik.d)
        self.position = self.ik.d.site_xpos[self.grasp_id].copy()
        self.rotation = self.ik.d.site_xmat[self.grasp_id].reshape(3, 3).copy()
        self.raw_position = self.position.copy()
        self.raw_rotation = self.rotation.copy()

    def update(self, data, phase, fraction, raw_angle_deg=None, effective_angle_deg=None):
        """Update at task rate. Return six joint positions and positive finger displacement.

        The task loop owns event gates, raw angular progress and its feedback
        limit. Send the final angular references through hold, release and
        retreat_arm. All distances are in metres, angles in degrees except
        arm joint commands and ik_rotation_error (radians).
        """
        dt = max(0., float(data.time) - self.time)
        self.time = float(data.time)
        if phase != self.phase:
            self.start_command = self.command.copy()
            self.start_width = self.width
            self.phase = phase
        progress = float(smooth(fraction))
        self.ik.d.qpos[:] = data.qpos
        self.ik_position_error = self.ik_rotation_error = 0.
        limit = self.cfg.get('arm_joint_rate_rad_s', 1.4)*dt
        if phase in ('approach_base', 'settle', 'retreat_base', 'stow'):
            desired = self.home.copy()
            if phase == 'stow':
                # Pull the elbow and wrist in with J1 stationary. Swinging
                # J1 toward home with the arm extended crosses the open leaf.
                fold = self.start_command.copy()
                fold[1:] += smooth(fraction/.45)*(self.home[1:] - fold[1:])
                fold[0] += smooth((fraction-.45)/.55)*(self.home[0] - fold[0])
                desired = fold
            self.command += np.clip(desired-self.command, -limit, limit)
            self.width = self.start_width + progress * (self.home_width - self.start_width)
            self._command_fk()
            return self.command.copy(), self.width/2

        if phase in ('final', 'post_release_hold'):
            # Keep the previous joint or Cartesian hold according to the
            # preceding phase. Neither a drifting door nor a new phase timer
            # should generate additional motion after separation.
            if phase == 'final':
                self._command_fk()
                return self.command.copy(), self.width/2
        else:
            measured = float(np.rad2deg(data.qpos[self.hinge_q]))
            self.raw_angle_deg = measured if raw_angle_deg is None else float(raw_angle_deg)
            self.angle_deg = self.raw_angle_deg if effective_angle_deg is None else float(effective_angle_deg)
            clearance = 0.
            retreat = 0.
            self.width = self.cfg['open_width_m']
            if phase == 'pregrasp':
                clearance = self.cfg['pregrasp_distance_m']
                self.width = self.start_width + progress * (self.width-self.start_width)
            elif phase == 'dry_sweep':
                # As the virtual arc leaves the closed door, taper the
                # stand-off. Return along the same free-space arc at the end.
                arc = float(smooth(1. - abs(2.*np.clip(fraction, 0., 1.) - 1.)))
                self.angle_deg = self.raw_angle_deg = measured + arc*(self.cfg['target_angle_deg'] - measured)
                clearance = self.cfg['pregrasp_distance_m']*(1. - smooth(abs(self.angle_deg-measured)/15.))
            elif phase == 'approach_arm':
                clearance = self.cfg['pregrasp_distance_m'] * (1.-progress)
            elif phase == 'grasp':
                self.width = self.start_width + progress*(self.cfg['closed_command_width_m']-self.start_width)
            elif phase in ('open', 'hold'):
                self.width = self.cfg['closed_command_width_m']
            elif phase == 'release':
                self.width = self.start_width + progress*(self.width-self.start_width)
            elif phase == 'retreat_arm':
                retreat = progress
                clearance = self.cfg['retreat_distance_m']*retreat
            else:
                raise ValueError(f'Unknown P6 arm phase {phase!r}')
            self.position, self.rotation = self._tool_pose(data, self.angle_deg, clearance, retreat)
            self.raw_position, self.raw_rotation = self._tool_pose(data, self.raw_angle_deg, clearance, retreat)

        self.seed, self.ik_position_error, self.ik_rotation_error = self.ik.solve(
            self.position, self.rotation, self.seed, iterations=35)
        desired = self.seed
        if phase == 'pregrasp':
            desired = self.start_command + progress*(self.seed-self.start_command)
        self.command += np.clip(desired-self.command, -limit, limit)
        if phase == 'pregrasp':
            # The effective intermediate task is the FK of the smoothly
            # deployed joint reference, not the yet-to-be-reached pregrasp.
            self._command_fk()
        return self.command.copy(), self.width/2
