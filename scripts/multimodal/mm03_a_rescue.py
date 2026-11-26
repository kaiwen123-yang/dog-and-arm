"""44 registered channel interventions with the unmodified native scorer/servo."""
from collections import defaultdict
import json
from pathlib import Path
import time

import mujoco as mj
import numpy as np

from scripts.multimodal.collect import EpisodeWriter, instruction
from scripts.multimodal.mm02_physics import init_resources


MASKS = {"student": (), "teacher_legs12": range(12), "teacher_wheels4": range(12, 16),
         "teacher_arm_grip7": range(16, 23), "teacher_legs_wheels16": range(16),
         "teacher_all23": range(23)}


def rescue_jobs(repo):
    manifest = json.loads((repo/"results/multimodal/mm02_20261125/manifest.json").read_text())
    jobs = []
    for side in ("pull", "push"):
        for goal in (15, 25):
            for branch in ("supervised_aggregate", "model_trajectory", "teacher"):
                variants = ("teacher_all23",) if branch == "teacher" else tuple(MASKS)[:-1]
                for variant in variants:
                    deploy = {} if branch == "teacher" else manifest["terminal_packages"][branch + "/deployment"]
                    jobs.append(dict(id=f"{branch}_{side}{goal}_{variant}", scene="tr_nominal", side=side,
                                     goal=goal, branch=branch, variant=variant, checkpoint=deploy.get("source"),
                                     checkpoint_sha256=deploy.get("sha256")))
    return jobs


class PhysicsLog:
    """All series are aligned on solved 2ms intervals; start and endpoint are explicit."""
    def __init__(self, model, mapping, meter):
        self.rows = defaultdict(list)
        self.collision = []
        self.meter = meter
        self.mapping = mapping
        joints = model.actuator_trnid[mapping.actuator_ids, 0]
        self.limited = joints[model.jnt_limited[joints].astype(bool)]
        self.qindex = model.jnt_qposadr[self.limited]
        self.bounds = model.jnt_range[self.limited]
        self.limit_names = [model.joint(j).name for j in self.limited]
        self.rot = np.empty(9)
        self.wrench = np.empty(6)

    def step(self, model, d, q, v, c, judge, teacher, student, executed, target, bias, mask):
        a = self.rows
        m = self.mapping
        mj.mju_quat2Mat(self.rot, q[3:7])
        r = self.rot.reshape(3, 3)
        pos = d.qpos[self.qindex]
        for key, value in (
            ("t_start", d.time-judge.dt), ("wheel_normal_n", c.normal),
            ("four_supported", c.supported), ("incomplete_support_s", judge.unloaded*judge.dt),
            ("roll_pitch_rad", [np.arctan2(r[2, 1], r[2, 2]), np.arcsin(np.clip(-r[2, 0], -1, 1))]),
            ("base_height_m", q[2]), ("base_linear_world_m_s", v[:3]),
            ("base_vx_wz", [r[:, 0] @ v[:3], r[2] @ v[3:6]]),
            ("teacher_request_norm23", teacher), ("executed_clipped_norm23", executed),
            ("actual_physical_target23", target), ("servo_bias23", bias),
            ("actual_ctrl23", d.ctrl[m.actuator_ids]), ("executor_source_mask23", mask),
            ("joint_lower_margin_end", pos-self.bounds[:, 0]), ("joint_upper_margin_end", self.bounds[:, 1]-pos),
            ("actuator_force23", d.actuator_force[m.actuator_ids]),
            ("saturation_mask23", judge.saturated[m.actuator_ids] > 0),
        ):
            a[key].append(np.array(value, dtype=np.bool_ if key in ("four_supported", "executor_source_mask23",
                                                                    "saturation_mask23") else np.float32))
        if student is not None:
            a["student_request_norm23"].append(student.astype(np.float32))
        # Include positive self-contact normal forces even below the judge's threshold.
        for i, con in enumerate(d.contact):
            g1, g2 = map(int, con.geom)
            if con.efc_address < 0 or not (self.meter.robot[g1] and self.meter.robot[g2]):
                continue
            mj.mj_contactForce(model, d, i, self.wrench)
            if self.wrench[0] > 0:
                self.collision.append(dict(step=judge.steps, geom1=self.meter.names[g1], geom2=self.meter.names[g2],
                                           normal_n=float(self.wrench[0])))

    def save(self, folder):
        folder.mkdir()
        for k, v in self.rows.items():
            np.save(folder/(k + ".npy"), np.asarray(v), allow_pickle=False)
        (folder/"self_collision.json").write_text(json.dumps(self.collision))
        loads = np.asarray(self.rows["wheel_normal_n"])
        return dict(wheel_order=list(self.meter.wheel_labels), joint_margin_names=self.limit_names,
                    min_wheel_load_n=loads.min(axis=0).tolist(),
                    unsupported_samples=(~np.asarray(self.rows["four_supported"])).sum(axis=0).tolist(),
                    max_incomplete_support_s=float(np.max(self.rows["incomplete_support_s"])),
                    self_collision_points=len(self.collision), log="physics_2ms",
                    clock="root and contact at interval start, joint margin at solved end",
                    target_units="canonical physical target incl. full jaw; servo ctrl has half jaw plus bias")


def run_rescue(job, folder, *, client_factory=None):
    scene, cfg, model, d, teacher, judge = init_resources(job)
    mask = np.zeros(23, dtype=bool)
    mask[list(MASKS[job["variant"]])] = True
    source = "teacher" if mask.all() else "mixed" if mask.any() else "pure_student"
    rec = EpisodeWriter(model, cfg, scene, job["side"], job["goal"], job["id"], source)
    m = rec.mapping
    physics = PhysicsLog(model, m, judge.meter)
    previous = np.zeros(23, dtype=np.float32)
    client = None
    start = time.monotonic()
    try:
        if source != "teacher":
            if client_factory is None:
                from scripts.multimodal.mm03_inference import PolicyClient
                client = PolicyClient(job["checkpoint"], kind="mm02")
            else:
                client = client_factory(job["checkpoint"])
            client.reset(instruction(job["side"], job["goal"]))
        while not (judge.failure or judge.passed):
            now = float(d.time)
            p, image = rec.boundary(now, d.qpos, d.qvel)
            raw = None if client is None else client.step(p, previous, image, rec.arrays["image_t"][-1], now)
            label = teacher.before(d)
            combined = label.raw.copy() if raw is None else np.where(mask, label.raw, raw)
            if not np.all(np.isfinite(combined)):
                raise FloatingPointError("Nonfinite actuator request before clipping")
            previous = np.clip(combined, -1., 1.)
            physical = m.offset + m.scale*previous
            servo = physical*m.finger_factor
            rec.action(combined, previous, physical, label.phase)
            for sub in range(10):
                if sub:
                    teacher.before(d)
                q, v = d.qpos.copy(), d.qvel.copy()
                bias = d.qfrc_bias[m.dof]*m.bias_gain
                d.ctrl[m.actuator_ids] = servo + bias
                mj.mj_step(model, d)
                c = judge.observe(d, q, v)
                teacher.after(d, c)
                rec.substep(d.ctrl[m.actuator_ids], c.finger_normal)
                physics.step(model, d, q, v, c, judge, label.raw, raw, previous, physical, bias, mask)
                if judge.failure or judge.passed:
                    break
        rec.boundary(d.time, d.qpos, d.qvel)
        rec.save(folder/"episode", judge.passed, judge.failure and judge.failure["reason"])
        summary = physics.save(folder/"physics_2ms")
        return {**job, **judge.result(), **summary, "source": source, "executor_source_mask": mask.tolist(),
                "wall_s": time.monotonic()-start, "teacher_query_steps": teacher.step,
                "teacher_failure": teacher.failure, "decisions": len(rec.arrays["action_raw"])}
    finally:
        rec.sensors.close()
        if client is not None:
            client.close()
