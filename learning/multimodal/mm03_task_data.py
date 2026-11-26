"""Shared BC row membership with six task phases and real, episode-local histories."""
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import torch

from .dataset import EpisodeDataset

PHASES = ("approach_base", "settle", "reach_handle", "grasp", "open", "hold",
          "release", "retreat_arm", "post_release_hold", "stow", "retreat_base", "final")
PHASE_GROUP = {phase: i // 2 for i, phase in enumerate(PHASES)}
PHASE_GROUP.update(pregrasp=1, approach_arm=1)


class SharedRows:
    def __init__(self, membership, vocab, device):
        self.device = torch.device(device)
        self.strata = defaultdict(lambda: defaultdict(list))
        self.source_rows = Counter()
        self.available_by_episode = {}
        self.paths = list(dict.fromkeys(membership["teachers"] + membership["corrections"]))
        teacher_set = set(membership["teachers"])
        episodes = [(Path(p), json.loads((Path(p) / "metadata.json").read_text())) for p in self.paths]
        # Large later rounds can retain the contiguous lookup arrays in host memory.
        # Only the 256-row minibatch then crosses PCIe. Other lanes keep their GPU allocation.
        image_bytes = sum((p / (k + ".npy")).stat().st_size for p, _ in episodes for k in
                          ("rgb", "depth", "depth_valid"))
        resident = self.device if image_bytes <= 10 * 2**30 else torch.device("cpu")
        self.data = EpisodeDataset(None, "train", vocab, resident, episodes=episodes)
        commands = torch.zeros((len(self.data.states["episode"]), 2), device=resident)
        command_valid = torch.zeros(len(commands), device=resident, dtype=torch.bool)
        for i, (p, m) in enumerate(episodes):
            if m["scene_id"] not in ("tr_nominal", "tr_offset", "tr_load"):
                raise ValueError(f"Training member outside registered scenes: {p}")
            def arr(k):
                return np.load(p / (k + ".npy"), mmap_mode="r")
            n = len(arr("valid_transition"))
            valid = np.array(arr("valid_transition"), dtype=bool, copy=True)
            if (p / "expert_label_valid.npy").exists():
                valid &= arr("expert_label_valid")
            else:
                valid &= arr("action_supervision_mask")
            if m.get("schema") == "mm03_causal_task_v1":
                valid &= arr("action_supervision_mask")
            source = "teacher" if str(p) in teacher_set else "correction"
            if source == "correction" and (p / "execution_source.npy").exists():
                # New supervision comes only from steps the student actually executed.
                valid &= arr("execution_source") == 0
            if (p / "judge_phase.npy").exists():
                groups = arr("judge_phase") // 2
            else:
                mapping = np.asarray([PHASE_GROUP[name] for name in m["phases"]])
                groups = mapping[arr("phase")]
            start = self.data.starts[i]
            if (p / "expert_request.npy").exists() and m.get("expert_velocity_qualified", True):
                req = arr("expert_request")
                if req.shape != (n, 2) or not np.isfinite(req[valid]).all():
                    raise ValueError(f"Malformed compatible command labels: {p}")
                commands[start:start+n] = torch.tensor(np.asarray(req), device=resident)
                command_valid[start:start+n] = torch.tensor(valid, device=resident)
            counts = []
            for group in range(6):
                ids = start + np.flatnonzero(valid & (groups == group))
                counts.append(len(ids))
                if len(ids):
                    self.strata[source, group][(m["side"], m["target_deg"], m["scene_id"])].append(ids)
                    self.source_rows[source] += len(ids)
            self.available_by_episode[m["episode_id"]] = counts
        self.commands = commands
        self.command_valid = command_valid
        self.distribution = {}
        for key, strata in self.strata.items():
            # Each side, then goal inside side, then scene inside goal, then episode,
            # then eligible row in that episode gets equal conditional probability.
            sides = sorted({side for side, _, _ in strata})
            rows, weights = [], []
            for side in sides:
                goals = sorted({goal for s, goal, _ in strata if s == side})
                for goal in goals:
                    scenes = sorted(scene for s, g, scene in strata if s == side and g == goal)
                    for scene in scenes:
                        buckets = strata[side, goal, scene]
                        mass = 1 / (len(sides)*len(goals)*len(scenes)*len(buckets))
                        for ids in buckets:
                            rows.append(ids)
                            weights.append(np.full(len(ids), mass / len(ids)))
            probabilities = np.concatenate(weights)
            self.distribution[key] = np.concatenate(rows), probabilities / probabilities.sum()
        if not all(self.source_rows[source] for source in ("teacher", "correction")):
            raise ValueError(f"Cannot construct the registered 50:50 pools: {self.source_rows}")

    def schedule(self, path, updates, seed):
        path = Path(path)
        from scripts.multimodal.mm03_b import emit
        path.parent.mkdir(parents=True, exist_ok=True)
        member_sig = hashlib.sha256(json.dumps([self.paths, self.available_by_episode], sort_keys=True).encode()).hexdigest()
        meta_path = path.with_suffix(".json")
        header = dict(steps=updates, seed=seed, batch=256, members=member_sig, paths=self.paths)
        if path.exists() and meta_path.exists():
            m = json.loads(meta_path.read_text())
            if any(m[k] != v for k, v in header.items()):
                raise ValueError(f"Existing row order has different members or budget: {path}")
            return np.load(path, mmap_mode="r"), m
        rng = np.random.default_rng(seed)
        table = np.empty((updates, 256), dtype=np.int32)
        row = np.arange(updates * 128, dtype=np.int64)
        counts, fallback = {}, {}
        for half, source in enumerate(("teacher", "correction")):
            available = [g for g in range(6) if (source, g) in self.distribution]
            phase = row % 6
            for g in range(6):
                if g not in available:
                    at = np.flatnonzero(phase == g)
                    phase[at] = np.asarray(available)[np.arange(len(at)) % len(available)]
                    fallback[f"{source}/{g}"] = len(at)
            samples = np.empty(len(row), np.int32)
            for g in available:
                ids, weights = self.distribution[source, g]
                at = np.flatnonzero(phase == g)
                samples[at] = rng.choice(ids, size=len(at), replace=True, p=weights)
                counts[f"{source}/{g}"] = len(at)
            table[:, half*128:(half+1)*128] = samples.reshape(updates, 128)
        for line in table:
            rng.shuffle(line)
        tmp = path.with_suffix(".npy.part")
        with tmp.open("wb") as f:
            np.save(f, table, allow_pickle=False)
        os.replace(tmp, path)
        meta = dict(**header, counts_by_pool_phase=counts, missing_phase_fallback_draws=fallback,
                    available_rows_by_episode=self.available_by_episode, available_by_pool=dict(self.source_rows),
                    batch_rows_sha256=hashlib.sha256(table.tobytes()).hexdigest(),
                    end_generator_state=rng.bit_generator.state)
        emit(meta_path, meta)
        return table, meta

    def batch(self, rows):
        tensor = torch.tensor(np.array(rows, dtype=np.int64, copy=True), device=self.data.device)
        batch = self.data.batch_rows(tensor)
        batch["command"] = self.commands[tensor]
        batch["command_valid"] = self.command_valid[tensor]
        return {k: value.to(self.device, non_blocking=True) for k, value in batch.items()}
