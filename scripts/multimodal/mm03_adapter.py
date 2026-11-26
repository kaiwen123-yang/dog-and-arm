"""MM03 effective task commands and query-only 500 Hz local wheel/leg teacher."""
import numpy as np
import mujoco as mj

from learning.b0.physics import ActionMap
from p6_base import BaseDrive, wheel_geometry, wheel_rates
from scripts.multimodal.correction_teacher import ExpertLabel, P6CorrectionTeacher


class LocalVelocityTeacher:
    """A phase-independent command interface. Requests are SI body vx and yaw rate.

    The two integrators belong to this local teacher. No world destination, task
    phase, base velocity, wheel load or contact classification enters update().
    Wheel offsets/axes are relative kinematics; yaw feedback is gyro projected
    onto vertical using measured gravity. Output is the pre-bias action.
    """

    version = "MM03-local-vx-wz-v1"

    def __init__(self, model, frame0, cfg):
        self.cfg = cfg
        self.map = ActionMap(model)
        self.drive = BaseDrive(model, frame0, cfg)
        self.model = model
        self.dt = float(model.opt.timestep)
        if abs(self.dt - .002) > 1e-10 or abs(frame0.time) > 1e-10:
            raise ValueError("Local command teacher must start at the original 2 ms frame0")
        self.request = np.zeros(2)
        self.integral = 0.
        self.stance_yaw = 0.
        self.trim_limit = np.deg2rad(cfg["stance_yaw_limit_deg"])
        self.turn_limit = cfg["travel_turn_limit_rad_s"]
        self.bounds = np.array([cfg["straight_speed_m_s"], cfg["yaw_rate_rad_s"]])
        # BaseDrive arrays follow XML actuator order, ActionMap follows the canonical ABI.
        self.leg_order = [np.flatnonzero(self.drive.legs == i).item() for i in self.map.actuator_ids[:12]]
        self.wheel_order = [np.flatnonzero(self.drive.wheels == i).item() for i in self.map.actuator_ids[12:16]]
        self.rotation = np.empty(9)

    def update(self, data, request):
        vx, wz = self.request = np.clip(request, -self.bounds, self.bounds)
        d = self.drive
        mj.mju_quat2Mat(self.rotation, data.qpos[d.root_q+3:d.root_q+7])
        gyro_vertical = self.rotation.reshape(3, 3)[2] @ data.qvel[d.root_v+3:d.root_v+6]
        # The returned stance belongs to this decision boundary. Integrating the
        # applied command below produces the next local state.
        legs = d.leg_rest + self.stance_yaw*d.leg_yaw_gain
        if wz == 0:
            self.integral = 0.
            turn = 0.
        else:
            error = wz - gyro_vertical
            self.integral = float(np.clip(self.integral + self.dt*error, -.30, .30))
            turn = np.clip(wz + self.cfg["yaw_rate_kp"]*error + self.cfg["yaw_rate_ki"]*self.integral,
                           -self.turn_limit, self.turn_limit)
            self.stance_yaw = float(np.clip(self.stance_yaw + self.dt*wz, -self.trim_limit, self.trim_limit))
        axis, offsets = wheel_geometry(data, d.body, d.wheel_joints)
        wheels = wheel_rates(axis, offsets, d.radius, vx, turn)
        # legs is the explicit position reference, with no dynamic bias added.
        physical = np.r_[legs[self.leg_order], wheels[self.wheel_order]]
        return (physical - self.map.offset[:16]) / self.map.scale[:16]


class CommandTeacher(P6CorrectionTeacher):
    """P6 navigation/arm labels and local-v1 legs/wheels, queried on actual state."""

    def __init__(self, model, frame0, cfg):
        super().__init__(model, frame0, cfg)
        self.local = LocalVelocityTeacher(model, frame0, cfg)
        self.request = np.zeros(2)
        self.original_boundary_label = None

    def before(self, data):
        label = super().before(data)
        if label is not None:
            # The original P6 and local-v1 use the same continuously updated
            # P6 control state. Prefix execution may consume the original here.
            self.original_boundary_label = label
            # last_speed already passed alignment/deadband/hysteresis. The yaw
            # request is upstream of PI and downstream of its enable decision.
            self.request = np.array([self.drive.last_speed, self.drive.effective_yaw_request])
        # Navigation's 50 Hz request is held through all ten 2 ms updates.
        low = self.local.update(self.scratch, self.request)
        if label is None:
            return None
        self.request = self.local.request.copy()
        raw = np.r_[low, label.raw[16:]]
        target = np.clip(raw, -1., 1.)
        reason = self.failure or "valid"
        if not np.all(np.isfinite(raw)):
            reason = "nonfinite_request"
        elif np.max(abs(raw)) > 1. + 1e-8:
            reason = "mapped_request_out_of_range"
        elif self.arm.ik_position_error > .002 or self.arm.ik_rotation_error > .02:
            reason = "ik_residual_out_of_tolerance"
        return ExpertLabel(raw, target, self.mapping.offset+self.mapping.scale*target,
                           reason == "valid", reason, label.phase)

    def snapshot(self):
        state = super().snapshot()
        state["mm03_local"] = dict(request=self.request.copy(), integral=self.local.integral,
                                   stance_yaw=self.local.stance_yaw)
        return state

    def restore(self, snapshot):
        super().restore(snapshot)
        local = snapshot["mm03_local"]
        self.request = np.array(local["request"], copy=True)
        self.local.request = self.request.copy()
        self.local.integral = local["integral"]
        self.local.stance_yaw = local["stance_yaw"]
