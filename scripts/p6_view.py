"""Single Linux desktop window, overview and gripper detail from the same MjData."""
import signal
import time
import glfw
import imageio.v2 as imageio
import mujoco as mj
import numpy as np


class DoorView:
    def __init__(self, model, data, handle_id, cfg, out, video):
        if not glfw.init():
            raise RuntimeError('Cannot open Linux desktop with GLFW')
        self.title = f"P6 / FREE_BASE / mj_step  |  {cfg['stage']}  C{cfg['case']:02}"
        glfw.window_hint(glfw.RESIZABLE, glfw.FALSE)
        self.window = glfw.create_window(1120, 704, self.title, None, None)
        if not self.window:
            raise RuntimeError('GLFW window creation failed')
        glfw.make_context_current(self.window)
        glfw.swap_interval(0)
        glfw.show_window(self.window)
        glfw.focus_window(self.window)
        self.m, self.d, self.handle = model, data, handle_id
        self.main = mj.MjvCamera()
        self.main.type = mj.mjtCamera.mjCAMERA_FIXED
        self.main.fixedcamid = model.camera('p6_overview').id
        self.detail = mj.MjvCamera()
        self.view_azimuth = 235 if cfg['stage'] == 'push' else 55
        self.hinge_q = model.joint('door_single_hinge').qposadr[0]
        self.detail.elevation = -22
        self.detail.distance = .39
        self.opt = mj.MjvOption()
        self.opt.geomgroup[3:5] = 0
        self.scene = mj.MjvScene(model, maxgeom=3000)
        self.ctx = mj.MjrContext(model, mj.mjtFontScale.mjFONTSCALE_150)
        w, h = glfw.get_framebuffer_size(self.window)
        self.rect = mj.MjrRect(0, 0, w, h)
        self.inset = mj.MjrRect(w-w//3, h-h//3, w//3, h//3)
        self.pixels = np.empty((h, w, 3), dtype=np.uint8)
        self.writer = imageio.get_writer(out/'motion.mp4', fps=25, codec='libx264', quality=6) if video else None
        self.frames = 0
        self.paused = False
        self.leave = False
        self.last_lines = ('', '')
        glfw.set_key_callback(self.window, self.key)
        signal.signal(signal.SIGUSR1, lambda *_: setattr(self, 'leave', True))

    def key(self, window, key, scancode, action, mods):
        if action == glfw.PRESS:
            if key == glfw.KEY_SPACE:
                self.paused = not self.paused
            if key == glfw.KEY_ESCAPE:
                glfw.set_window_should_close(window, True)

    def draw(self, left, right, record=True):
        self.last_lines = (left, right)
        self.detail.lookat[:] = self.d.site_xpos[self.handle]
        self.detail.azimuth = self.view_azimuth + np.rad2deg(self.d.qpos[self.hinge_q])
        mj.mjv_updateScene(self.m, self.d, self.opt, None, self.main, mj.mjtCatBit.mjCAT_ALL, self.scene)
        mj.mjr_render(self.rect, self.scene, self.ctx)
        mj.mjv_updateCamera(self.m, self.d, self.detail, self.scene)
        mj.mjr_render(self.inset, self.scene, self.ctx)
        mj.mjr_overlay(mj.mjtFont.mjFONT_NORMAL, mj.mjtGridPos.mjGRID_TOPLEFT, self.rect, left, right, self.ctx)
        if self.writer and record:
            mj.mjr_readPixels(self.pixels, None, self.rect, self.ctx)
            self.writer.append_data(self.pixels[::-1])
        self.frames += int(record)
        glfw.swap_buffers(self.window)
        glfw.poll_events()

    def handle_pause(self):
        start = time.monotonic()
        while self.paused and self.running():
            glfw.set_window_title(self.window, self.title + '  |  PAUSED')
            glfw.wait_events_timeout(.05)
        glfw.set_window_title(self.window, self.title)
        return time.monotonic() - start

    def running(self):
        return not glfw.window_should_close(self.window)

    def finish_video(self):
        if self.writer:
            self.writer.close()
            self.writer = None

    def close(self, hold, result):
        self.finish_video()
        glfw.set_window_title(self.window, self.title + '  |  ' + result)
        left, right = self.last_lines
        while hold and self.running() and not self.leave:
            self.draw(left + '\nReview', right + '\n' + result, record=False)
            glfw.wait_events_timeout(.12)
        self.ctx.free()
        glfw.destroy_window(self.window)
        glfw.terminate()
