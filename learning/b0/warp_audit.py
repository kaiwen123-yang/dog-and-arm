"""Read-only free-motion contact audit for the pinned MuJoCo-Warp 3.16 solver."""
import math

import mujoco_warp as mjw
import numpy as np
import torch
import warp as wp

from .physics import LIMBS, settings

# Pair categories above the four wheel ordinals. Ignore contacts solely in the scene.
OTHER = wp.constant(4)
DOOR = wp.constant(5)


@wp.kernel
def _sum_contacts(nacon: wp.array[int], world: wp.array[int], geom: wp.array[wp.vec2i],
                  pair: wp.array2d[int], force: wp.array[wp.spatial_vector],
                  metrics: wp.array2d[float]):
    c = wp.tid()
    if c >= nacon[0]:
        return
    category = pair[geom[c][0], geom[c][1]]
    normal = force[c][0]
    if normal <= 0.0 or category < 0:
        return
    w = world[c]
    if category < OTHER:
        wp.atomic_add(metrics, w, category, normal)
    else:
        # P6 cutoff for individual unexpected contacts is in normal force.
        wp.atomic_max(metrics, w, OTHER, normal)
        if category == DOOR:
            # Free-motion P6 phases also bound the sum of all door force norms.
            wp.atomic_add(metrics, w, DOOR, wp.length(wp.spatial_top(force[c])))


@wp.kernel
def _finish_audit(metrics: wp.array2d[float], unloaded: wp.array[int], overflow: wp.array[int],
                  counts: wp.array[int], capacity: int, contact_limit: float,
                  wheel_limit: float, max_unloaded: int, buffer_mask: int,
                  invalid: wp.array[bool]):
    w = wp.tid()
    supported = True
    for i in range(4):
        if metrics[w, i] < wheel_limit:
            supported = False
    if supported:
        unloaded[w] = 0
    else:
        unloaded[w] += 1
    invalid[w] = (unloaded[w] >= max_unloaded or metrics[w, OTHER] > contact_limit
                  or metrics[w, DOOR] > contact_limit or (overflow[w] & buffer_mask) != 0
                  or counts[w] > capacity)


class WarpFreeAudit:
    """Use immediately after each sim.step(). All output tensors refer to the latest step.

    overflow_bits include iteration-cap flags. Those two diagnostic flags alone do
    not indicate discarded constraints and do not fail the buffer-capacity gate.
    Warp itself clears overflow_bits only when that world resets.
    """
    def __init__(self, model, sim):
        cfg = settings("mobile", 1)
        self.sim = sim
        self._data = data = sim.wp_data
        self._device = sim.wp_device
        self._wp_stream = wp.get_stream(self._device)
        self._torch_stream = wp.stream_to_torch(self._wp_stream)
        self.contact_limit = float(cfg["contact_threshold_n"])
        self.wheel_limit = float(cfg["wheel_threshold_n"])
        self.max_unloaded_steps = math.ceil(cfg["unloaded_limit_s"] / model.opt.timestep - 1e-10)
        self.buffer_mask = int(mjw.OverflowType.ALL &
                               ~(mjw.OverflowType.ITERATIONS | mjw.OverflowType.LS_ITERATIONS))
        geom_body = model.geom_bodyid
        robot = model.body_rootid[geom_body] == model.body("m1_base_link").id
        door = np.array([(model.geom(i).name or "").startswith("door_single_")
                         for i in range(model.ngeom)])
        pair = np.where(robot[:, None] | robot[None, :], 4, -1).astype(np.int32)
        pair[(robot[:, None] & door[None, :]) | (door[:, None] & robot[None, :])] = 5
        floor = model.geom("preview_floor").id
        for i, limb in enumerate(LIMBS):
            wheels = geom_body == model.body(f"m1_{limb}_FOOT_LINK").id
            pair[wheels, floor] = pair[floor, wheels] = i

        self._pair = wp.array(pair, dtype=int, device=self._device)
        self._ids = wp.array(np.arange(data.naconmax, dtype=np.int32), device=self._device)
        self._force = wp.empty(data.naconmax, dtype=wp.spatial_vector, device=self._device)
        self._metrics = wp.zeros((sim.num_envs, 6), dtype=float, device=self._device)
        self._unloaded = wp.zeros(sim.num_envs, dtype=int, device=self._device)
        self._invalid = wp.zeros(sim.num_envs, dtype=bool, device=self._device)
        metrics = wp.to_torch(self._metrics)
        self.wheel_loads_n = metrics[:, :4]
        self.peak_other_normal_n = metrics[:, 4]
        self.door_force_norm_sum_n = metrics[:, 5]
        self.unloaded_steps = wp.to_torch(self._unloaded)
        self.overflow_bits = wp.to_torch(data.overflow)
        self.invalid = wp.to_torch(self._invalid)

    def reset(self, ids=None):
        """Clear only the audit's consecutive-step timer at an environment reset."""
        current = torch.cuda.current_stream(self.sim.device)
        self._torch_stream.wait_stream(current)
        with torch.cuda.stream(self._torch_stream):
            if ids is None:
                self.unloaded_steps.zero_()
            else:
                self.unloaded_steps[ids] = 0
        current.wait_stream(self._torch_stream)

    def step(self):
        """Reduce solved contacts by world. Never changes a MuJoCo model or data field."""
        data = self._data
        current = torch.cuda.current_stream(self.sim.device)
        # Keep solver and audit ordered, including consumers on a torch stream.
        self._torch_stream.wait_stream(current)
        with wp.ScopedStream(self._wp_stream):
            self._metrics.zero_()
            mjw.contact_force(self.sim.wp_model, data, self._ids, False, self._force)
            wp.launch(_sum_contacts, dim=data.naconmax,
                      inputs=[data.nacon, data.contact.worldid, data.contact.geom, self._pair,
                              self._force, self._metrics], device=self._device)
            wp.launch(_finish_audit, dim=self.sim.num_envs,
                      inputs=[self._metrics, self._unloaded, data.overflow, data.nefc, data.njmax,
                              self.contact_limit, self.wheel_limit, self.max_unloaded_steps,
                              self.buffer_mask, self._invalid], device=self._device)
        current.wait_stream(self._torch_stream)
        return self.invalid
