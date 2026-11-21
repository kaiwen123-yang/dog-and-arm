"""Replay measured free-motion teacher actions in the pinned mjlab simulation."""
from argparse import ArgumentParser
import json
from pathlib import Path

import mujoco
import mujoco_warp
import numpy as np
import torch

from learning.b0.evaluate import ErrorMeasures
from learning.b0.physics import make_model
from learning.b0.reference import ROOT, load_episode, reference_entries
from learning.b0.research_env import ResearchPlant
from p6_contacts import ContactMeter


def run():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new comparison JSON file")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output to preserve the last comparison")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tasks = [e for e in reference_entries() if e["task"] in ("support", "moving_arm", "park")]
    episodes = [load_episode(e["path"]) for e in tasks]
    m = make_model()
    count = len(tasks)
    checks = dict(native_version="3.3.0", research_mujoco=mujoco.__version__, worlds=count,
                  status="starting", state_sample_hz=50, contact_sample_hz=5,
                  contact_convention="last solved substep per sampled 20ms boundary",
                  motion_source=[e["episode_id"] for e in tasks], cases={})
    tensor = lambda x: torch.as_tensor(np.stack(x), device="cuda:0", dtype=torch.float32)
    try:
        plant = ResearchPlant(m, count, "cuda:0")
        host = mujoco.MjData(m)
        meter = ContactMeter(m, "preview_floor")
        scorer = ErrorMeasures(m)
        initial_q = [d["qpos"][0] for d in episodes]
        initial_v = [d["qvel"][0] for d in episodes]
        plant.reset(tensor(initial_q), tensor(initial_v))
        q_world = [plant.data.qpos[:].cpu().numpy().copy()]
        v_world = [plant.data.qvel[:].cpu().numpy().copy()]
        loaded, wheel_reference_at = [], []
        invalid_ticks, unexpected_peak = np.zeros(count, dtype=int), np.zeros(count)
        steps = len(episodes[0]["action_clipped"])
        for k in range(steps):
            action = tensor([d["action_clipped"][k] for d in episodes])
            flag = plant.step(action)
            invalid_ticks += flag.cpu().numpy()
            q_world.append(plant.data.qpos[:].cpu().numpy().copy())
            v_world.append(plant.data.qvel[:].cpu().numpy().copy())
            if k % 10 == 9:
                loads = []
                for i in range(count):
                    mujoco_warp.get_data_into(host, m, plant.sim.wp_data, world_id=i)
                    contact = meter.measure(host)
                    unexpected_peak[i] = max(unexpected_peak[i], max(contact.unexpected.values(), default=0.))
                    loads.append(contact.normal)
                loaded.append(loads)
                wheel_reference_at.append((k+1)*10-1)
        for i,(e,d) in enumerate(zip(tasks,episodes)):
            ref_load = np.load(ROOT/e["path"]/"substeps/wheel_load_N.npy", mmap_mode="r")[wheel_reference_at]
            actual_load = np.asarray(loaded)[:,i]
            checks["cases"][e["task"]] = {
                "reference_id": e["reference_id"],
                "steps": steps,
                "physics_steps": steps*10,
                "invalid_policy_intervals": int(invalid_ticks[i]),
                "errors": scorer.compare(np.asarray(q_world)[:,i], np.asarray(v_world)[:,i],
                                         d["qpos"], d["qvel"], ref_tcp=d["tcp_world"]),
                "wheel_normal_rmse_N_FAR_FBL_RAR_RBL": np.sqrt(np.mean((actual_load-ref_load)**2, axis=0)).tolist(),
                "samples_with_wheel_load_mismatch_1N_threshold": int(np.any((actual_load>=1.) != (ref_load>=1.), axis=1).sum()),
                "unexpected_sampled_contact_peak_N": float(unexpected_peak[i])
            }
        checks["status"] = "completed"
    except Exception as exc:
        checks["status"] = "failed"
        checks["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        args.output.write_text(json.dumps(checks, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    run()
