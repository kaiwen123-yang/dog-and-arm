"""Vectorized B0 scene using the Simulation interface of the O1 mjlab pin."""
import numpy as np
import torch
import warp as wp
from mjlab.sim import MujocoCfg, Simulation, SimulationCfg

from .physics import ActionMap
from .warp_audit import WarpFreeAudit


class ResearchPlant:
    def __init__(self, model, count, device):
        self.mapping = ActionMap(model)
        self.model = model
        opt = model.opt
        config = MujocoCfg(timestep=opt.timestep, integrator='implicitfast', cone='elliptic',
                           impratio=opt.impratio, iterations=opt.iterations, tolerance=opt.tolerance,
                           ls_iterations=opt.ls_iterations, ls_tolerance=opt.ls_tolerance,
                           ccd_iterations=opt.ccd_iterations, gravity=tuple(opt.gravity))
        self.sim = Simulation(count, SimulationCfg(mujoco=config, njmax=256, nconmax=128),
                              model=model, device=device)
        self.device = device
        self.count = count
        for field in ('scale', 'offset', 'bias_gain', 'finger_factor', 'actuator_ids', 'dof'):
            arr = getattr(self.mapping, field)
            setattr(self, field, torch.as_tensor(arr, device=device,
                    dtype=torch.long if arr.dtype.kind in 'iu' else torch.float32))
        self.arm_q = torch.as_tensor(self.mapping.q[16:22], device=device)
        self.arm_limits = torch.tensor(model.jnt_range[[model.joint(f'piper_joint{i}').id
                                      for i in range(1, 7)]], device=device, dtype=torch.float32)
        self.force_limit = torch.as_tensor(model.actuator_forcerange[:, 1].copy(), device=device)
        self.saturation_time = torch.zeros((count, 23), device=device)
        self.data = self.sim.data
        self.contact_audit = WarpFreeAudit(model, self.sim)
        self.indices = torch.arange(count, device=device)

    def reset(self, qpos, qvel, ids=None):
        if ids is None:
            ids = self.indices
        self.sim.reset(ids)
        self.contact_audit.reset(ids)
        self.data.qpos[ids] = qpos
        self.data.qvel[ids] = qvel
        self.saturation_time[ids] = 0.
        self.sim.forward()

    def step(self, action, record_substeps=False, on_substep=None):
        target = (action * self.scale + self.offset) * self.finger_factor
        invalid = torch.zeros(self.count, device=self.device, dtype=torch.bool)
        records = []
        for substep in range(1, 11):
            self.data.ctrl[:, self.actuator_ids] = target + self.data.qfrc_bias[:, self.dof] * self.bias_gain
            self.sim.step()
            arm = self.data.qpos[:, self.arm_q]
            q = self.data.qpos[:, 3:7]
            w, x, y, z = q.unbind(1)
            roll = torch.atan2(2*(w*x+y*z), 1-2*(x*x+y*y))
            pitch = torch.asin((2*(w*y-z*x)).clamp(-1,1))
            invalid |= self.contact_audit.step()
            sat = self.data.actuator_force[:].abs() >= .98 * self.force_limit
            self.saturation_time = torch.where(sat, self.saturation_time + .002, 0.)
            invalid |= ((arm < self.arm_limits[:, 0]) | (arm > self.arm_limits[:, 1])).any(1)
            invalid |= (torch.maximum(roll.abs(), pitch.abs()) >= np.deg2rad(5)) | (self.saturation_time.max(1).values >= .25)
            invalid |= ~torch.isfinite(self.data.qvel[:]).all(1)
            if on_substep is not None:
                on_substep(substep, invalid)
            if record_substeps:
                records.append(torch.cat([self.data.ctrl[:], self.data.actuator_force[:],
                                          self.contact_audit.wheel_loads_n, invalid[:, None]], dim=1))
        if record_substeps:
            self.substeps = torch.stack(records, dim=1)
        return invalid
