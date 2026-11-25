"""Native MM-02 rollouts and independently restored teacher corrections."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import pickle
import time

import mujoco as mj
import numpy as np

from learning.b0.physics import build
from learning.multimodal.judge import DoorTaskJudge, PHASES
from scripts.b0.eval_contact_segments import continuous_initial
from scripts.multimodal.collect import EpisodeWriter, instruction, load_scenes
from scripts.multimodal.collect_feasibility import teacher_config
from scripts.multimodal.correction_teacher import P6CorrectionTeacher, capture_physics, restore_physics
from scripts.multimodal.mm02_inference import PolicyPipe
from scripts.multimodal.render_episode import render_episode

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "results/planning/multimodal_mm02_20261125/registration.json"
JUDGE_DYNAMIC = ("i", "steps", "phase_start", "ready", "unloaded", "lost", "sliding",
                 "saturated", "events", "failure", "last", "seen_contact", "two_finger",
                 "wrong_contact", "peak_force", "max_angle", "closest_station", "closest_handle")
TORCH = ROOT / ".conda/envs/arm-and-dog/bin/python"


def scenes():
    registered = json.loads(REG.read_text())
    return {s["id"]: s for s in load_scenes()["scenes"] + registered["splits"]["new_blind_scenes"]}


def emit(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n")
    tmp.replace(path)


def digest(value):
    return hashlib.sha256(value).hexdigest()


class CorrectionWriter(EpisodeWriter):
    def __init__(self, model, cfg, scene, job, sensors=None):
        super().__init__(model, cfg, scene, job["side"], job["goal"], job["id"], job["mode"], sensors)
        self.meta.update(schema="mm02_causal_corrections_v1", source_policy=job["branch"],
                         round=job["round"], partition=job["partition"], checkpoint=job["checkpoint"],
                         execution_source_values={"0": "student", "1": "teacher"},
                         label_units="normalized 23-channel command [-1,1]; expert_physical_target in native units",
                         phase_owner="P6 correction controller", judge_phases=PHASES)
        self.start_previous = np.zeros(23, np.float32)

    def previous_at_start(self):
        return self.start_previous

    def supervision_mask(self, a, success):
        return a["expert_label_valid"] & a["valid_transition"]

    def record(self, raw, label, teacher_runs, judge, teacher):
        a = self.arrays
        executed = label.raw if teacher_runs else raw
        if not np.isfinite(executed).all() or not np.isfinite(raw).all():
            raise ValueError("Nonfinite actual action or student query")
        clipped = np.clip(executed, -1., 1.)
        target = self.mapping.offset + self.mapping.scale * clipped
        self.action(executed, clipped, target, label.phase, label.valid)
        for key, value in (("student_action_raw",raw), ("expert_action_raw",label.raw),
                           ("expert_action_target",label.target), ("expert_physical_target",label.physical),
                           ("executed_action_raw",executed), ("executed_action_clipped",clipped)):
            a[key].append(np.asarray(value, dtype=np.float32).copy())
        a["expert_label_valid"].append(bool(label.valid))
        in_range = np.isfinite(label.raw) & (abs(label.raw) <= 1.+1e-8)
        a["expert_channel_in_range"].append(in_range)
        a["expert_label_reason"].append(label.reason)
        a["execution_source"].append(int(teacher_runs))
        a["intervention"].append(bool(teacher_runs))
        a["judge_phase"].append(judge.i)
        a["teacher_phase_elapsed_s"].append(teacher.step*.002-teacher.phase_start)
        a["teacher_ik_residual"].append((teacher.arm.ik_position_error, teacher.arm.ik_rotation_error))
        return clipped, target * self.mapping.finger_factor


class Reservoir:
    """Uniform samples within each observed judge phase, without buffering every MjData."""
    def __init__(self, count, seed):
        self.count = count
        self.rng = np.random.default_rng(seed)
        self.seen = Counter()
        self.selected = defaultdict(dict)

    def offer(self, job, d, teacher, judge, recorder, previous, tick, image):
        phase = judge.phase
        self.seen[phase] += 1
        n = self.seen[phase]
        slot = n-1 if n <= self.count else int(self.rng.integers(n))
        if slot >= self.count:
            return
        a = recorder.arrays
        # The prefix excludes the anchor observation. Early histories repeat physical frame zero.
        indices = np.maximum(np.arange(tick-9, tick), 0)
        preceding = np.stack([a["action_clipped"][i-1] if i else recorder.start_previous for i in indices])
        prefix = (np.stack([a["proprio"][i] for i in indices]), preceding)
        contact = np.r_[(a["contact"][-1] > .01), a["both_contact_fraction"][-1]/a["substeps"][-1]]
        state = capture_physics(teacher.model, d)
        # Include task, inputs and evolving control state when deduplicating identical branches.
        h = hashlib.sha256()
        h.update(f'{job["scene"]}/{job["side"]}/{job["goal"]}/{tick}'.encode())
        for x in (state["integration"], *prefix, previous, teacher.q_arm, teacher.drive.leg_rest):
            h.update(np.ascontiguousarray(x).tobytes())
        h.update(teacher.phase.encode())
        self.selected[phase][slot] = dict(
            tick=tick, phase=phase, key=h.hexdigest(), physics=state, teacher=teacher.snapshot(),
            judge=deepcopy({k:getattr(judge,k) for k in JUDGE_DYNAMIC}), prefix=prefix,
            previous=previous.copy(), previous_contact=contact.astype(np.float32),
            image_t=a["image_t"][-1], image=tuple(x.copy() for x in image))

    def save(self, folder, job, episode):
        if not self.count:
            return []
        folder.mkdir(parents=True, exist_ok=True)
        candidates = []
        for items in self.selected.values():
            for snapshot in items.values():
                snapshot.update(parent=job, parent_path=str(episode))
                path = folder/f'{snapshot["tick"]:06d}.pkl'
                with path.open("wb") as f:
                    pickle.dump(snapshot, f, protocol=5)
                candidates.append({k:snapshot[k] for k in ("tick","phase","key")} |
                                  dict(path=str(path), scene=job["scene"], side=job["side"],
                                       goal=job["goal"], parent=job["id"], mode=job["mode"],
                                       branch=job["branch"]))
        return candidates


def init_resources(job):
    scene = scenes()[job["scene"]]
    cfg = teacher_config(job["side"], job["goal"], scene)
    model = build(cfg)
    if mj.__version__ != "3.3.0" or abs(model.opt.timestep-.002)>1e-12:
        raise ValueError("Registered native plant and time step required")
    d, _, _ = continuous_initial(model,cfg,None)
    teacher = P6CorrectionTeacher(model,d,cfg)
    judge = DoorTaskJudge(model,cfg,job["side"],job["goal"])
    return scene,cfg,model,d,teacher,judge


def execute(run, job, *, anchor=None, client=None, sensors=None, resources=None):
    root = Path(run)
    root_dir = root / job["partition"]
    case = root_dir / job["id"]
    case.mkdir(parents=True, exist_ok=True)
    if (case/"result.json").exists():
        return json.loads((case/"result.json").read_text())
    scene,cfg,model,d,teacher,judge = resources or init_resources(job)
    initial = digest(np.r_[d.qpos,d.qvel].astype("<f8").tobytes())
    recorder = CorrectionWriter(model,cfg,scene,job,sensors=sensors)
    previous = recorder.start_previous.copy()
    prefix = None
    tick = 0
    if anchor is not None:
        d = restore_physics(model,anchor["physics"])
        teacher.restore(anchor["teacher"])
        judge.__dict__.update(deepcopy(anchor["judge"]))
        previous = anchor["previous"].copy()
        recorder.start_previous = previous.astype(np.float32)
        tick = anchor["tick"]
        prefix = anchor["prefix"]
        recorder.meta.update(parent_episode=anchor["parent"]["id"], parent_path=anchor["parent_path"],
                             anchor_tick=tick, anchor_key=anchor["key"], anchor_phase=anchor["phase"])
        a = recorder.arrays
        a["history_prefix_proprio"] = prefix[0]
        a["history_prefix_previous_action"] = prefix[1]
        a["history_prefix_contact"] = anchor["previous_contact"]
        recorder.last_image = anchor["image"]
        for k,x in zip(("rgb","depth","depth_valid"),recorder.last_image):
            a[k].append(x)
        a["image_t"].append(anchor["image_t"])
    start_tick, start_physics = tick, judge.steps
    begin = time.monotonic()
    make_client = client is None
    client = client or PolicyPipe(TORCH,job["checkpoint"])
    client.reset(instruction(job["side"],job["goal"]),tick,prefix)
    rng = np.random.default_rng(job["seed"])
    reservoir = Reservoir(job.get("snapshot_count",0), job["seed"]+123457)
    student_visited = False
    selection = []
    min_margin = np.full(6, np.inf)
    squared_joint_error = np.zeros(6)
    joint_rows = 0
    m = recorder.mapping
    try:
        while not judge.passed and not judge.failure and (anchor is None or tick-start_tick < 32):
            t = float(d.time)
            proprio,image = recorder.boundary(t,d.qpos,d.qvel)
            raw = client.step(proprio,previous,image,recorder.arrays["image_t"][-1],t)
            if reservoir.count and student_visited:
                reservoir.offer(job,d,teacher,judge,recorder,previous,tick,image)
            if anchor is not None:
                teacher_runs = True
            elif job["mode"] == "mixed":
                if tick%10 == 0:
                    selection.append(bool(rng.random()<job["probability"]))
                teacher_runs = selection[-1]
            else:
                teacher_runs = False
            label = teacher.before(d)
            previous, servo = recorder.record(raw,label,teacher_runs,judge,teacher)
            for sub in range(10):
                if sub:
                    teacher.before(d)
                q,v = d.qpos.copy(),d.qvel.copy()
                d.ctrl[m.actuator_ids] = servo + d.qfrc_bias[m.dof]*m.bias_gain
                mj.mj_step(model,d)
                c = judge.observe(d,q,v)
                teacher.after(d,c)
                recorder.substep(d.ctrl[m.actuator_ids],c.finger_normal)
                pos = d.qpos[judge.arm_q]
                min_margin = np.minimum(min_margin,np.minimum(pos-judge.ranges[:,0],judge.ranges[:,1]-pos))
                squared_joint_error += (pos-servo[16:22])**2
                joint_rows += 1
                if judge.passed or judge.failure:
                    break
            student_visited |= not teacher_runs
            tick += 1
        recorder.boundary(float(d.time),d.qpos,d.qvel)
        path = case/"episode"
        failure = judge.failure["reason"] if judge.failure else None
        meta = recorder.save(path,judge.passed,failure,extra=dict(
            first_failure=judge.failure, judge_events=judge.events, teacher_events=teacher.events,
            teacher_first_failure=teacher.failure, block_executors=selection, initial_state_sha256=initial,
            source_checkpoint_sha256=job["sha"], parent_clock_start_s=start_tick*.02,
            horizon_complete=bool(anchor is not None and tick-start_tick==32 and judge.steps-start_physics==320),
            expert_label_reason_counts=dict(Counter(recorder.arrays["expert_label_reason"]))))
        candidates = reservoir.save(case/"snapshots",job,path)
        result = {**job,**judge.result(),"wall_s":time.monotonic()-begin,"raw_episode":str(path),
                  "initial_state_sha256":initial,"physics_steps":judge.steps-start_physics,
                  "decision_calls":tick-start_tick,"bc_labels":meta["bc_labels"],"camera_frames":meta["frames"],
                  "initial_deg":float(np.rad2deg(recorder.arrays["object_state"][0][0])),
                  "final_deg":float(np.rad2deg(d.qpos[judge.hinge.qposadr.item()])),
                  "joint_min_margin_rad":min_margin.tolist(),
                  "joint_servo_rmse_over_range":(np.sqrt(squared_joint_error/joint_rows)/
                                                 np.diff(judge.ranges).ravel()).tolist(),
                  "teacher_steps":int(np.sum(recorder.arrays["execution_source"])),
                  "teacher_blocks":sum(selection),"selected_blocks":len(selection),
                  "expert_label_reason_counts":meta["expert_label_reason_counts"],
                  "ordered_event_count":len(judge.events),"candidate_anchors":len(candidates),
                  "parent_tick":start_tick,"horizon_complete":meta["horizon_complete"],
                  "recorded_utc":datetime.now(timezone.utc).isoformat()}
        if anchor is not None:
            result.update(parent_episode=anchor["parent"]["id"],anchor_key=anchor["key"])
        if candidates:
            emit(case/"candidates.json",candidates)
        emit(case/"result.json",result)
        if anchor is None and job["mode"]=="pure" and judge.passed:
            deliver_first(root,case,path,result)
        return result
    finally:
        if make_client:
            client.close()
        if sensors is None:
            recorder.sensors.close()


def deliver_first(root,case,path,result):
    folder = root/"videos"
    folder.mkdir(exist_ok=True)
    try:
        with (folder/"first_success.json").open("x") as f:
            json.dump(dict(result=str(case/"result.json"), episode=str(path),
                           checkpoint=result["checkpoint"], sha256=result["sha"]), f, indent=2)
    except FileExistsError:
        return
    render_episode(path, folder/"first_student_success_1080p.mp4")
