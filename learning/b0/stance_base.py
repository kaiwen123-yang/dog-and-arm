"""Planar correction with stationary wheel contact Jacobians and body-frame reference errors."""
import mujoco as mj
import numpy as np
import torch

from .physics import ActionMap, LIMBS, settings


class PlanarStanceFeedback(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        d = mj.MjData(model)
        mj.mj_resetDataKeyframe(model, d, model.key("home").id)
        mj.mj_forward(model, d)
        mapping = ActionMap(model)
        root = model.body("m1_base_link").id
        rot = d.xmat[root].reshape(3,3)
        radius = settings("mobile",1)["rolling_radius_m"]
        rows, wheel = [], []
        for i, limb in enumerate(LIMBS):
            body = model.body(f"m1_{limb}_FOOT_LINK").id
            geom = next(j for j in range(model.ngeom) if model.geom_bodyid[j]==body and model.geom_contype[j])
            point = d.geom_xpos[geom] - np.array([0.,0.,radius])
            lever = rot.T @ (point-d.xpos[root])
            jac = np.zeros((3, model.nv))
            mj.mj_jac(model, d, jac, None, point, body)
            block = rot.T @ jac[:,mapping.dof[3*i:3*i+3]]
            rows.extend(np.linalg.solve(block, [[0.,0.],[-1.,-lever[0]],[0.,0.]]))
            joint = model.joint(f"m1_{limb}_FOOT_JOINT").id
            sign = np.sign(d.xaxis[joint] @ rot[:,1])
            wheel.append(sign*np.array([1.,-lever[1]]) / radius)
        gain = np.asarray(rows) / mapping.scale[:12,None]
        for name, x in (("leg_map",gain),("leg_inverse",np.linalg.pinv(gain)),
                        ("wheel_map", np.asarray(wheel)/mapping.scale[12:16,None])):
            self.register_buffer(name,torch.tensor(x,dtype=torch.float32))

    def forward(self, baseline, previous, local_xy, relative_yaw, rate):
        # Relative-yaw and lateral error move the neutral leg stance so all four
        # contacts can support the correction. Along-track speed goes to the wheels.
        error = torch.cat((local_xy,relative_yaw[:,None]),dim=1)
        tolerance=error.new_tensor([.001,.001,.002])
        error=error.sign()*(error.abs()-tolerance).clamp_min(0)
        # Observable servo memory: project the last 12 issued commands relative
        # to the current backbone output onto the two declared stance directions.
        previous_trim = (previous[:,:12]-baseline[:,:12]) @ self.leg_inverse.T
        previous_trim = torch.where(previous_trim.abs()>error.new_tensor([.0003,.001]),
                                    previous_trim, torch.zeros_like(previous_trim))
        trim=(previous_trim + .02*rate*error[:,1:]).clamp(-error.new_tensor([.075,.20]),error.new_tensor([.075,.20]))
        legs=(trim @ self.leg_map.T).clamp(-.70,.70)
        wheels=(rate*error[:,[0,2]] @ self.wheel_map.T).clamp(-.25,.25)
        return torch.cat((baseline[:,:12]+legs,baseline[:,12:16]+wheels,baseline[:,16:]),dim=1)
