"""Named M1/Piper servo mapping shared by native and research MuJoCo."""
from pathlib import Path
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from p6_contacts import ContactMeter
from p6_scene import build, settings

LIMBS = ('FAR', 'FBL', 'RAR', 'RBL')
LEGS = [f'm1_{limb}_{axis}_JOINT' for limb in LIMBS for axis in ('ABAD', 'HIP', 'KNEE')]
WHEELS = [f'm1_{limb}_FOOT_JOINT' for limb in LIMBS]
ARM = [f'piper_joint{i}' for i in range(1, 7)]
FINGERS = ['piper_gripper_joint1', 'piper_gripper_joint2']


def make_model(side='mobile', case=1):
    return build(settings(side, case))


class ActionMap:
    def __init__(self, model):
        self.names = LEGS + WHEELS + ARM + FINGERS[:1]
        joints = np.array([model.joint(n).id for n in self.names])
        self.actuator_ids = np.array([np.flatnonzero(model.actuator_trnid[:, 0] == j).item()
                                      for j in joints])
        self.dof = model.jnt_dofadr[joints]
        self.q = model.jnt_qposadr[joints]
        home = model.key('home').qpos[self.q]
        arm_limits = model.jnt_range[joints[16:22]]
        self.offset = np.r_[home[:12], np.zeros(4), arm_limits.mean(axis=1), .05]
        self.scale = np.r_[np.full(12, .35), np.full(4, 6.), np.diff(arm_limits).ravel() / 2, .05]
        self.bias_gain = 1 / model.actuator_gainprm[self.actuator_ids, 0]
        self.bias_gain[12:16] = 0.
        self.finger_factor = np.ones(23)
        self.finger_factor[-1] = .5

    def describe(self, model):
        return [dict(channel=i, joint=n, actuator=model.actuator(a).name, xml_index=int(a),
                     unit='rad/s' if n in WHEELS else 'm opening' if n in FINGERS else 'rad',
                     scale=float(self.scale[i]), offset=float(self.offset[i]),
                     kp_or_wheel_kv=float(model.actuator_gainprm[a, 0]),
                     velocity_feedback=float(-model.actuator_biasprm[a, 2]),
                     force_range=model.actuator_forcerange[a].tolist())
                for i, (n, a) in enumerate(zip(self.names, self.actuator_ids))]


class NativePlant:
    """Free-motion evaluation. A callback can record each solved substep."""
    def __init__(self, model):
        self.model, self.data = model, mj.MjData(model)
        self.mapping = ActionMap(model)
        self.meter = ContactMeter(model, 'preview_floor')
        self.arm_range = model.jnt_range[[model.joint(n).id for n in ARM]]
        self.limit = model.actuator_forcerange[:, 1]

    def reset(self, qpos, qvel):
        mj.mj_resetData(self.model, self.data)
        self.data.qpos[:] = qpos
        self.data.qvel[:] = qvel
        mj.mj_forward(self.model, self.data)
        self.unloaded_time = 0.
        self.sat_time = np.zeros(23)

    def step(self, clipped_action, on_substep=None):
        d, m, a = self.data, self.model, self.mapping
        action = np.asarray(clipped_action)
        if action.shape != (23,) or not np.isfinite(action).all() or np.any(np.abs(action) > 1):
            raise ValueError('expected 23 finite post-clamp actions in [-1,1]')
        target = (a.offset + a.scale * action) * a.finger_factor
        reason = None
        for sub in range(10):
            d.ctrl[a.actuator_ids] = target + d.qfrc_bias[a.dof] * a.bias_gain
            mj.mj_step(m, d)
            contact = self.meter.measure(d)
            arm = d.qpos[a.q[16:22]]
            q = d.qpos[3:7]
            tilt = np.arccos(np.clip(1 - 2 * (q[1]**2 + q[2]**2), -1, 1))
            self.unloaded_time = 0. if all(contact.supported) else self.unloaded_time + m.opt.timestep
            self.sat_time = np.where(abs(d.actuator_force) >= .98 * self.limit,
                                     self.sat_time + m.opt.timestep, 0.)
            if np.any(arm < self.arm_range[:, 0]) or np.any(arm > self.arm_range[:, 1]):
                reason = 'arm_joint_limit'
            elif contact.unexpected or np.any(contact.finger_normal > .01):
                reason = 'unexpected_contact'
            elif tilt > np.deg2rad(5):
                reason = 'tilt'
            elif self.unloaded_time > .1:
                reason = 'wheel_unloaded'
            elif self.sat_time.max() > .25:
                reason = 'saturation'
            elif not np.isfinite(d.qvel).all() or any(w.number for w in d.warning):
                reason = 'solver_warning'
            if on_substep:
                on_substep(d, contact)
            if reason:
                break
        return dict(physics_steps=sub + 1, failure_reason=reason)
