"""Neutral-stance Jacobian for the yaw component of the 12 physical leg targets."""
import mujoco as mj
import numpy as np

from .physics import ActionMap, LIMBS, settings


def yaw_trim_vector(model):
    d = mj.MjData(model)
    mj.mj_resetDataKeyframe(model, d, model.key("home").id)
    mj.mj_forward(model, d)
    mapping = ActionMap(model)
    root = model.body("m1_base_link").id
    rotation = d.xmat[root].reshape(3, 3)
    radius = settings("mobile", 1)["rolling_radius_m"]
    rows = []
    for index, limb in enumerate(LIMBS):
        body = model.body(f"m1_{limb}_FOOT_LINK").id
        geom = next(i for i in range(model.ngeom) if model.geom_bodyid[i] == body and model.geom_contype[i])
        point = d.geom_xpos[geom] - np.array([0., 0., radius])
        lever = (rotation.T @ (point-d.xpos[root]))[0]
        jac = np.empty((3, model.nv))
        mj.mj_jac(model, d, jac, None, point, body)
        dofs = mapping.dof[3*index:3*index+3]
        rows.extend(np.linalg.solve(rotation.T @ jac[:, dofs], [0., -lever, 0.]))
    return np.asarray(rows)
