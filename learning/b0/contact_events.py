"""Read-only B0 physical events. One call per solved interval, before FK refresh.

Native and Warp callers must supply the same interval-start q/v and solved contact
sample (including the active side's two finger loads). Only the judge's counters
are mutable; it owns no control, IK, reference advance or simulator reset.
"""
from dataclasses import dataclass
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from .physics import ARM, FINGERS, ContactMeter
from .contact_clock import ContactClock


@dataclass(frozen=True)
class FrozenDoorReference:
    phase_bounds: dict        # absolute source step, [start, stop)
    endpoint_pose: dict       # intended TCP world xyz / rotation for near events
    station_xy: np.ndarray    # after the nominal reference has settled
    station_yaw: float
    target_angle_deg: float

    @classmethod
    def from_episode(cls, path, model):
        path = Path(path)
        meta = json.loads((path / 'metadata.json').read_text())
        phase = np.load(path / 'substeps/phase.npy', mmap_mode='r')
        changes = np.r_[0, np.flatnonzero(np.diff(phase)) + 1, len(phase)]
        names = [meta['phases'][int(phase[i])] for i in changes[:-1]]
        if len(names) != len(set(names)):
            raise ValueError('reference contains a repeated phase')
        bounds = dict(zip(names, zip(map(int, changes[:-1]), map(int, changes[1:]))))
        states = np.load(path / 'substeps/qpos.npy', mmap_mode='r')
        tcp = model.site('p4_grasp').id
        scratch = mj.MjData(model)
        poses = {}
        goal_path = path / 'substeps/tcp_goal_world_m.npy'
        if goal_path.exists():
            goal_pos = np.load(goal_path, mmap_mode='r')
            goal_rot = np.load(path / 'substeps/tool_goal_world_R.npy', mmap_mode='r')
        else:
            goal_pos = goal_rot = None
        for name, (_, stop) in bounds.items():
            if goal_pos is not None:
                poses[name] = (goal_pos[stop-1].copy(), goal_rot[stop-1].copy())
                continue
            scratch.qpos[:] = states[stop]
            mj.mj_kinematics(model, scratch)
            poses[name] = (scratch.site_xpos[tcp].copy(), scratch.site_xmat[tcp].reshape(3, 3).copy())
        station_q = states[bounds['settle'][1] - 1] if 'settle' in bounds else states[0]
        rotation = np.empty(9)
        mj.mju_quat2Mat(rotation, station_q[3:7])
        return cls(bounds, poses, station_q[:2].copy(), float(np.arctan2(rotation[3], rotation[0])),
                   float(meta['target_angle_deg']))


class ContactEvents:
    def __init__(self, model, cfg, side, reference, phases=None, hold_seconds=None, start_step=None,
                 score_until_step=None):
        if side not in ('pull', 'push'):
            raise ValueError('side must be pull or push')
        self.cfg, self.reference = cfg, reference
        self.phases = tuple(reference.phase_bounds if phases is None else phases)
        if not self.phases or any(p not in reference.phase_bounds for p in self.phases):
            raise ValueError('missing reference phases')
        self.dt = float(model.opt.timestep)
        self.reference_stride = ContactClock(self.dt).servo_stride
        self.offset = self.reference_stride * (
            reference.phase_bounds[self.phases[0]][0] if start_step is None else start_step)
        self.hold_seconds = .5 if hold_seconds is None else float(hold_seconds)
        self.meter = ContactMeter(model, 'preview_floor', 'back' if side == 'push' else 'front',
                                  cfg['contact_threshold_n'], cfg['wheel_threshold_n'])
        self.tcp = model.site('p4_grasp').id
        self.handle = model.site(cfg['handle_site']).id
        if ('back' in cfg['handle_site']) != (side == 'push'):
            raise ValueError('contact side disagrees with handle site')
        self.arm_q = np.array([model.joint(n).qposadr.item() for n in ARM])
        self.arm_home = model.key('home').qpos[self.arm_q].copy()
        self.arm_ranges = model.jnt_range[[model.joint(n).id for n in ARM]]
        self.finger_q = [model.joint(n).qposadr.item() for n in FINGERS]
        hinge = model.joint('door_single_hinge')
        self.hinge_q, self.hinge_v = hinge.qposadr.item(), hinge.dofadr.item()
        self.saturation = np.zeros(model.nu, dtype=int)
        self.effort = model.actuator_forcerange[:, 1] * cfg['sat_fraction']
        self.actuated = [model.joint(j).name for j in model.actuator_trnid[:, 0]]
        self.rotation = np.empty(9)
        self.nominal_xy = np.array(cfg['base_xyz_m'][:2])
        yaw = cfg['base_yaw_rad']
        self.parking = self.nominal_xy - cfg['travel_m'] * np.array([np.cos(yaw), np.sin(yaw)])
        self.phase_start = self.i = self.step = self.good = self.lost = self.sliding = self.unloaded = 0
        self.events, self.failure = [], None
        self.score_until_step = None if score_until_step is None else score_until_step * self.reference_stride
        self.terminal_event_step = None
        self.last_not_ready = {}
        self.peak_ready_steps, self.latest = {}, None

    def ticks(self, seconds):
        return int(np.ceil(seconds / self.dt - 1e-9))

    @property
    def phase(self):
        return self.phases[self.i] if self.i < len(self.phases) else None

    @property
    def passed(self):
        return self.i == len(self.phases) and self.failure is None

    def observe(self, data, contact, q0, v0):
        """Use immediately after mj_step; q0/v0 from before that step, qpos from after.

        The cached Cartesian geometry, contacts, slip, wrench and effort all refer
        to the solved interval. ContactMeter.measure must precede any mj_forward.
        """
        if self.failure or self.passed:
            raise ValueError('terminal event judge')
        phase, cfg = self.phase, self.cfg
        k = self.offset + self.step
        elapsed = self.step - self.phase_start
        self.step += 1
        c = self.meter.measure(data) if contact is None else contact
        mj.mju_quat2Mat(self.rotation, q0[3:7])
        rot = self.rotation.reshape(3, 3)
        yaw = np.arctan2(rot[1, 0], rot[0, 0])
        tilt = np.rad2deg(max(abs(np.arctan2(rot[2, 1], rot[2, 2])), abs(np.arcsin(np.clip(-rot[2, 0], -1., 1.)))))
        if phase in ('final', 'retreat_base'):
            goal_xy, goal_yaw = self.parking, cfg['base_yaw_rad']
        elif phase in ('settle', 'approach_base'):
            goal_xy, goal_yaw = self.nominal_xy, cfg['base_yaw_rad']
        else:
            goal_xy, goal_yaw = self.reference.station_xy, self.reference.station_yaw
        drift = np.linalg.norm(q0[:2] - goal_xy)
        heading = abs(np.rad2deg(np.arctan2(np.sin(yaw-goal_yaw), np.cos(yaw-goal_yaw))))
        in_zone = drift <= cfg['position_tol_m'] and heading <= cfg['heading_tol_deg']
        supported = bool(c.supported.all())
        speed = np.linalg.norm(v0[:2])
        yaw_rate = np.rad2deg(rot[2] @ v0[3:6])
        stable = in_zone and supported and speed < cfg['settle_speed_m_s'] and abs(yaw_rate) < cfg['settle_yaw_rate_deg_s']
        angle = np.rad2deg(q0[self.hinge_q])
        reached = abs(angle - self.reference.target_angle_deg) <= cfg['angle_tolerance_deg']
        tcp = data.site_xpos[self.tcp]
        error = np.linalg.norm(tcp - data.site_xpos[self.handle])
        jaw = q0[self.finger_q[0]] - q0[self.finger_q[1]]
        gripped = c.both and cfg['grasp_width_range_m'][0] <= jaw <= cfg['grasp_width_range_m'][1] and error <= cfg['grasp_error_m']
        detached = c.force_norm_sum <= cfg['contact_threshold_n']
        net = np.linalg.norm(c.door_force)
        slip = np.max(np.hypot(np.nan_to_num(c.slip_long), np.nan_to_num(c.slip_lat)))
        self.saturation[:] = np.where(np.abs(data.actuator_force) >= self.effort, self.saturation+1, 0)
        self.unloaded = 0 if supported else self.unloaded+1
        gripping = phase in ('open', 'hold')
        self.lost = self.lost+1 if gripping and not c.both else 0
        self.sliding = self.sliding+1 if phase in ('grasp','open','hold','release') and slip > cfg['park_slip_limit_m_s'] else 0
        arm = data.qpos[self.arm_q]
        margin = np.minimum(arm - self.arm_ranges[:, 0], self.arm_ranges[:, 1] - arm)
        reason = None
        if not (np.isfinite(data.qpos).all() and np.isfinite(data.qvel).all()) or any(w.number for w in data.warning):
            reason = 'nonfinite_or_solver_warning'
        elif np.any(margin < 0.):
            reason = 'arm_joint_limit:' + ARM[int(np.argmin(margin))]
        elif c.unexpected:
            reason = 'unexpected_contact:' + ','.join(sorted(c.unexpected))
        elif phase in ('approach_base','settle','pregrasp','post_release_hold','stow','retreat_base','final') and not detached:
            reason = 'door_contact_outside_manipulation'
        elif self.unloaded >= self.ticks(cfg['unloaded_limit_s']) or tilt >= cfg['tilt_limit_deg']:
            reason = 'wheel_support_or_tilt'
        elif self.saturation.max() >= self.ticks(cfg['sat_limit_s']):
            reason = 'persistent_saturation:' + self.actuated[int(np.argmax(self.saturation))]
        elif self.lost >= self.ticks(cfg['loss_limit_s']):
            reason = 'lost_grip'
        elif self.sliding >= self.ticks(cfg['park_slip_limit_s']):
            reason = 'persistent_grip_phase_wheel_slip'
        elif gripping and (not in_zone or error > cfg['grasp_error_m']):
            reason = 'grip_base_or_handle_error'
        elif phase not in ('approach_base','settle','retreat_base','final') and not in_zone:
            reason = 'operation_station_drift'
        elif gripping and net > cfg['grip_net_force_limit_n']:
            reason = 'door_force_limit'
        # Fixed clock and phase endpoints come only from the given nominal reference.
        # No future physical state, teacher inverse kinematics or controller is called.
        begin, end = self.reference.phase_bounds[phase]
        begin, end = begin*self.reference_stride, end*self.reference_stride
        ramp = k >= begin + self.ticks(cfg['phase_ramp_s'].get(phase, 0))
        if phase in ('approach_base', 'retreat_base'):
            ready, seconds = in_zone and drift < .010 and heading < 1., .06
        elif phase == 'settle':
            ready, seconds = stable, cfg['settle_time_s']
        elif phase in ('pregrasp', 'approach_arm', 'retreat_arm'):
            pos, target_rotation = self.reference.endpoint_pose[phase]
            distance = np.linalg.norm(tcp - pos)
            orientation = data.site_xmat[self.tcp].reshape(3, 3)
            rot_error = np.arccos(np.clip((np.sum(orientation * target_rotation)-1)/2, -1., 1.))
            ready = ramp and distance <= cfg['tracking_tol_m'] and rot_error <= .02
            if phase == 'retreat_arm':
                ready = ready and detached and error >= .8*cfg['retreat_distance_m']
            seconds = .15
        elif phase == 'grasp':
            ready, seconds = ramp and gripped, cfg['grasp_confirm_s']
        elif phase == 'open':
            seconds = .15
            ready = k >= end-self.ticks(seconds) and reached and c.both
        elif phase == 'hold':
            ready = reached and gripped and stable and abs(v0[self.hinge_v]) < .01
            seconds = self.hold_seconds
        elif phase == 'release':
            ready, seconds = ramp and detached and jaw >= .9*cfg['open_width_m'], .15
        elif phase == 'stow':
            ready, seconds = ramp and detached and np.max(np.abs(q0[self.arm_q]-self.arm_home)) < .025, .15
        elif phase in ('post_release_hold', 'final'):
            ready, seconds = stable and detached and reached, cfg['post_hold_s']
        else:
            raise ValueError(f'unsupported frozen event {phase}')
        self.good = self.good+1 if ready else 0
        if not ready:
            flags = dict(ramp=bool(ramp), within_position_zone=bool(in_zone), stable=bool(stable),
                         wheels_loaded=bool(supported), reached=bool(reached), both_fingers=bool(c.both),
                         gripped=bool(gripped), detached=bool(detached), door_speed_rad_s=float(v0[self.hinge_v]),
                         planar_speed_m_s=float(speed), yaw_rate_deg_s=float(yaw_rate),
                         tcp_handle_error_m=float(error), width_m=float(jaw))
            if phase in ('pregrasp','approach_arm','retreat_arm'):
                flags.update(tcp_goal_distance_m=float(distance),tcp_goal_rotation_error_rad=float(rot_error))
            self.last_not_ready[phase] = dict(reference_substep=k, **flags)
        self.peak_ready_steps[phase] = max(self.good, self.peak_ready_steps.get(phase, 0))
        self.latest = dict(phase=phase, door_deg=float(angle), width_m=float(jaw),
                           finger_n=c.finger_normal.tolist(), net_door_force_n=float(net),
                           tcp_handle_error_m=float(error), station_error_m=float(drift),
                           tilt_deg=float(tilt), speed_m_s=float(speed), yaw_rate_deg_s=float(yaw_rate),
                           continuous_ready_steps=self.good, required_ready_steps=self.ticks(seconds))
        if self.terminal_event_step is not None:
            # The original physical gate already passed. Keep enforcing its terminal
            # conditions on the actual policy through the requested score horizon.
            if not reason and not ready:
                reason = 'terminal_hold_lost_during_scoring'
            if not reason and self.step >= self.score_until_step:
                self.i += 1
        elif not reason and self.good >= self.ticks(seconds):
            self.events.append(dict(phase=phase, end_step=self.step, ref_end_step=k+1, ticks=self.good,
                                    door_deg=float(angle), width_m=float(jaw), net_force_n=float(net)))
            if self.i == len(self.phases)-1:
                self.terminal_event_step = self.step
            if self.terminal_event_step is None or self.score_until_step is None or self.step >= self.score_until_step:
                self.i += 1
                self.phase_start, self.good = self.step, 0
        elif not reason and elapsed >= self.ticks(cfg['phase_timeout_s'][phase]):
            reason = 'timeout:' + phase
        if reason:
            self.failure = dict(reason=reason, phase=phase, first_failure_substep=self.step,
                                interval_start_s=(self.step-1)*self.dt, interval_end_s=self.step*self.dt,
                                door_deg=float(angle), finger_load_n=c.finger_normal.tolist(),
                                wheel_load_n=c.normal.tolist(), door_net_force_n=float(net),
                                door_contact_sum_n=float(c.force_norm_sum), tcp_handle_error_m=float(error),
                                min_arm_margin_rad=float(margin.min()))
        return self.failure
