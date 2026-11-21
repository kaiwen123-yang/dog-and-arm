"""Run the frozen native teacher and P6 event judge on a single mjlab/Warp world."""
import argparse
import json
from pathlib import Path

import mujoco_warp
import numpy as np
import torch

from learning.b0.research_env import ResearchPlant
from scripts.b0.collect_reference import Recorder
from p6_scene import settings
from p6_single_door import run


class TeacherPhysics:
    source = "pinned mjlab Simulation.step / MuJoCo Warp"

    def __init__(self):
        self.plant = None
        self.steps = 0

    def step(self, model, data):
        if self.plant is None:
            self.plant = ResearchPlant(model, 1, "cuda:0")
            initial_q = torch.tensor(data.qpos, device="cuda:0", dtype=torch.float32)[None]
            initial_v = torch.tensor(data.qvel, device="cuda:0", dtype=torch.float32)[None]
            self.plant.reset(initial_q, initial_v)
        # P6 has already evaluated its feedback and per-substep bias compensation.
        # The single simulator input is the exact 23-value ctrl vector it issued.
        self.plant.data.ctrl[0] = torch.as_tensor(data.ctrl, device="cuda:0", dtype=torch.float32)
        self.plant.sim.step()
        self.steps += 1
        # Read the integrated state and solver's contact results. CPU IK, kinematics
        # and event observation can read this snapshot without advancing any physics.
        mujoco_warp.get_data_into(data, model, self.plant.sim.wp_data, world_id=0)


def audit_windows(path):
    """Independently read the final 1500 step-starts of each P6 hold phase."""
    meta = json.loads((path/"metadata.json").read_text())
    phases = np.load(path/"substeps/phase.npy")
    q = np.load(path/"substeps/qpos.npy", mmap_mode="r")
    v = np.load(path/"substeps/qvel.npy", mmap_mode="r")
    wheels = np.load(path/"substeps/wheel_load_N.npy", mmap_mode="r")
    finger = np.load(path/"substeps/finger_load_N.npy", mmap_mode="r")
    unexpected = np.load(path/"substeps/unexpected_contact_N.npy", mmap_mode="r")
    result = {}
    for name in ("post_release_hold", "final"):
        if name not in meta["phases"]:
            continue
        steps = np.flatnonzero(phases == meta["phases"].index(name))[-1500:]
        w, x, y, z = q[steps, 3:7].T
        rotation_z = np.column_stack((2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)))
        omega_z = (rotation_z*v[steps, 3:6]).sum(1)
        result[name] = dict(first_substep=int(steps[0]), last_substep=int(steps[-1]),
                            continuous_physics_steps=int(len(steps)) if np.all(np.diff(steps)==1) else 0,
                            max_speed_m_s=float(np.linalg.norm(v[steps,:2], axis=1).max()),
                            max_yaw_rate_deg_s=float(np.rad2deg(np.abs(omega_z).max())),
                            min_wheel_load_N=float(wheels[steps].min()),
                            peak_target_finger_N=float(finger[steps].max()),
                            unexpected_contact_peak_N=float(unexpected[steps].max()),
                            max_goal_error_deg=float(np.abs(np.rad2deg(q[steps,-1])-meta["target_angle_deg"]).max()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("side", choices=("pull","push"))
    parser.add_argument("--output", type=Path, required=True, help="new full data directory")
    parser.add_argument("--evidence", type=Path, required=True, help="new lightweight result JSON")
    args = parser.parse_args()
    if args.evidence.exists():
        parser.error("evidence file already exists")
    args.output.mkdir(parents=True, exist_ok=False)
    args.evidence.parent.mkdir(exist_ok=True, parents=True)
    stage = "mobile" if args.side == "pull" else "push"
    cfg = settings(stage, 1)
    integrator = TeacherPhysics()
    recorder = None

    def observe(model, data, t, q, v, target, phase, contact):
        nonlocal recorder
        if recorder is None:
            recorder = Recorder(model, cfg, args.output, args.side)
        recorder.step(model, data, t, q, v, target, phase, contact)

    passed = run(cfg, args.output, False, False, False, step_observer=observe, integrator=integrator)
    summary = json.loads((args.output/"summary.json").read_text())
    if summary["physics_steps"] != integrator.steps:
        raise RuntimeError("Physics integrator and teacher disagree on the step count")
    min_margin = min(joint["min_margin_rad"] for joint in summary["arm_joint_limit_min"].values())
    limit_pass = min_margin >= 0.
    passed = passed and limit_pass
    failure = summary["failure"] if limit_pass else "arm_joint_limit"
    meta = recorder.finish(passed, failure, dict(
        task=args.side, wm_split="research_backend_teacher_validation", noise_seed=None,
        teacher="frozen P6 C01, 500 Hz feedback on mjlab world with solver readback",
        physics_source=integrator.source, target_angle_deg=cfg["target_angle_deg"],
        event_log="summary.json"))
    evidence = {k:summary[k] for k in (
        "stage", "case", "task_success", "failure", "last_phase", "events", "physics_steps", "dt_s",
        "mujoco", "source", "initial_qpos", "final_qpos", "final_deg", "target_deg", "sim_time_s",
        "max_tilt_deg", "max_grip_error_m", "max_door_force_N", "unexpected", "warnings", "phases",
        "arm_joint_limit_min")}
    evidence.update(teacher_pin=meta["teacher_pin"], mount=meta["mount"],
                    physical_pass=passed, min_arm_limit_margin_rad=min_margin, parking_windows=audit_windows(args.output),
                    raw_directory=str(args.output), solver_warning_scope="host MjData warning counters only; Warp does not export a native warning vector",
                    teacher_rate="base 500 Hz, arm every 5 substeps or new phase",
                    state_observation="one solved state per completed 2 ms step",
                    clipping="GPU ctrl stored in float32, saved physical targets in float64")
    # These are capacity settings, not measured CUDA warning counters.
    d = integrator.plant.sim.wp_data
    for field in ("njmax", "naconmax"):
        evidence[field] = int(getattr(d, field))
    args.evidence.write_text(json.dumps(evidence, indent=2, allow_nan=False)+"\n")
    print(f"saved {args.evidence}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
