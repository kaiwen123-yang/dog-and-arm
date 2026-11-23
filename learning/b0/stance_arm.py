"""Reference-only arm Jacobian map for a root-translation feedback correction."""
import mujoco as mj
import numpy as np

from .physics import ActionMap


class ReferenceArmMap:
    """Static geometric derivative on the two provided motions. No online IK or task target."""
    def __init__(self, model, reference_qpos):
        mapping = ActionMap(model)
        data = mj.MjData(model)
        arm = mapping.dof[16:22]
        joint_q = mapping.q[16:22]
        home = model.key('home').qpos[joint_q]
        self.scale = mapping.scale[16:22]
        self.reference = reference_qpos
        self.gain = []
        for q in self.reference:
            data.qpos[:] = q
            mj.mj_kinematics(model,data)
            mj.mj_comPos(model,data)
            jp,jr = np.zeros((3,model.nv)),np.zeros((3,model.nv))
            mj.mj_jacSite(model,data,jp,jr,model.site('p4_grasp').id)
            j = np.vstack((jp[:,arm],.12*jr[:,arm]))
            # Levenberg damping and a fixed smooth amplitude envelope keep
            # nearly stowed postures from asking for a large arm correction.
            D = np.linalg.solve(j.T@j+np.eye(6)*.01**2,jp[:,arm].T)
            gate = np.clip(np.linalg.norm(q[joint_q]-home)/.25,0.,1.)
            self.gain.append(gate*D)
        self.gain = np.array(self.gain)

    def direction(self, frame, root_position):
        # Current spatial translation is privileged; all kinematic maps are
        # precomputed from the two common allowed references.
        shift = self.reference[frame,:3] - root_position
        return np.einsum('...ij,...j->...i',self.gain[frame],shift).clip(-.05,.05)
