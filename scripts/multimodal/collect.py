"""Record causal wrist/whole-body trajectories in the native P6 single-door plant."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import tempfile
import time

import mujoco as mj
import numpy as np

from scripts.b0.collect_contact import HeldTeacher
from scripts.b0.collect_reference import DECIMATION
from scripts.multimodal.collect_feasibility import teacher_config
from learning.multimodal.sensors import CAMERA_STRIDE, DEPTH_RANGE_M, SIZE, RobotSensors
from p6_single_door import run


ROOT = Path(__file__).resolve().parents[2]
SCENES = ROOT / "config/multimodal/scenes.json"


def load_scenes():
    return json.loads(SCENES.read_text())


def instruction(side, goal):
    return f"{side} the door to {goal:g} degrees then release stow and exit"


class GraspPerturbation(HeldTeacher):
    """Temporary full-width commands during hold, followed by the nominal teacher."""
    def __init__(self, widths):
        super().__init__()
        self.widths = widths

    def select(self, model, step, candidate, arm, fraction):
        target = super().select(model, step, candidate, arm, fraction)
        if step % DECIMATION == 0 and arm.phase == "hold" and 1 <= self.hold_ticks <= len(self.widths):
            width = self.widths[self.hold_ticks-1]
            self.request[-1] = (width-self.mapping.offset[-1])/self.mapping.scale[-1]
            target[self.mapping.actuator_ids[-1]] = width
        return target


class EpisodeWriter:
    """Append actual states, selected actions and solved substeps. Publish only on save."""

    def __init__(self, model, cfg, scene, side, goal, episode_id, source, sensors=None):
        self.sensors = sensors or RobotSensors(model, cfg["handle_site"], scene.get("panel_rgb"))
        self.mapping = self.sensors.mapping
        self.arrays = defaultdict(list)
        self.phases = []
        self.last_image = None
        self.image_wall_s = 0.
        self.start = time.monotonic()
        self.dt = float(model.opt.timestep)
        self.meta = dict(schema="mm01_wrist_rgbd_50hz_v1", episode_id=episode_id,
                         scene_id=scene["id"], side=side, target_deg=goal, split=scene["split"],
                         task_text=instruction(side, goal), source=source,
                         perturbation=scene["perturbation"], panel_rgb=scene.get("panel_rgb"),
                         mount="rail_bridge_front60_v2", physics_dt_s=self.dt,
                         policy_dt_s=DECIMATION*self.dt, camera_stride=CAMERA_STRIDE,
                         wrist_camera="wrist_rgbd", image_size=[SIZE, SIZE],
                         camera_fovy_deg=float(model.camera("wrist_rgbd").fovy.item()),
                         camera_modality="aligned synthetic RGB and metric axial depth",
                         camera_time="synchronous exposure and availability at t; most recent delivered frame",
                         depth_range_m=list(DEPTH_RANGE_M), depth_missing_m=0.,
                         action_channels=self.mapping.describe(model),
                         proprio_order=["encoder_position_23", "encoder_velocity_23",
                                       "gravity_unit_xyz_in_body", "body_gyro_rad_s_xyz"],
                         action_map="12 leg rad, 4 wheel rad/s, 6 arm rad, full jaw width m",
                         contact_definition="peak normal load in N on each finger in this action interval",
                         object_state_order=["hinge_rad", "hinge_rad_s", "handle_x_in_tcp_m",
                                             "handle_y_in_tcp_m", "handle_z_in_tcp_m"],
                         privileged_targets=["qpos", "qvel", "object_state", "contact", "phase",
                                             "both_contact_fraction"],
                         previous_action_definition="previous executed normalized held action, zero at reset",
                         mujoco_version=mj.__version__)

    def boundary(self, t, qpos, qvel, image=None):
        a = self.arrays
        if len(a["t"]) != len(a["action_clipped"]):
            raise ValueError("Boundary needs one action per preceding state")
        p = self.sensors.proprio(qpos, qvel)
        a["t"].append(float(t))
        a["proprio"].append(p)
        a["qpos"].append(qpos.copy())
        a["qvel"].append(qvel.copy())
        a["object_state"].append(self.sensors.object_state(qpos, qvel))
        # A partial terminal interval never advances the synthetic camera early.
        if not a["image_t"] or t - a["image_t"][-1] >= self.meta["policy_dt_s"]*CAMERA_STRIDE-1e-9:
            start = time.monotonic()
            self.last_image = self.sensors.image(qpos, qvel) if image is None else image
            self.image_wall_s += time.monotonic() - start
            rgb, depth, valid = self.last_image
            a["rgb"].append(rgb.copy())
            a["depth"].append(depth.copy())
            a["depth_valid"].append(valid.copy())
            a["image_t"].append(float(t))
        a["image_index"].append(len(a["image_t"])-1)
        return p, self.last_image

    def action(self, raw, clipped, physical_target, phase, supervised=False):
        a = self.arrays
        if len(a["t"]) != len(a["action_clipped"])+1:
            raise ValueError("Action needs a current observation")
        if phase not in self.phases:
            self.phases.append(phase)
        a["phase"].append(self.phases.index(phase))
        a["action_raw"].append(np.asarray(raw, dtype=np.float32).copy())
        a["action_clipped"].append(np.asarray(clipped, dtype=np.float32).copy())
        a["physical_target"].append(np.asarray(physical_target, dtype=np.float32).copy())
        a["action_supervision_mask"].append(bool(supervised))
        a["contact"].append(np.zeros(2, dtype=np.float32))
        a["both_contact_fraction"].append(0)
        a["substeps"].append(0)
        a["applied_ctrl"].append(np.full((DECIMATION, 23), np.nan, dtype=np.float32))

    def substep(self, applied_ctrl, finger_load_N):
        a = self.arrays
        i = a["substeps"][-1]
        if applied_ctrl is not None:
            a["applied_ctrl"][-1][i] = applied_ctrl
        a["contact"][-1] = np.maximum(a["contact"][-1], finger_load_N).astype(np.float32)
        a["both_contact_fraction"][-1] += int(np.all(np.asarray(finger_load_N) > .01))
        a["substeps"][-1] += 1

    def save(self, out, success, failure, *, extra=None):
        a = {key: np.asarray(values) for key, values in self.arrays.items()}
        n = len(a["action_clipped"])
        if len(a["t"]) != n + 1 or n < 1 or not np.allclose(
                np.diff(a["t"]), self.dt*a["substeps"], rtol=0, atol=1e-8):
            raise ValueError("State/action/substep times disagree")
        a["valid_transition"] = a["substeps"] == DECIMATION
        a["action_supervision_mask"] &= a["valid_transition"] & bool(success)
        a["previous_action"] = np.concatenate((np.zeros((1, 23), np.float32), a["action_clipped"]))
        a["both_contact_fraction"] = (a["both_contact_fraction"] / a["substeps"]).astype(np.float32)
        a["terminated"] = np.arange(n) == n-1
        if not np.all(np.isfinite(a["action_clipped"])) or not np.allclose(
                a["action_clipped"], np.clip(a["action_raw"], -1, 1), atol=1e-6):
            raise ValueError("Action clipping does not reproduce the issued command")
        if not np.allclose(a["physical_target"], self.mapping.offset+
                           self.mapping.scale*a["action_clipped"], atol=1e-6):
            raise ValueError("Encoded physical target differs from the sent action")
        if not np.all(a["image_t"][a["image_index"]] <= a["t"] + 1e-10):
            raise ValueError("A future wrist image reached a decision")
        elapsed = time.monotonic() - self.start
        meta = {**self.meta, **(extra or {}), "success": bool(success), "failure": failure,
                "phases": self.phases, "physics_steps": int(a["substeps"].sum()),
                "transitions": n, "valid_transitions": int(a["valid_transition"].sum()),
                "bc_labels": int(a["action_supervision_mask"].sum()), "frames": len(a["rgb"]),
                "depth_valid_fraction": float(a["depth_valid"].mean()),
                "both_contact_intervals": int(np.count_nonzero(a["both_contact_fraction"])),
                "final_hinge_deg": float(np.rad2deg(a["object_state"][-1, 0])),
                "episode_wall_s": elapsed, "image_wall_s": self.image_wall_s, "pid": os.getpid()}
        out = Path(out)
        if out.exists():
            raise FileExistsError(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
        for key, values in a.items():
            np.save(work / f"{key}.npy", values, allow_pickle=False)
        (work / "metadata.json").write_text(json.dumps(meta, indent=2, allow_nan=False)+"\n")
        work.rename(out)
        return meta


def collect_case(dataset, diagnostics, scene, side, goal, intervention=None):
    intervention = intervention or {}
    name = intervention.get("name", "held")
    eid = f"{scene['id']}_{side}_{goal}_{name}"
    dest = Path(dataset) / eid
    evidence = Path(diagnostics) / eid
    if dest.exists() or evidence.exists():
        raise FileExistsError(f"Existing episode or physics evidence for {eid}")
    evidence.mkdir(parents=True)
    cfg = teacher_config(side, goal, scene)
    if "widths_m" in intervention:
        teacher = GraspPerturbation(intervention["widths_m"])
    else:
        teacher = HeldTeacher(release_during_hold=intervention.get("release_during_hold", False),
                              hold_open_policy_ticks=intervention.get("hold_open_ticks", 0))
    recorder = last_data = None
    k = 0
    affected = []

    def observe(model, data, t, q, v, target, phase, contacts):
        nonlocal recorder, last_data, k
        if recorder is None:
            source = "P6_held_20ms" if not intervention else f"P6_held_20ms_{name}"
            recorder = EpisodeWriter(model, cfg, scene, side, goal, eid, source)
        if k % DECIMATION == 0:
            recorder.boundary(t, q, v)
            raw = teacher.request
            overridden = phase == "hold" and (
                teacher.release_during_hold or teacher.hold_ticks <= max(
                    teacher.hold_open_policy_ticks, len(intervention.get("widths_m", []))))
            if overridden:
                affected.append(k//DECIMATION)
            recorder.action(raw, np.clip(raw, -1., 1.), target[recorder.mapping.actuator_ids],
                            phase, supervised=not overridden)
        recorder.substep(data.ctrl[recorder.mapping.actuator_ids], contacts.finger_normal)
        last_data = data
        k += 1

    try:
        success = run(cfg, evidence, False, False, False, held_teacher=teacher, step_observer=observe)
        summary = json.loads((evidence / "summary.json").read_text())
        recorder.boundary(last_data.time, last_data.qpos, last_data.qvel)
        return recorder.save(dest, success, summary["failure"], extra={
            "teacher": "P6 feedback, reference tracking and IK; sampled via collect_contact.HeldTeacher",
            "image_source": "integrated native episode, rendered from its sampled causal state",
            "overridden_action_indices": affected, "last_phase": summary["last_phase"],
            "teacher_event_times": summary["events"], "unexpected": summary["unexpected"],
            "physics_evidence": str(evidence), "initial_qpos": summary["initial_qpos"],
        })
    finally:
        if recorder is not None:
            recorder.sensors.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--side", choices=["pull", "push"], required=True)
    parser.add_argument("--goal", type=int, choices=[15, 25], required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--diagnostics", type=Path, required=True)
    args = parser.parse_args()
    scene = next(s for s in load_scenes()["scenes"] if s["id"] == args.scene)
    result = collect_case(args.dataset, args.diagnostics, scene, args.side, args.goal)
    print(json.dumps({key: result[key] for key in ("episode_id", "success", "transitions",
                     "frames", "physics_steps", "image_wall_s", "episode_wall_s")}), flush=True)


if __name__ == "__main__":
    main()
