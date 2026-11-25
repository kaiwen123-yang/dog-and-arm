"""Compare measured feedback and issued targets in common-parent and nominal teacher approaches."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.multimodal.actor import load_actor
from learning.multimodal.dataset import EpisodeDataset


@torch.inference_mode()
def diagnose(checkpoint, data, cases, output):
    torch.set_num_threads(1)
    actor, vocab, _ = load_actor(checkpoint, "cpu")
    physical = json.loads(cases.read_text())
    ids = [row["case_id"] for row in physical]
    store = EpisodeDataset(data, "train", vocab, "cpu", ids)
    result = {"checkpoint": str(checkpoint), "cases": [],
              "finite_difference": "All 10 measured history samples shifted together; images, executed-action history, text, other sensor channels and clock held fixed. This is actor input sensitivity in physical action units.",
              "teacher_comparison": "Same nominal scene, goal and elapsed physical time. Student and teacher subsequently occupy different physical states."}
    for row in physical:
        i = store.episode_ids.index(row["case_id"])
        directory, meta = store.episodes[i]
        teacher = data / f"tr_nominal_{meta['side']}_{int(meta['target_deg'])}_held"
        ref_meta = json.loads((teacher / "metadata.json").read_text())
        scales = np.array([channel["scale"] for channel in ref_meta["action_channels"]])
        q, qt, a, at = [np.load(path, mmap_mode="r") for path in
                        (directory / "proprio.npy", teacher / "proprio.npy", directory / "physical_target.npy", teacher / "physical_target.npy")]
        n = min(len(a), len(at))
        ticks = sorted({tick for tick in [0,10,50,150,250,450,n-1] if 0 <= tick < n})
        evidence = []
        for tick in ticks:
            batch = store.batch([i], [tick])
            response = {}
            for name, channel, sensor, epsilon in (("j2", 17, 17, 0.005), ("first_wheel", 12, 23+12, 0.015)):
                h = batch["proprio_history"]
                delta = torch.zeros_like(h)
                delta[:,:,sensor] = epsilon
                higher = actor({**batch, "proprio_history": h + delta})
                lower = actor({**batch, "proprio_history": h - delta})
                response[name] = float((higher-lower)[0,channel]) * scales[channel] / (2*epsilon)
            evidence.append({"tick": tick, "elapsed_s": float(batch["sensor"][0,2]),
                "student_j2_measured_rad": float(q[tick,17]), "student_j2_target_rad": float(a[tick,17]),
                "teacher_j2_measured_rad": float(qt[tick,17]), "teacher_j2_target_rad": float(at[tick,17]),
                "student_wheel_target_vector_norm_rad_s": float(np.linalg.norm(a[tick,12:16])),
                "teacher_wheel_target_vector_norm_rad_s": float(np.linalg.norm(at[tick,12:16])),
                "physical_target_per_measured_input_derivative": response})
        result["cases"].append({"student_episode": meta["episode_id"], "teacher_episode": ref_meta["episode_id"],
            "failure": row["first_failure"], "decision_calls": row["decision_calls"],
            "j2_linear_skip_physical_gain": float(actor.servo_slope[17]) * scales[17],
            "first_wheel_linear_skip_physical_gain": float(actor.servo_slope[12]) * scales[12],
            "sampled": evidence})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["checkpoint", "data", "cases", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    diagnose(a.checkpoint, a.data, a.cases, a.output)
