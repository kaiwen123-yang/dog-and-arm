"""Export the trained forward pass and verify it against the optimizer checkpoint on real cameras."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.multimodal.actor import OnlinePolicy, load_actor
from learning.multimodal.dataset import EpisodeDataset


@torch.inference_mode()
def instruction_pairs(actor, dataset):
    outcome = []
    cases = {}
    for i, (_, meta) in enumerate(dataset.episodes):
        cases.setdefault((meta["scene_id"], meta["side"]), []).append((float(meta["target_deg"]), i))
    for (scene, side), goals in cases.items():
        if len(goals) != 2:
            continue
        (low, i), (high, j) = sorted(goals)
        count = min(dataset.lengths[i], dataset.lengths[j])-1
        left = dataset.states["action"][dataset.starts[i]:dataset.starts[i]+count]
        right = dataset.states["action"][dataset.starts[j]:dataset.starts[j]+count]
        changed = (left - right).abs().amax(-1) > 1e-5
        ticks = [0]
        if changed.any():
            ticks.append(int(torch.nonzero(changed)[0,0]))
        rows = []
        for tick in ticks:
            a = dataset.batch([i], [tick])
            b = dataset.batch([j], [tick])
            original = actor(a)
            swapped = actor({**a, "tokens": b["tokens"]})
            delta = (original - swapped).abs()[0]
            rows.append({"policy_tick": tick, "time_s": float(a["sensor"][0,2]),
                         "same_rgb": torch.equal(a["rgb"], b["rgb"]), "same_metric_depth": torch.equal(a["depth"], b["depth"]),
                         "max_abs_proprio_history_difference": float((a["proprio_history"]-b["proprio_history"]).abs().max()),
                         "teacher_action_max_abs_difference": float((left[tick]-right[tick]).abs().max()),
                         "frozen_observation_language_change_mean_abs": float(delta.mean()),
                         "frozen_observation_language_change_max_abs": float(delta.max()),
                         "largest_response_channel": int(delta.argmax())})
        outcome.append({"scene": scene, "side": side, "goals_deg": [low, high],
                        "rows": rows, "selection": "reset and first teacher action difference > 1e-5 at the same elapsed time"})
    return outcome


@torch.inference_mode()
def export(checkpoint, data, destination, report):
    torch.set_num_threads(1)
    original, vocab, full = load_actor(checkpoint, "cpu")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    inference = {"schema": full["schema"], "vocabulary": vocab.tokens, "actor": original.state_dict(),
                 "method": "M1Piper-Multimodal-v1", "operation": "inference", "source_sha256": digest,
                 "update": full["update"], "configuration": full["configuration"]}
    temporary = destination.with_suffix(".pt.tmp")
    torch.save(inference, temporary)
    restored, _, _ = load_actor(temporary, "cpu")
    validation = EpisodeDataset(data, "validation", vocab, "cpu", full["membership"]["validation"])
    tested = []
    max_batch = max_stream = 0.0
    for i, (_, meta) in enumerate(validation.episodes):
        n = validation.lengths[i]
        ticks = np.unique(np.linspace(0, n-1, num=min(n, 96), dtype=int))
        batch = validation.batch(np.full(len(ticks), i), ticks)
        reference = original(batch)
        difference = (reference - restored(batch)).abs().max().item()
        max_batch = max(max_batch, difference)
        if difference != 0:
            raise RuntimeError(f"Deployment batch outputs changed on {meta['episode_id']}: {difference}")
        policies = [OnlinePolicy(module, vocab, "cpu") for module in (original, restored)]
        for policy in policies:
            policy.reset(meta["task_text"])
        steps = min(18, n-1)
        start = validation.batch(np.full(steps, i), np.arange(steps))
        for j in range(steps):
            inputs = [start[k][j].numpy() for k in ("rgb", "depth", "depth_valid")]
            inputs.extend(start[k][j,-1].numpy() for k in ("proprio_history", "previous_history"))
            inputs.extend([float(start["sensor"][j,0]), bool(start["sensor"][j,1])])
            a, b = (policy.step(*inputs) for policy in policies)
            stream_error = float(np.max(np.abs(a - b)))
            max_stream = max(max_stream, stream_error)
            if stream_error != 0:
                raise RuntimeError(f"Deployment stream changed on {meta['episode_id']} step {j}: {stream_error}")
        tested.append({"episode_id": meta["episode_id"], "spread_states": len(ticks), "consecutive_stream_states": steps})
    temporary.replace(destination)
    result = {"source_checkpoint": str(checkpoint), "source_sha256": digest, "deployment_filename": destination.name,
              "deployment_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "size_bytes": destination.stat().st_size,
              "device": "cpu", "validation_episodes": tested, "max_abs_batch_difference": max_batch,
              "max_abs_online_control_difference": max_stream, "validation_instruction_pairs": instruction_pairs(restored, validation)}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("checkpoint", "data", "output", "report"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    export(args.checkpoint, args.data, args.output, args.report)
