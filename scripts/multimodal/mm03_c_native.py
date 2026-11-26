"""Persistent native MuJoCo 3.3 lanes controlled by one differentiable, batched Torch policy."""
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import pickle
import struct
import subprocess
import sys
import time
import traceback

import numpy as np


def send(stream, value):
    blob = pickle.dumps(value, protocol=5)
    stream.write(struct.pack("<I", len(blob)))
    stream.write(blob)
    stream.flush()


def receive(stream):
    header = stream.read(4)
    if not header:
        raise EOFError("MM03 native stream closed")
    size, = struct.unpack("<I", header)
    data = stream.read(size)
    if len(data) != size:
        raise EOFError("Incomplete MM03 native response")
    return pickle.loads(data)


class NativePool:
    def __init__(self, workers):
        self.workers = []
        self.owner = {}
        socket = os.environ.get("MM03_INFERENCE_SOCKET")
        self.unit = os.environ.get("MM03_UNIT")
        self.run_root = (Path(socket).parent.parent if self.unit in ("B","C") and socket else None)
        self.clear_timing()
        self.spawn(workers)
        self.log_change("start",[],[w.pid for w in self.workers])

    def clear_timing(self):
        self.since = time.monotonic()
        self.native_steps = self.windows = 0
        self.reset_wall = self.advance_wall = 0.

    def spawn(self, workers):
        repo = Path(__file__).resolve().parents[2]
        for _ in range(workers):
            proc = subprocess.Popen([str(repo / ".venv/bin/python"), "-u", "-m", __name__ if
                 __name__ != "__main__" else "scripts.multimodal.mm03_c_native", "--worker"],
                 cwd=repo, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                 env={**os.environ, "MKL_NUM_THREADS":"1", "OMP_NUM_THREADS":"1", "OPENBLAS_NUM_THREADS":"1"})
            self.workers.append(proc)

    def log_change(self, reason, old, new):
        if self.run_root is None:
            return
        wall = time.monotonic()-self.since
        record = dict(utc=datetime.now(timezone.utc).isoformat(), reason=reason, pid=os.getpid(),
                      before=len(old), after=len(new), previous_native_pids=old, native_pids=new,
                      previous_windows=self.windows, previous_native_substeps=self.native_steps,
                      previous_reset_wall_s=self.reset_wall, previous_native_advance_wall_s=self.advance_wall,
                      previous_wall_s=wall, before_substeps_per_wall_s=self.native_steps/wall if wall else None,
                      before_substeps_per_advance_s=self.native_steps/self.advance_wall if self.advance_wall else None)
        path=self.run_root/self.unit/"native_pool_changes.jsonl"
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open("a") as stream:
            stream.write(json.dumps(record, allow_nan=False)+"\n")

    def sync_target(self):
        if self.run_root is None:
            return
        path = self.run_root/"resources"/"worker_targets.json"
        if not path.is_file():
            return
        target = json.loads(path.read_text())
        key="B_CF" if self.unit=="B" else "C"
        n = target.get("workers",target).get(key,len(self.workers))
        if self.unit=="B" and n==0:
            return
        if type(n) is not int or not 1 <= n <= 25:
            raise ValueError(f"Invalid MM03 C native-worker target: {n!r}")
        if n != len(self.workers):
            old = [w.pid for w in self.workers]
            if n>len(old):
                self.spawn(n-len(old))
            else:
                self.drain(keep=n)
            self.log_change("resize_before_independent_batch",old,[w.pid for w in self.workers])
            self.clear_timing()

    def dispatch(self, op, payloads):
        pending = []
        for worker, grouped in zip(self.workers, payloads):
            if grouped:
                try:
                    send(worker.stdin, (op, grouped))
                except (OSError, ValueError):
                    # Workers already dispatched can be blocked sending images. Consume
                    # their replies before higher-level checkpoint recovery waits on them.
                    self.collect(pending)
                    raise
                pending.append(worker)
        return pending

    @staticmethod
    def collect(pending):
        result = {}
        problem = None
        for worker in pending:
            try:
                ok, reply = receive(worker.stdout)
                if ok:
                    result.update(reply)
                else:
                    problem = problem or RuntimeError(reply)
            except (EOFError, OSError) as error:
                problem = problem or error
        if problem is not None:
            raise problem
        return result

    def reset(self, paths):
        self.sync_target()
        begin = time.monotonic()
        n = len(self.workers)
        self.owner = {i: i % n for i in range(len(paths))}
        payloads = [{} for _ in self.workers]
        for i, path in enumerate(paths):
            payloads[self.owner[i]][i] = str(path)
        records=self.collect(self.dispatch("reset", payloads))
        self.windows += len(paths)
        self.reset_wall += time.monotonic()-begin
        return records

    def start_step(self, slots, actions):
        payloads = [{} for _ in self.workers]
        for i, action in zip(slots, actions, strict=True):
            payloads[self.owner[i]][i] = np.asarray(action, dtype=np.float32)
        begin=time.monotonic()
        return begin,self.dispatch("step",payloads)

    def finish_step(self, ticket):
        begin,pending=ticket
        records=self.collect(pending)
        self.advance_wall += time.monotonic()-begin
        self.native_steps += sum(r["substeps"] for r in records.values())
        return records

    def advance(self, slots, actions):
        return self.finish_step(self.start_step(slots,actions))

    def close(self):
        old=[w.pid for w in self.workers]
        if old:
            self.drain()
            self.log_change("close",old,[])

    def drain(self, keep=0):
        for worker in self.workers[keep:]:
            try:
                worker.stdin.close()
            except BrokenPipeError:
                pass
        for worker in self.workers[keep:]:
            worker.wait()
        del self.workers[keep:]


@lru_cache(maxsize=12)
def binary_sensors(path, handle, panel_rgb):
    import mujoco as mj
    from learning.multimodal.sensors import RobotSensors
    model=mj.MjModel.from_binary_path(str(path))
    sensors=RobotSensors(model,handle,panel_rgb)
    sensors.mm03_compiled_file=str(path)
    return sensors


@lru_cache(maxsize=12)
def environment(scene_name, side, goal):
    from scripts.multimodal.mm02_physics import init_resources, scenes
    from scripts.multimodal.collect_feasibility import teacher_config
    from scripts.multimodal.mm03_plant import verified_file
    from learning.multimodal.sensors import RobotSensors
    socket=os.environ.get("MM03_INFERENCE_SOCKET")
    if socket:
        scene=scenes()[scene_name]
        cfg=teacher_config(side,goal,scene)
        path=verified_file(Path(socket).parent.parent,scene,side,goal,cfg)
        if path:
            color=tuple(scene["panel_rgb"]) if scene.get("panel_rgb") is not None else None
            sensors=binary_sensors(path,cfg["handle_site"],color)
            return sensors.model,cfg,sensors
    scene, cfg, model, _, _, _ = init_resources(dict(scene=scene_name, side=side, goal=goal))
    return model, cfg, RobotSensors(model, cfg["handle_site"], scene.get("panel_rgb"))


class StudentBranch:
    def __init__(self, path):
        from scripts.multimodal.correction_teacher import restore_physics
        from learning.multimodal.judge import DoorTaskJudge
        with open(path, "rb") as f:
            anchor = pickle.load(f)
        job = anchor["parent"]
        self.model, cfg, self.sensors = environment(job["scene"], job["side"], job["goal"])
        self.data = restore_physics(self.model, anchor["physics"])
        self.judge = DoorTaskJudge(self.model, cfg, job["side"], job["goal"])
        self.judge.__dict__.update(deepcopy(anchor["judge"]))
        self.start_events = len(self.judge.events)
        self.exposure = float(anchor["image_t"])
        self.start_quat = self.data.qpos[3:7].copy()
        self.tick = anchor["tick"]
        self.key = anchor["key"]
        if self.judge.passed or self.judge.failure or abs(self.tick*.02-self.data.time) > 1e-7:
            raise ValueError(f"Invalid physical anchor {path}")
        self.start_p = self.sensors.proprio(self.data.qpos, self.data.qvel)
        self.previous = anchor["previous"]

    def advance(self, action):
        import mujoco as mj
        d, m, judge = self.data, self.sensors.mapping, self.judge
        if judge.passed or judge.failure:
            raise ValueError("Native step across a terminated episode")
        if action.shape != (23,) or not np.isfinite(action).all() or np.any(abs(action) > 1.000001):
            raise ValueError("Invalid executed normalized 23-channel command")
        servo = (m.offset + m.scale * np.clip(action, -1., 1.))*m.finger_factor
        peak = np.zeros(2)
        bilateral = 0
        for sub in range(1, 11):
            q, v = d.qpos.copy(), d.qvel.copy()
            d.ctrl[m.actuator_ids] = servo + d.qfrc_bias[m.dof]*m.bias_gain
            mj.mj_step(self.model, d)
            c = judge.observe(d, q, v, return_wheel_slip=False)
            peak = np.maximum(peak, c.finger_normal)
            bilateral += int((c.finger_normal > .01).all())
            if judge.passed or judge.failure:
                break
        self.tick += 1
        result = dict(substeps=sub, dt=sub*.002, done=bool(judge.passed or judge.failure),
                      time=float(d.time), image_t=self.exposure, image=None,
                      failure=judge.failure["reason"] if judge.failure else None,
                      events_advanced=len(judge.events)-self.start_events, success=judge.passed)
        result.update(p=self.sensors.proprio(d.qpos, d.qvel), quat=d.qpos[3:7].astype(np.float32),
                      o=self.sensors.object_state(d.qpos, d.qvel),
                      contact=np.r_[peak > .01, bilateral/sub].astype(np.float32))
        if sub == 10 and d.time-self.exposure >= .1-1e-9:
            result["image"] = self.sensors.image(d.qpos, d.qvel)
            self.exposure = result["image_t"] = float(d.time)
        return result


def serve():
    import mujoco
    if mujoco.__version__ != "3.3.0":
        raise RuntimeError(f"Native 3.3.0 required, found {mujoco.__version__}")
    src, dst = sys.stdin.buffer, sys.stdout.buffer
    lanes = {}
    while True:
        try:
            op, values = receive(src)
        except EOFError:
            break
        try:
            if op == "reset":
                lanes = {i: StudentBranch(path) for i, path in values.items()}
                value = {i: dict(q0=b.start_quat, p=b.start_p, previous=b.previous, key=b.key,
                                 time=float(b.data.time), image_t=b.exposure) for i, b in lanes.items()}
            elif op == "step":
                value = {i: lanes[i].advance(a) for i, a in values.items()}
            else:
                raise ValueError(f"Unknown native operation {op}")
            send(dst, (True, value))
        except Exception:
            send(dst, (False, traceback.format_exc()))
            break


if __name__ == "__main__":
    serve()
