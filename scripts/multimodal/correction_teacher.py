"""Stateful, query-only P6 control for native 2 ms M1/Piper door episodes.

Call before and after around *every* physical integration, whichever controller
executes. Only the 20 ms boundary returns a label. Neither method writes to the
student MjData. P6 control transitions and the independent evaluator have
different phase names and different predicates.
"""
from copy import deepcopy
from dataclasses import dataclass
import math

import mujoco as mj
import numpy as np

from learning.b0.physics import ActionMap
from p6_arm import Arm
from p6_base import BaseDrive, signed_angle


CONTROL_PHASES = ("approach_base", "settle", "pregrasp", "approach_arm", "grasp",
                  "open", "hold", "release", "retreat_arm", "post_release_hold",
                  "stow", "retreat_base", "final")
STATE_SPEC = mj.mjtState.mjSTATE_INTEGRATION


@dataclass(frozen=True)
class ExpertLabel:
    raw: np.ndarray
    target: np.ndarray
    physical: np.ndarray
    valid: bool
    reason: str
    phase: str


def capture_physics(model, data):
    """Capture exactly the inputs to the next native servo and solver step.

    The stored bias belongs to the *last solved* interval and is used before
    the next mj_step. Recomputing it at the new qpos changes the command.
    mjSTATE_INTEGRATION includes time, qpos/qvel/act, warmstart, all actual
    controls, applied forces, plugins, equality flags, mocap and userdata.
    """
    state = np.empty(mj.mj_stateSize(model, STATE_SPEC))
    mj.mj_getState(model, data, state, STATE_SPEC)
    return dict(integration=state, qfrc_bias=data.qfrc_bias.copy(),
                warning_number=data.warning.number.copy(),
                warning_lastinfo=data.warning.lastinfo.copy())


def restore_physics(model, snapshot):
    data = mj.MjData(model)
    mj.mj_setState(model, data, snapshot["integration"], STATE_SPEC)
    mj.mj_forward(model, data)
    # Forward computes derived transforms; restore warmstart and previous bias.
    mj.mj_setState(model, data, snapshot["integration"], STATE_SPEC)
    data.qfrc_bias[:] = snapshot["qfrc_bias"]
    data.warning.number[:] = snapshot["warning_number"]
    data.warning.lastinfo[:] = snapshot["warning_lastinfo"]
    return data


class P6CorrectionTeacher:
    def __init__(self, model, frame0, cfg):
        if abs(frame0.time) > 1e-10 or abs(model.opt.timestep - .002) > 1e-12:
            raise ValueError("P6 correction teacher requires the original 2 ms frame0")
        self.model, self.cfg = model, cfg
        self.dt = float(model.opt.timestep)
        self.mapping = ActionMap(model)
        self.drive, self.arm = BaseDrive(model, frame0, cfg), Arm(model, frame0, cfg)
        self.scratch = mj.MjData(model)
        self.station = np.asarray(cfg["base_xyz_m"][:2])
        self.yaw = cfg["base_yaw_rad"]
        self.parking = self.station - cfg["travel_m"] * np.array([np.cos(self.yaw), np.sin(self.yaw)])
        self.ref_xy, self.ref_yaw = self.station.copy(), self.yaw
        self.hinge = model.joint("door_single_hinge")
        self.goal = cfg["target_angle_deg"]
        self.fingers = [model.joint(f"piper_gripper_joint{i}").qposadr.item() for i in (1, 2)]
        self.arm_ids = np.r_[self.drive.arms, self.drive.grip]
        self.position_ids = np.r_[self.drive.legs, self.arm_ids]
        self.dofs = model.jnt_dofadr[model.actuator_trnid[:, 0]]
        self.gains = model.actuator_gainprm[:, 0]
        self.force_limit = model.actuator_forcerange[:, 1]
        self.arm_bounds = self.arm.ik.bounds
        self.q_arm, self.q_finger = self.arm.home.copy(), self.arm.home_width/2
        self.raw_angle = self.effective_angle = float(np.rad2deg(frame0.qpos[self.hinge.qposadr.item()]))
        self.index = self.step = self.arm_queries = 0
        self.phase_start = self.good_time = self.lost = self.sliding = self.unloaded = 0.
        self.sat_time = np.zeros(model.nu)
        self.last_phase = self.failure = None
        self.events = []
        self._pending = False

    @property
    def phase(self):
        return CONTROL_PHASES[min(self.index, len(CONTROL_PHASES) - 1)]

    def before(self, data):
        if self._pending:
            raise RuntimeError("Call after on the actual solved transition before the next query")
        cfg, d, arm, drive = self.cfg, self.scratch, self.arm, self.drive
        phase = self.phase
        new_phase = phase != self.last_phase
        self.last_phase = phase
        d.time = data.time
        d.qpos[:] = data.qpos
        d.qvel[:] = data.qvel
        d.qfrc_bias[:] = data.qfrc_bias
        mj.mj_kinematics(self.model, d)
        elapsed = d.time - self.phase_start
        fraction = min(1., elapsed / cfg["phase_ramp_s"].get(phase, 1.))
        base_mode = {"approach_base": "approach", "retreat_base": "retreat"}.get(phase, "hold")
        if phase in ("grasp", "open", "hold", "release"):
            base_mode = "grip"
        at_parking = phase in ("retreat_base", "final")
        destination = self.parking if at_parking else self.ref_xy
        heading = self.yaw if at_parking else self.ref_yaw
        state = drive.state(d)
        drift = float(np.linalg.norm(state["xy"] - destination))
        heading_err = abs(math.degrees(signed_angle(state["yaw"] - heading)))
        tilt = float(np.rad2deg(max(abs(state["roll"]), abs(state["pitch"]))))
        slow = (state["speed"] < cfg["settle_speed_m_s"] and
                abs(np.rad2deg(state["yaw_rate"])) < cfg["settle_yaw_rate_deg_s"])
        in_zone = drift <= cfg["position_tol_m"] and heading_err <= cfg["heading_tol_deg"]
        angle = float(np.rad2deg(d.qpos[self.hinge.qposadr.item()]))
        width = float(d.qpos[self.fingers[0]] - d.qpos[self.fingers[1]])
        if phase == "open":
            rate = cfg["angle_rate_deg_s"] * min(1., elapsed / cfg["angle_accel_ramp_s"])
            self.raw_angle = min(self.goal, self.raw_angle + self.dt * rate)
            if not self.lost and not self.sliding and in_zone and not np.any(self.sat_time):
                self.effective_angle = min(self.raw_angle, angle + cfg["angle_lead_deg"],
                                           self.effective_angle + self.dt * rate)
        elif phase in ("pregrasp", "approach_arm", "grasp"):
            self.raw_angle = self.effective_angle = angle
        if new_phase or self.step % 5 == 0:
            self.q_arm, self.q_finger = arm.update(d, phase, fraction, self.raw_angle, self.effective_angle)
            self.arm_queries += 1
        # Mirror P6's bias removal and XML ordering even for noncanonical
        # actuator order. The hold is *after* updating the base integrators.
        candidate = np.empty(self.model.nu)
        candidate[drive.legs] = drive.leg_commands(d)
        candidate[drive.wheels] = drive.wheel_commands(d, destination, heading, base_mode)
        self._context = (elapsed, fraction, base_mode, state, drift, heading_err, tilt, slow, in_zone, angle, width)
        self._pending = True
        if self.step % 10:
            return None
        ids = self.arm_ids
        candidate[ids] = np.r_[self.q_arm, self.q_finger] + d.qfrc_bias[self.dofs[ids]] / self.gains[ids]
        ids = self.position_ids
        candidate[ids] -= d.qfrc_bias[self.dofs[ids]] / self.gains[ids]
        candidate[drive.grip] *= 2.
        a = self.mapping
        raw = (candidate[a.actuator_ids] - a.offset) / a.scale
        target = np.clip(raw, -1., 1.)
        reason = self.failure or "valid"
        if not np.isfinite(raw).all():
            reason = "nonfinite_request"
        elif np.any(abs(raw) > 1. + 1e-8):
            reason = "mapped_request_out_of_range"
        elif arm.ik_position_error > .002 or arm.ik_rotation_error > .02:
            reason = "ik_residual_out_of_tolerance"
        return ExpertLabel(raw, target, a.offset + a.scale*target, reason == "valid", reason, phase)

    @property
    def needs_wheel_slip(self):
        """Whether the pending solved interval contributes to the sliding failure counter."""
        return self._pending and self.index < len(CONTROL_PHASES) and self._context[2] == "grip"

    def after(self, data, contact):
        if not self._pending:
            raise RuntimeError("A teacher pre-step observation is required")
        self._pending = False
        self.step += 1
        if self.index == len(CONTROL_PHASES):
            return
        (elapsed, fraction, base_mode, state, drift, heading_err, tilt, slow,
         in_zone, angle, width) = self._context
        cfg, dt, phase, arm = self.cfg, self.dt, self.phase, self.arm
        c = contact
        xyz = data.site_xpos[arm.grasp_id]
        grip_error = np.linalg.norm(xyz - data.site_xpos[arm.handle_id])
        tracking = np.linalg.norm(xyz - arm.position)
        no_contact = c.force_norm_sum <= cfg["contact_threshold_n"]
        supported = bool(c.supported.all())
        self.sat_time = np.where(abs(data.actuator_force) >= self.force_limit*cfg["sat_fraction"],
                                 self.sat_time + dt, 0.)
        self.unloaded = 0. if supported else self.unloaded + dt
        gripping = phase in ("open", "hold")
        self.lost = self.lost + dt if gripping and not c.both else 0.
        slipping = base_mode == "grip" and np.max(np.hypot(np.nan_to_num(c.slip_long),
                                                       np.nan_to_num(c.slip_lat))) > cfg["park_slip_limit_m_s"]
        self.sliding = self.sliding + dt if slipping else 0.
        if self.failure:
            return
        arm_pos = data.qpos[arm.ik.q]
        if not np.isfinite(data.qpos).all() or any(w.number for w in data.warning):
            self.failure = "nonfinite_or_solver_warning"
        elif np.any(arm_pos < self.arm_bounds[:, 0]) or np.any(arm_pos > self.arm_bounds[:, 1]):
            self.failure = "arm_joint_limit"
        elif c.unexpected:
            self.failure = "unexpected_contact:" + ",".join(sorted(c.unexpected))
        elif phase in ("approach_base", "settle", "pregrasp", "post_release_hold", "stow",
                       "retreat_base", "final") and not no_contact:
            self.failure = "door_contact_outside_manipulation"
        elif self.unloaded >= cfg["unloaded_limit_s"] or tilt >= cfg["tilt_limit_deg"]:
            self.failure = "wheel_support_or_tilt"
        elif self.sat_time.max() >= cfg["sat_limit_s"]:
            self.failure = "persistent_saturation"
        elif self.lost >= cfg["loss_limit_s"] or self.sliding >= cfg["park_slip_limit_s"]:
            self.failure = "lost_grip" if self.lost else "persistent_grip_phase_wheel_slip"
        elif gripping and (not in_zone or grip_error > cfg["grasp_error_m"]):
            self.failure = "grip_base_or_handle_error"
        elif phase not in ("approach_base", "settle", "retreat_base", "final") and not in_zone:
            self.failure = "operation_station_drift"
        elif gripping and np.linalg.norm(c.door_force) > cfg.get("grip_net_force_limit_n", math.inf):
            self.failure = "door_force_limit"
        if self.failure:
            return
        stable = slow and in_zone and supported
        reached = abs(angle - self.goal) <= cfg["angle_tolerance_deg"]
        near = tracking <= cfg["tracking_tol_m"] and arm.ik_position_error <= .002 and arm.ik_rotation_error <= .02
        ramp_done = fraction >= 1.
        low, high = cfg["grasp_width_range_m"]
        q, v = self.scratch.qpos, self.scratch.qvel
        if phase in ("approach_base", "retreat_base"):
            ready, seconds = in_zone and drift < .010 and heading_err < 1., .06
        elif phase == "settle":
            ready, seconds = stable, cfg["settle_time_s"]
        elif phase in ("pregrasp", "approach_arm"):
            ready, seconds = ramp_done and near, .15
        elif phase == "grasp":
            ready = ramp_done and c.both and low <= width <= high and grip_error <= cfg["grasp_error_m"]
            seconds = cfg["grasp_confirm_s"]
        elif phase == "open":
            ready = self.raw_angle >= self.goal and self.effective_angle >= self.goal-.05 and reached and c.both
            seconds = .15
        elif phase == "hold":
            ready = reached and c.both and stable and abs(v[self.hinge.dofadr.item()]) < .01
            seconds = cfg.get("grip_hold_s", .5)
        elif phase == "release":
            ready, seconds = ramp_done and no_contact and width >= .9*cfg["open_width_m"], .15
        elif phase == "retreat_arm":
            ready = ramp_done and no_contact and near and grip_error >= .8*cfg["retreat_distance_m"]
            seconds = .15
        elif phase == "stow":
            ready, seconds = ramp_done and no_contact and np.max(np.abs(q[arm.ik.q]-arm.home)) < .025, .15
        else:
            ready = stable and no_contact and reached
            seconds = cfg.get("final_reference_hold_s", cfg["post_hold_s"]) if phase == "final" else cfg["post_hold_s"]
        self.good_time = self.good_time + dt if ready else 0.
        release_allowed = phase != "hold" or self.step >= cfg.get("teacher_release_earliest_step", 0)
        if self.good_time+1e-10 >= seconds and release_allowed:
            self.events.append(dict(phase=phase, time_s=float(data.time)))
            if phase == "settle":
                self.ref_xy, self.ref_yaw = state["xy"].copy(), state["yaw"]
            self.index += 1
            self.phase_start, self.good_time = float(data.time), 0.
        elif elapsed >= cfg["phase_timeout_s"][phase]:
            self.failure = "timeout:" + phase

    def snapshot(self):
        if self._pending or self.step % 10:
            raise ValueError("Capture before a 20 ms boundary query")
        state = {k: getattr(self, k) for k in (
            "index", "step", "arm_queries", "last_phase", "phase_start", "good_time", "lost",
            "sliding", "unloaded", "sat_time", "raw_angle", "effective_angle", "ref_xy",
            "ref_yaw", "q_arm", "q_finger", "failure", "events")}
        drive = {k: v for k, v in vars(self.drive).items() if k not in ("model", "cfg")}
        arm = {k: v for k, v in vars(self.arm).items() if k not in ("ik", "cfg")}
        return deepcopy(dict(state=state, drive=drive, arm=arm, ik_qpos=self.arm.ik.d.qpos))

    def restore(self, snapshot):
        if self._pending:
            raise ValueError("Cannot restore between a pre-step query and its observed successor")
        restored = deepcopy(snapshot)
        self.__dict__.update(restored["state"])
        self.drive.__dict__.update(restored["drive"])
        self.arm.__dict__.update(restored["arm"])
        self.arm.ik.d.qpos[:] = restored["ik_qpos"]
        # Next arm.update fills its scratch qpos from the actual branch state.
