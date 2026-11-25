"""Train a common multimodal BC parent and matched supervised / model-optimized continuations."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.multimodal.actor import MultimodalActor, OnlinePolicy, Vocabulary, load_actor
from learning.multimodal.dataset import EpisodeDataset, discover, training_vocabulary


GROUPS = {"legs": slice(0,12), "wheels": slice(12,16), "arm": slice(16,22), "jaw": slice(22,23)}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def atomic_save(path, value):
    temporary = path.with_suffix(".pt.tmp")
    torch.save(value, temporary)
    temporary.replace(path)


def synchronize(device):
    if torch.device(device).type == "cuda":
        torch.cuda.synchronize(device)


def peak(device):
    if torch.device(device).type != "cuda":
        return {"cuda_peak_allocated_MiB": 0.0, "cuda_peak_reserved_MiB": 0.0}
    return {"cuda_peak_allocated_MiB": torch.cuda.max_memory_allocated(device) / 2**20,
            "cuda_peak_reserved_MiB": torch.cuda.max_memory_reserved(device) / 2**20}


def bc_objective(actor, action, target):
    normalized = (action - target) / actor.residual_std
    errors = F.smooth_l1_loss(normalized, torch.zeros_like(normalized), reduction="none", beta=0.5)
    return torch.stack([errors[:, group].mean() for group in GROUPS.values()]).mean()


def run_updates(actor, optimizer, dataset, steps, seed, batch_size, extra_loss=None, *, start=0,
                sampler_state=None, batch_digest=None, on_interval=None, interval=200):
    rng = np.random.default_rng(seed)
    if sampler_state is not None:
        rng.bit_generator.state = sampler_state
    digest = bytes.fromhex(batch_digest) if batch_digest is not None else bytes(32)
    device = dataset.device
    synchronize(device)
    begun = time.perf_counter()
    records = []
    sums = {}
    since = 0
    actor.train()
    for step in range(start+1, steps+1):
        indices = dataset.sample_indices(rng, batch_size)
        digest = hashlib.sha256(digest + indices.astype("<i8", copy=False).tobytes()).digest()
        batch = dataset.batch_rows(indices)
        action = actor(batch)
        bc_loss = bc_objective(actor, action, batch["action"])
        loss = bc_loss
        meter = {"bc_loss": bc_loss.detach()}
        if extra_loss is not None:
            extra = extra_loss(actor, batch)
            if isinstance(extra, tuple):
                extra, extra_stats = extra
                for key, value in extra_stats.items():
                    meter[key] = torch.as_tensor(value, device=device).detach()
            loss = loss + extra
            meter["world_model_term"] = extra.detach()
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(actor.parameters(), 2.0, error_if_nonfinite=True)
        optimizer.step()
        meter["gradient_norm"] = norm.detach()
        since += 1
        for key, value in meter.items():
            sums[key] = sums.get(key, 0) + value
        if step % interval == 0 or step == steps:
            synchronize(device)
            duration = time.perf_counter() - begun
            rec = {"update": step, "interval_updates": since, "elapsed_s": duration,
                   "updates_per_s": (step-start)/duration, "samples_per_s": (step-start)*batch_size/duration,
                   **{key: float((value / since).cpu()) for key, value in sums.items()}, **peak(device)}
            print(json.dumps(rec, allow_nan=False), flush=True)
            records.append(rec)
            if on_interval is not None:
                on_interval(step, rng.bit_generator.state, digest.hex(), records)
            sums = {}
            since = 0
    return records, rng.bit_generator.state, digest.hex()


@torch.inference_mode()
def evaluate_actor(actor, dataset, vocab, n_samples=4096):
    actor.eval()
    evaluation = {"episodes": dataset.episode_ids, "eligible_expert_transitions": len(dataset.expert_rows),
                  "valid_transitions": len(dataset.valid_rows)}
    rng = np.random.default_rng(2069)
    def selected(rows):
        return np.sort(rng.choice(rows, size=min(len(rows), n_samples), replace=False))
    labeled_rows = selected(dataset.expert_rows)
    by_group = {name: [] for name in GROUPS}
    normalized = []
    for part in np.array_split(labeled_rows, max(1, (len(labeled_rows)+127)//128)):
        if not len(part):
            continue
        batch = dataset.batch_rows(part)
        diff = actor(batch) - batch["action"]
        normalized.append((diff / actor.action_std).square().cpu().numpy())
        for name, section in GROUPS.items():
            by_group[name].append(diff[:, section].square().cpu().numpy())
    evaluation["bc_scored_samples"] = len(labeled_rows)
    evaluation["action_rmse_by_group"] = {key: float(np.sqrt(np.concatenate(values).mean())) if values else None
                                           for key, values in by_group.items()}
    evaluation["action_train_std_normalized_rmse"] = float(np.sqrt(np.concatenate(normalized).mean())) if normalized else None
    by_side = {}
    for _, m in dataset.episodes:
        by_side.setdefault(m["side"], {})[m["target_deg"]] = m["task_text"]
    other, available = [], []
    for _, m in dataset.episodes:
        alternatives = [text for angle, text in sorted(by_side[m["side"]].items()) if angle != m["target_deg"]]
        other.append(vocab.encode(alternatives[0] if alternatives else m["task_text"]))
        available.append(bool(alternatives))
    other = torch.tensor(other, device=dataset.device)
    available = torch.tensor(available, device=dataset.device)
    response = {k: [] for k in ("zero_rgb", "missing_depth", "permuted_rgbd", "same_side_other_goal", "repeated_latest_proprio")}
    probe_rows = selected(dataset.valid_rows)
    for part in np.array_split(probe_rows, max(1, (len(probe_rows)+127)//128)):
        if not len(part):
            continue
        batch = dataset.batch_rows(part)
        pred = actor(batch)
        def record(key, inputs, valid=None):
            delta = (actor(inputs) - pred).abs()
            if valid is not None:
                delta = delta[valid]
            if len(delta):
                response[key].append(delta.cpu().numpy())
        record("zero_rgb", {**batch, "rgb": torch.zeros_like(batch["rgb"])})
        record("missing_depth", {**batch, "depth_valid": torch.zeros_like(batch["depth_valid"])})
        perm = torch.as_tensor(rng.permutation(len(part)), device=dataset.device)
        record("permuted_rgbd", {**batch, **{key: batch[key][perm] for key in ("rgb", "depth", "depth_valid")}})
        ids = dataset.states["episode"][torch.as_tensor(part, device=dataset.device)]
        record("same_side_other_goal", {**batch, "tokens": other[ids]}, available[ids])
        record("repeated_latest_proprio", {**batch, "proprio_history": batch["proprio_history"][:, -1:].expand_as(batch["proprio_history"])})
    evaluation["frozen_observation_interventions"] = {}
    for key, rows in response.items():
        values = np.concatenate(rows) if rows else np.empty((0,23))
        evaluation["frozen_observation_interventions"][key] = {"samples": len(values),
            "mean_abs_action_change": float(values.mean()) if len(values) else None,
            "by_group": {name: float(values[:, section].mean()) for name, section in GROUPS.items()} if len(values) else {}}
    directory, meta = dataset.episodes[0]
    online = OnlinePolicy(actor, vocab, dataset.device)
    online.reset(meta["task_text"])
    n = min(16, dataset.lengths[0])
    s = dataset.batch(np.zeros(n, dtype=np.int64), np.arange(n))
    expected = actor(s).cpu().numpy()
    output = []
    for j in range(n):
        vals = [s[k][j].cpu().numpy() for k in ("rgb", "depth", "depth_valid")]
        output.append(online.step(*vals, s["proprio_history"][j,-1].cpu().numpy(), s["previous_history"][j,-1].cpu().numpy(),
                                  float(s["sensor"][j,0]), bool(s["sensor"][j,1])))
    evaluation["online_window_parity"] = {"episode": meta["episode_id"], "steps": n,
                                          "max_abs_action_error": float(np.max(np.abs(expected - output)))}
    return evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["benchmark", "initial", "paired"], required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=192)
    parser.add_argument("--seed", type=int, default=701)
    parser.add_argument("--lr", type=float, default=0.0005)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--interval", type=int, default=250)
    parser.add_argument("--save-every", type=int, default=2000)
    parser.add_argument("--parent", type=Path)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--world-model", type=Path)
    parser.add_argument("--membership", type=Path, help="JSON object with train and validation episode ID lists")
    args = parser.parse_args()
    if args.stage == "paired" and args.parent is None or args.world_model and args.stage != "paired":
        parser.error("Paired continuation needs its common parent; the world-model objective is a paired option")
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "final.pt").exists():
        raise FileExistsError(args.output / "final.pt")
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    if device.type == "cuda":
        torch.cuda.set_device(device)
        torch.cuda.reset_peak_memory_stats(device)
    membership = json.loads(args.membership.read_text()) if args.membership else {}
    membership = membership.get("membership", membership)
    if args.parent or args.resume:
        actor, vocab, payload = load_actor(args.resume or args.parent, device)
        saved_membership = payload["membership"]
        if membership and saved_membership != membership:
            raise ValueError("Registered episodes differ from restored checkpoint")
        membership = saved_membership
    else:
        vocab = training_vocabulary(args.data, membership.get("train"))
        actor = MultimodalActor(vocab).to(device)
        payload = None
    dataset = EpisodeDataset(args.data, "train", vocab, device, membership.get("train"))
    membership["train"] = dataset.episode_ids
    if args.stage != "benchmark" and "validation" not in membership:
        membership["validation"] = [m["episode_id"] for _, m in discover(args.data, "validation")]
    if not len(dataset.expert_rows):
        raise ValueError("No valid expert BC labels in the registered training episodes")
    if payload is None:
        ids = torch.as_tensor(dataset.expert_rows, device=device)
        actor.fit_scalers(dataset.states["proprio"][ids], dataset.states["action"][ids])
    if args.stage == "paired":
        actor.freeze_encoders()
    optimizer = torch.optim.AdamW(actor.parameters(), lr=args.lr, weight_decay=1e-5)
    if payload:
        optimizer.load_state_dict(payload["optimizer"])
        for group in optimizer.param_groups:
            group["lr"] = args.lr
    parent_hash = hashlib.sha256(args.parent.read_bytes()).hexdigest() if args.parent else None
    wm_hash = hashlib.sha256(args.world_model.read_bytes()).hexdigest() if args.world_model else None
    configuration = {"stage": args.stage, "steps": args.steps, "batch_size": args.batch_size, "seed": args.seed,
        "lr": args.lr, "parent_sha256": parent_hash, "world_model_sha256": wm_hash, "torch_version": torch.__version__,
        "device": str(device), "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU",
        "parameters": sum(p.numel() for p in actor.parameters()), "trainable_parameters": sum(p.numel() for p in actor.parameters() if p.requires_grad),
        "backbone": "In-project RGB CNN + metric depth/mask CNN + learned textual token pooling. Random initialization. No pretrained weights.",
        "clock": "elapsed sensor time from physical reset; no reference clock, phase, root or door state in actor inputs",
        "sampling": "per batch 1/3 upper-quartile measured command change, 1/6 contact if eligible, remainder uniform teacher labels",
        "train_valid_transitions": len(dataset.valid_rows), "train_expert_transitions": len(dataset.expert_rows),
        "train_contact_expert_rows": len(dataset.contact_rows), "vocabulary": vocab.tokens,
        "membership": membership}
    if args.resume:
        if payload["configuration"] != configuration:
            raise ValueError("Resume configuration differs from the saved run")
    atomic_json(args.output / "configuration.json", configuration)
    print(json.dumps(configuration), flush=True)
    objective = None
    if args.world_model:
        from learning.multimodal.world_model import make_policy_objective
        calibrated = torch.load(args.world_model, map_location="cpu", weights_only=False)
        if calibrated["common_actor_sha256"] != parent_hash:
            raise ValueError("Visual bridge was calibrated to a different common policy")
        del calibrated
        objective = make_policy_objective(args.world_model, device)
    def snapshot(step, sampler_state, digest, records):
        prior_records = payload.get("updates", []) if args.resume else []
        atomic_json(args.output / "progress.json", {"update": step, "batch_sequence_sha256": digest,
                                                    "updates": prior_records + records})
        if args.stage != "benchmark" and (step % args.save_every == 0 or step == args.steps):
            value = {"schema": "M1Piper-Multimodal-v1-actor-v1", "actor": actor.state_dict(),
                     "optimizer": optimizer.state_dict(), "configuration": configuration, "membership": membership,
                     "vocabulary": vocab.tokens, "update": step, "sampler_state": sampler_state,
                     "batch_sequence_sha256": digest, "updates": prior_records + records}
            atomic_save(args.output / ("final.pt" if step == args.steps else f"step_{step:06d}.pt"), value)
    history, _, digest = run_updates(actor, optimizer, dataset, args.steps, args.seed, args.batch_size, objective,
        start=payload["update"] if args.resume else 0, sampler_state=payload["sampler_state"] if args.resume else None,
        batch_digest=payload["batch_sequence_sha256"] if args.resume else None, on_interval=snapshot, interval=args.interval)
    if args.stage == "benchmark":
        atomic_json(args.output / "benchmark.json", {**configuration, "measurements": history, "discarded_updates": args.steps})
    else:
        val = EpisodeDataset(args.data, "validation", vocab, device, membership["validation"])
        metrics = evaluate_actor(actor, val, vocab)
        atomic_json(args.output / "evaluation.json", {"batch_sequence_sha256": digest, **metrics, **peak(device)})
        print(json.dumps(metrics, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
