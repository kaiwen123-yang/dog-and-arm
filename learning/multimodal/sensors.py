"""The simulated wrist and encoder/IMU interface at a policy decision boundary."""
import mujoco as mj
import numpy as np

from learning.b0.physics import ActionMap, FINGERS


SIZE = 64
CAMERA_STRIDE = 5  # 50 Hz control, 10 Hz simultaneous synthetic RGB and depth.
DEPTH_RANGE_M = (.05, 5.0)


class RobotSensors:
    def __init__(self, model, handle_site, panel_rgb=None):
        self.model = model
        self.mapping = ActionMap(model)
        self.finger2_q = model.joint(FINGERS[1]).qposadr.item()
        self.finger2_v = model.joint(FINGERS[1]).dofadr.item()
        self.tcp = model.site("p4_grasp").id
        self.handle = model.site(handle_site).id
        self.hinge = model.joint("door_single_hinge")
        self.scratch = mj.MjData(model)
        self.renderer = None
        self.option = mj.MjvOption()
        self.option.geomgroup[3:] = 0
        self.option.sitegroup[:] = 0
        if panel_rgb is not None:
            model.geom("door_single_panel").rgba[:3] = panel_rgb

    def proprio(self, qpos, qvel):
        """Return encoder position/rate, body-frame gravity direction and body gyro."""
        positions = qpos[self.mapping.q].copy()
        velocities = qvel[self.mapping.dof].copy()
        positions[-1] -= qpos[self.finger2_q]
        velocities[-1] -= qvel[self.finger2_v]
        w, x, y, z = qpos[3:7]
        gravity = [2 * (w*y-x*z), -2 * (w*x+y*z), 2 * (x*x+y*y) - 1]
        return np.concatenate((positions, velocities, gravity, qvel[3:6])).astype(np.float32)

    def object_state(self, qpos, qvel):
        """Simulator-only targets. These columns never enter deployed observations."""
        d = self.scratch
        d.qpos[:] = qpos
        mj.mj_kinematics(self.model, d)
        relative = (d.site_xpos[self.handle] - d.site_xpos[self.tcp]) @ d.site_xmat[self.tcp].reshape(3, 3)
        return np.r_[qpos[self.hinge.qposadr], qvel[self.hinge.dofadr], relative].astype(np.float32)

    def image(self, qpos, qvel):
        """Metric optical-axis depth, aligned RGB, ideal zero-latency timestamp."""
        d = self.scratch
        d.qpos[:] = qpos
        d.qvel[:] = qvel
        mj.mj_forward(self.model, d)
        if self.renderer is None:
            self.renderer = mj.Renderer(self.model, height=SIZE, width=SIZE)
        r = self.renderer
        r.update_scene(d, camera="wrist_rgbd", scene_option=self.option)
        r.disable_depth_rendering()
        rgb = r.render().copy()
        r.enable_depth_rendering()
        depth = r.render().copy()
        r.disable_depth_rendering()
        valid = np.isfinite(depth) & (depth >= DEPTH_RANGE_M[0]) & (depth <= DEPTH_RANGE_M[1])
        depth[~valid] = 0
        return rgb, depth, valid

    def close(self):
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
