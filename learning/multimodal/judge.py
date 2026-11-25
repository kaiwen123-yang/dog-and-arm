"""Score task-space events in solved physics at 500 Hz, independent of reference time."""
import numpy as np
import mujoco as mj

from learning.b0.physics import ARM, FINGERS, ContactMeter


PHASES = ("approach_base", "settle", "reach_handle", "grasp", "open", "hold",
          "release", "retreat_arm", "post_release_hold", "stow", "retreat_base", "final")


class DoorTaskJudge:
    def __init__(self, model, cfg, side, goal_deg):
        self.cfg, self.goal = cfg, float(goal_deg)
        self.dt = float(model.opt.timestep)
        self.meter = ContactMeter(model, "preview_floor", "back" if side == "push" else "front",
                                  cfg["contact_threshold_n"], cfg["wheel_threshold_n"])
        self.tcp, self.handle = model.site("p4_grasp").id, model.site(cfg["handle_site"]).id
        self.hinge = model.joint("door_single_hinge")
        self.arm_q = np.array([model.joint(n).qposadr.item() for n in ARM])
        self.arm_home = model.key("home").qpos[self.arm_q].copy()
        self.ranges = model.jnt_range[[model.joint(n).id for n in ARM]]
        self.fingers = [model.joint(n).qposadr.item() for n in FINGERS]
        self.effort = model.actuator_forcerange[:, 1] * cfg["sat_fraction"]
        self.actuated = [model.joint(j).name for j in model.actuator_trnid[:, 0]]
        self.station = np.asarray(cfg["base_xyz_m"][:2])
        self.yaw = cfg["base_yaw_rad"]
        self.parking = self.station - cfg["travel_m"] * np.array([np.cos(self.yaw), np.sin(self.yaw)])
        self.timeouts = dict(cfg["phase_timeout_s"])
        self.timeouts["reach_handle"] = self.timeouts["pregrasp"] + self.timeouts["approach_arm"]
        self.i = self.steps = self.phase_start = self.ready = self.unloaded = self.lost = self.sliding = 0
        self.saturated = np.zeros(model.nu, dtype=np.int32)
        self.events, self.failure, self.last = [], None, {}
        self.rotation = np.empty(9)
        self.seen_contact = self.two_finger = self.wrong_contact = 0
        self.peak_force = self.max_angle = 0.
        self.closest_station = self.closest_handle = np.inf

    @property
    def passed(self):
        return self.i == len(PHASES) and self.failure is None

    @property
    def phase(self):
        return PHASES[self.i] if self.i < len(PHASES) else None

    def observe(self, d, q, v, contact=None):
        """q,v start this 2 ms interval. The solved contacts/Cartesian fields refer to it."""
        c = self.meter.measure(d) if contact is None else contact
        cfg, phase = self.cfg, self.phase
        self.steps += 1
        mj.mju_quat2Mat(self.rotation, q[3:7])
        r = self.rotation.reshape(3, 3)
        yaw = np.arctan2(r[1, 0], r[0, 0])
        heading = abs(np.rad2deg(np.arctan2(np.sin(yaw - self.yaw), np.cos(yaw - self.yaw))))
        tilt = np.rad2deg(max(abs(np.arctan2(r[2, 1], r[2, 2])), abs(np.arcsin(np.clip(-r[2, 0], -1, 1)))))
        station_error = np.linalg.norm(q[:2] - self.station)
        park_error = np.linalg.norm(q[:2] - self.parking)
        self.closest_station = min(self.closest_station, station_error)
        end_zone = phase in ("retreat_base", "final")
        xy_error = park_error if end_zone else station_error
        zone = xy_error <= cfg["position_tol_m"] and heading <= cfg["heading_tol_deg"]
        supported = bool(c.supported.all())
        speed = np.linalg.norm(v[:2])
        yaw_speed = abs(np.rad2deg(r[2] @ v[3:6]))
        stable = zone and supported and speed < cfg["settle_speed_m_s"] and yaw_speed < cfg["settle_yaw_rate_deg_s"]
        angle = float(np.rad2deg(q[self.hinge.qposadr.item()]))
        reached = abs(angle - self.goal) <= cfg["angle_tolerance_deg"]
        door_speed = abs(v[self.hinge.dofadr.item()])
        tcp_error = np.linalg.norm(d.site_xpos[self.tcp] - d.site_xpos[self.handle])
        jaw = q[self.fingers[0]] - q[self.fingers[1]]
        low, high = cfg["grasp_width_range_m"]
        gripped = c.both and low <= jaw <= high and tcp_error <= cfg["grasp_error_m"]
        detached = c.force_norm_sum <= cfg["contact_threshold_n"]
        net = np.linalg.norm(c.door_force)
        stowed = np.max(np.abs(q[self.arm_q] - self.arm_home)) < .025
        self.seen_contact += int(not detached)
        self.two_finger += int(c.both)
        self.wrong_contact += int(bool(c.unexpected))
        self.peak_force = max(self.peak_force, net)
        self.max_angle = max(self.max_angle, angle)
        self.closest_handle = min(self.closest_handle, tcp_error)
        self.unloaded = 0 if supported else self.unloaded + 1
        self.saturated = np.where(abs(d.actuator_force) >= self.effort, self.saturated + 1, 0)
        gripping = phase in ("open", "hold")
        self.lost = self.lost + 1 if gripping and not c.both else 0
        slip = np.max(np.hypot(np.nan_to_num(c.slip_long), np.nan_to_num(c.slip_lat)))
        slipping = phase in ("grasp", "open", "hold", "release") and slip > cfg["park_slip_limit_m_s"]
        self.sliding = self.sliding + 1 if slipping else 0
        qarm = d.qpos[self.arm_q]
        margin = np.minimum(qarm - self.ranges[:, 0], self.ranges[:, 1] - qarm)

        reason = None
        if not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all() or any(w.number for w in d.warning):
            reason = "nonfinite_or_solver_warning"
        elif np.min(margin) < 0:
            reason = "arm_joint_limit:" + ARM[int(np.argmin(margin))]
        elif c.unexpected:
            reason = "unexpected_contact:" + ",".join(sorted(c.unexpected))
        elif phase in ("approach_base", "settle", "post_release_hold", "stow", "retreat_base", "final") and not detached:
            reason = "door_contact_outside_manipulation"
        elif self.unloaded * self.dt >= cfg["unloaded_limit_s"] or tilt >= cfg["tilt_limit_deg"]:
            reason = "wheel_support_or_tilt"
        elif self.saturated.max() * self.dt >= cfg["sat_limit_s"]:
            reason = "persistent_saturation:" + self.actuated[int(np.argmax(self.saturated))]
        elif self.lost * self.dt >= cfg["loss_limit_s"]:
            reason = "lost_grip"
        elif self.sliding * self.dt >= cfg["park_slip_limit_s"]:
            reason = "persistent_grip_phase_wheel_slip"
        elif gripping and (not zone or tcp_error > cfg["grasp_error_m"] or net > cfg["grip_net_force_limit_n"]):
            reason = "grip_base_handle_or_load_limit"
        elif phase not in ("approach_base", "settle", "retreat_base", "final") and not zone:
            reason = "operation_station_drift"

        if phase in ("approach_base", "retreat_base"):
            ok, duration = zone and xy_error < .010 and heading < 1., .06
        elif phase == "settle":
            ok, duration = stable, cfg["settle_time_s"]
        elif phase == "reach_handle":
            ok, duration = zone and tcp_error <= cfg["grasp_error_m"], .06
        elif phase == "grasp":
            ok, duration = gripped, cfg["grasp_confirm_s"]
        elif phase == "open":
            ok, duration = reached and c.both, .15
        elif phase == "hold":
            ok, duration = reached and gripped and stable and door_speed < .01, .5
        elif phase == "release":
            ok, duration = detached and jaw >= .9 * cfg["open_width_m"], .15
        elif phase == "retreat_arm":
            ok, duration = detached and tcp_error >= .8 * cfg["retreat_distance_m"], .15
        elif phase == "stow":
            ok, duration = detached and stowed, .15
        else:
            ok, duration = stable and detached and reached and (phase != "final" or stowed), cfg["post_hold_s"]
        self.ready = self.ready + 1 if ok else 0
        self.last = dict(phase=phase, hinge_deg=angle, jaw_m=float(jaw), tcp_handle_m=float(tcp_error),
                         station_error_m=float(station_error), parking_error_m=float(park_error),
                         heading_error_deg=float(heading), base_speed_m_s=float(speed), tilt_deg=float(tilt),
                         both=bool(c.both), finger_n=c.finger_normal.tolist(), net_door_n=float(net),
                         continuous_ready_s=self.ready*self.dt)
        if not reason and self.ready * self.dt + 1e-10 >= duration:
            self.events.append(dict(**self.last, end_step=self.steps, time_s=self.steps * self.dt))
            self.i += 1
            self.phase_start, self.ready = self.steps, 0
        elif not reason and (self.steps - self.phase_start) * self.dt >= self.timeouts[phase]:
            reason = "timeout:" + phase
        if reason:
            self.failure = dict(reason=reason, step=self.steps, **self.last)
        return c

    def result(self):
        return dict(success=self.passed, first_failure=self.failure, events=self.events,
                    next_phase=self.phase, last=self.last, physics_steps=self.steps,
                    robot_door_contact_steps=self.seen_contact, bilateral_contact_steps=self.two_finger,
                    unexpected_contact_steps=self.wrong_contact, peak_net_door_n=float(self.peak_force),
                    maximum_hinge_deg=float(self.max_angle), closest_station_m=float(self.closest_station),
                    closest_handle_m=float(self.closest_handle))
