"""Batched held-target interaction and 2 ms contact audit on MuJoCo-Warp.

This collector marks failed windows for replay. Full reference/phase success
is decided separately by the read-only task evaluator.
"""
import numpy as np
import torch
import warp as wp
import mujoco_warp as mjw

from .physics import LIMBS, settings
from .research_env import ResearchPlant
from .contact_clock import ContactClock

PHASES = ('approach_base', 'settle', 'pregrasp', 'approach_arm', 'grasp', 'open', 'hold',
          'release', 'retreat_arm', 'post_release_hold', 'stow', 'retreat_base', 'final')
PHASE_ID = {name: i for i, name in enumerate(PHASES)}
REASONS = ('none', 'nonfinite', 'buffer_capacity', 'arm_joint_limit', 'unexpected_contact',
           'door_contact_outside_manipulation', 'wheel_support_or_tilt', 'persistent_saturation',
           'lost_grip', 'persistent_grip_phase_wheel_slip', 'grip_handle_error', 'door_force_limit')
REASON = {name: i for i, name in enumerate(REASONS)}


@wp.kernel
def _door_wrenches(nacon: wp.array[int], world: wp.array[int], geoms: wp.array[wp.vec2i],
                   frames: wp.array[wp.mat33], point: wp.array[wp.vec3],
                   table: wp.array2d[int], robot_geom: wp.array[int], body: wp.array[int],
                   root: int, side: wp.array[int], com: wp.array2d[wp.vec3],
                   cvel: wp.array2d[wp.spatial_vector], force: wp.array[wp.spatial_vector],
                   load_cutoff: float, metrics: wp.array2d[float]):
    c = wp.tid()
    if c >= nacon[0]:
        return
    normal = force[c][0]
    if normal <= 0.0:
        return
    g1 = geoms[c][0]
    g2 = geoms[c][1]
    category = table[g1, g2]
    if category < 0:
        return
    w = world[c]
    if category < 4:
        wp.atomic_add(metrics, w, category, normal)
        if normal > load_cutoff:
            b = body[g2]
            if robot_geom[g1] == 1:
                b = body[g1]
            twist = cvel[w,b]
            v = wp.spatial_bottom(twist) + wp.cross(wp.spatial_top(twist), point[c] - com[w, root])
            wp.atomic_max(metrics, w, 11, wp.sqrt(v[0]*v[0] + v[1]*v[1]))
    else:
        # 4/5 are the front two fingers on the front rod, 6/7 the back rod;
        # 8 includes other robot/door contacts, 9 all other robot contacts.
        if category < 9:
            local = wp.spatial_top(force[c])
            f = wp.transpose(frames[c]) * local
            if robot_geom[g1] == 1:
                f = -f
            for j in range(3):
                wp.atomic_add(metrics, w, 6+j, f[j])
            wp.atomic_add(metrics, w, 9, wp.length(local))
        finger = category - 4 - 2 * side[w]
        if finger == 0 or finger == 1:
            wp.atomic_add(metrics, w, 4+finger, normal)
        else:
            wp.atomic_max(metrics, w, 10, normal)


class ContactPlant(ResearchPlant):
    def __init__(self, model, count, device, preserve_continuous_bias=False):
        self.preserve_continuous_bias = preserve_continuous_bias
        super().__init__(model, count, device)
        self.clock = ContactClock(float(model.opt.timestep))
        # At a refined step the last internal solve is newer than the external
        # controller's sample. Store its own delayed input across policy calls.
        self.servo_bias = (torch.zeros_like(self.data.qfrc_bias[:])
                           if self.clock.servo_stride > 1 else None)
        cfg = settings('mobile', 1)
        self.cfg = cfg
        self.count_limits = {key: round(cfg[key]/model.opt.timestep) for key in
                             ('unloaded_limit_s','loss_limit_s','sat_limit_s','park_slip_limit_s')}
        self.root_id = model.body('m1_base_link').id
        gbody = model.geom_bodyid
        robot = model.body_rootid[gbody] == self.root_id
        door = np.array([(model.geom(i).name or '').startswith('door_single_') for i in range(model.ngeom)])
        table = np.where(robot[:, None] | robot[None, :], 9, -1).astype(np.int32)
        table[(robot[:,None] & door[None,:]) | (door[:,None] & robot[None,:])] = 8
        floor = model.geom('preview_floor').id
        for i, limb in enumerate(LIMBS):
            wheel = gbody == model.body(f'm1_{limb}_FOOT_LINK').id
            table[wheel, floor] = table[floor, wheel] = i
        for bit, name in enumerate(('front', 'back')):
            rod = model.geom(f'door_single_{name}_handle_grip').id
            for finger in range(2):
                geometries = gbody == model.body(f'piper_gripper_link{finger+1}').id
                table[geometries, rod] = table[rod, geometries] = 4+2*bit+finger
        device_wp = self.sim.wp_device
        self.pair = wp.array(table, dtype=int, device=device_wp)
        self.robot_geom = wp.array(robot.astype(np.int32), dtype=int, device=device_wp)
        self.geom_bodies = wp.array(gbody.astype(np.int32), dtype=int, device=device_wp)
        self.metrics_wp = wp.zeros((count, 12), dtype=float, device=device_wp)
        self.metrics = wp.to_torch(self.metrics_wp)
        self.load_ticks = torch.zeros(count, dtype=torch.int32, device=device)
        self.lost_ticks = torch.zeros_like(self.load_ticks)
        self.slip_ticks = torch.zeros_like(self.load_ticks)
        self.sat_ticks = torch.zeros((count,23), dtype=torch.int32, device=device)
        self.tcp_id = model.site('p4_grasp').id
        self.rod_ids = torch.tensor([model.site(f'door_single_{side}_handle').id for side in ('front','back')],
                                    device=device)
        self.scale, self.offset, self.bias_gain, self.finger_factor = [
            item.float() for item in (self.scale, self.offset, self.bias_gain, self.finger_factor)]
        self.force_limit = self.force_limit.float()

    def reset(self, qpos, qvel, ids=None):
        # The controller consumes the preceding solve's bias. Reset refreshes
        # all worlds, including unrelated continuous lanes; preserve their input.
        keep = self.indices[~torch.isin(self.indices, ids)] if (
            self.preserve_continuous_bias and ids is not None and len(ids) < self.count
        ) else None
        if keep is not None:
            bias = wp.to_torch(self.sim.wp_data.qfrc_bias)
            old_bias = bias[keep]
        super().reset(qpos, qvel, ids)
        if keep is not None:
            bias[keep] = old_bias
        chosen = slice(None) if ids is None else ids
        if self.servo_bias is not None:
            self.servo_bias[chosen] = self.data.qfrc_bias[chosen]
        for counter in (self.load_ticks, self.lost_ticks, self.slip_ticks, self.sat_ticks):
            counter[chosen] = 0

    def _contacts(self, side_wp):
        sim, base = self.sim, self.contact_audit
        data = sim.wp_data
        current = torch.cuda.current_stream(self.device)
        base._torch_stream.wait_stream(current)
        with wp.ScopedStream(base._wp_stream):
            self.metrics_wp.zero_()
            mjw.contact_force(sim.wp_model, data, base._ids, False, base._force)
            wp.launch(_door_wrenches, dim=data.naconmax, device=sim.wp_device, inputs=[
                data.nacon, data.contact.worldid, data.contact.geom, data.contact.frame, data.contact.pos,
                self.pair, self.robot_geom, self.geom_bodies, self.root_id, side_wp, data.subtree_com,
                data.cvel, base._force, self.cfg['contact_threshold_n'], self.metrics_wp])
        current.wait_stream(base._torch_stream)

    def step_contact(self, actions, side_bits, phase_ids, record=False, measure_peak_force=False,
                     capture_first_failure_state=False, measure_grip=False, stop_at_first_failure=False):
        if stop_at_first_failure and self.count != 1:
            raise ValueError('Early stop requires a single diagnostic world')
        if actions.shape != (self.count, 23):
            raise ValueError('Expected one clipped action per world with 23 channels')
        if side_bits.shape != (self.count,) or phase_ids.shape not in (
                (self.count,), (self.count, self.clock.reference_ticks)):
            raise ValueError('Side and phase must identify each world')
        side_bits = side_bits.to(device=self.device, dtype=torch.int32).contiguous()
        phase_ids = phase_ids.to(self.device)
        side_wp = wp.from_torch(side_bits, dtype=wp.int32)
        actions = actions.to(self.device)
        finite = actions.isfinite().all(-1) & (actions.abs() <= 1.).all(-1)
        if not bool(finite.all()):
            raise ValueError('step_contact expects finite post-clamp policy commands')
        target = (actions * self.scale + self.offset) * self.finger_factor
        first = torch.zeros(self.count, device=self.device, dtype=torch.int32)
        peak_force = torch.zeros(self.count, device=self.device) if measure_peak_force else None
        if measure_grip:
            finger_min = torch.full((self.count,2), torch.inf, device=self.device)
            finger_max = torch.zeros(self.count,device=self.device)
            dual_prefix = torch.zeros_like(first)
            dual_alive = torch.ones_like(finite)
        if capture_first_failure_state:
            stop_q = torch.zeros_like(self.data.qpos[:])
            stop_v = torch.zeros_like(self.data.qvel[:])
            stop_valid = torch.zeros_like(finite)
        reason = torch.zeros_like(first)
        overflow = torch.zeros_like(first)
        rod_id = self.rod_ids[side_bits.long()]
        records = {}
        cfg, data = self.cfg, self.data
        limits = self.count_limits
        stride = self.clock.servo_stride
        for substep in range(self.clock.policy_steps):
            phase = phase_ids if phase_ids.ndim == 1 else phase_ids[:,substep // stride]
            # MuJoCo contact forces/site positions after step describe this
            # solve's interval-start pose. Signed arm margins check integrated q.
            q0 = data.qpos[:, 3:7].clone()
            servo_tick = substep % stride == 0
            if servo_tick:
                bias = data.qfrc_bias if self.servo_bias is None else self.servo_bias
                data.ctrl[:, self.actuator_ids] = target + bias[:, self.dof] * self.bias_gain
            self.sim.step()
            if servo_tick and self.servo_bias is not None:
                self.servo_bias.copy_(data.qfrc_bias[:])
            self._contacts(side_wp)
            m = self.metrics
            grip = (phase == PHASE_ID['open']) | (phase == PHASE_ID['hold'])
            active = (phase >= PHASE_ID['grasp']) & (phase <= PHASE_ID['release'])
            free = (phase <= PHASE_ID['pregrasp']) | (phase >= PHASE_ID['post_release_hold'])
            self.load_ticks = torch.where((m[:,:4] < cfg['wheel_threshold_n']).any(1), self.load_ticks+1, 0)
            self.lost_ticks = torch.where(grip & (m[:,4:6] <= cfg['contact_threshold_n']).any(1), self.lost_ticks+1, 0)
            self.slip_ticks = torch.where(active & (m[:,11] > cfg['park_slip_limit_m_s']), self.slip_ticks+1, 0)
            self.sat_ticks = torch.where(data.actuator_force[:].abs() >= cfg['sat_fraction']*self.force_limit, self.sat_ticks+1, 0)
            arm = data.qpos[:,self.arm_q]
            margin = torch.minimum(arm - self.arm_limits[:,0], self.arm_limits[:,1] - arm)
            w, x, y, z = q0.unbind(-1)
            tilt = torch.maximum(torch.atan2(2*(w*x+y*z), 1-2*(x*x+y*y)).abs(),
                                 torch.asin((2*(w*y-z*x)).clamp(-1,1)).abs())
            force_norm = torch.linalg.vector_norm(m[:,6:9], dim=-1)
            grip_error = torch.linalg.vector_norm(data.site_xpos[self.indices,rod_id] - data.site_xpos[:,self.tcp_id], dim=-1)
            bits = self.contact_audit.overflow_bits
            capacity = bits & self.contact_audit.buffer_mask
            capacity = torch.where(data.nefc[:] > self.sim.wp_data.njmax, capacity | (1 << 30), capacity)
            overflow |= capacity
            numerical = (torch.isfinite(data.qpos[:]).all(1) & torch.isfinite(data.qvel[:]).all(1)
                         & torch.isfinite(m).all(1) & torch.isfinite(data.actuator_force[:]).all(1))
            finite &= numerical & (capacity == 0)
            failures = (~numerical, capacity != 0, (margin < 0).any(1),
                        m[:,10] > cfg['contact_threshold_n'], free & (m[:,9] > cfg['contact_threshold_n']),
                        (self.load_ticks >= limits['unloaded_limit_s']) | (tilt >= np.deg2rad(cfg['tilt_limit_deg'])),
                        (self.sat_ticks >= limits['sat_limit_s']).any(1), self.lost_ticks >= limits['loss_limit_s'],
                        self.slip_ticks >= limits['park_slip_limit_s'], grip & (grip_error > cfg['grasp_error_m']),
                        grip & (force_norm > cfg['grip_net_force_limit_n']))
            for code, failed in enumerate(failures, 1):
                hit = (first == 0) & failed
                reason = torch.where(hit, code, reason)
                first = torch.where(hit, substep+1, first)
            if capture_first_failure_state:
                stopped = first == substep + 1
                stop_q = torch.where(stopped[:, None], data.qpos[:], stop_q)
                stop_v = torch.where(stopped[:, None], data.qvel[:], stop_v)
                stop_valid |= stopped & finite
            if measure_grip:
                finger_min = torch.minimum(finger_min, m[:,4:6])
                finger_max = torch.maximum(finger_max,m[:,4:6].amax(-1))
                dual_alive &= (m[:,4:6] > cfg['contact_threshold_n']).all(1) & (first==0)
                dual_prefix += dual_alive.long()
            if measure_peak_force:
                peak_force = torch.maximum(peak_force, force_norm)
            if record:
                fields = dict(finger_load_N=m[:,4:6], wheel_load_N=m[:,:4], door_robot_force_N=m[:,6:9],
                              door_force_norm_sum_N=m[:,9], unexpected_contact_N=m[:,10], wheel_slip_m_s=m[:,11],
                              arm_limit_margin_rad=margin, grip_error_m=grip_error, ctrl=data.ctrl[:],
                              actuator_force=data.actuator_force[:], overflow_bits=bits, qpos_post=data.qpos[:],
                              qvel_post=data.qvel[:], numerical_valid=numerical, first_fail_substep=first)
                for key, value in fields.items():
                    records.setdefault(key, []).append(value.clone())
            if stop_at_first_failure and first.item():
                break
        result = dict(first_fail_substep=first, reason=reason, overflow=overflow,
                      valid_full_interval=finite, physics_steps=torch.full_like(first, substep + 1))
        if measure_grip:
            result.update(finger_min=finger_min,finger_max=finger_max,dual_prefix=dual_prefix)
        if capture_first_failure_state:
            result.update(stop_qpos=stop_q, stop_qvel=stop_v, stop_valid=stop_valid)
        if measure_peak_force:
            result['peak_force_n'] = peak_force
        if record:
            result['substeps'] = {key:torch.stack(values, 1) for key,values in records.items()}
        return result
