"""Registered MM-02 expert-label membership and replayable shared BC row orders."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np

from .dataset import EpisodeDataset, discover


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def _executors(path, n):
    sources = np.load(path / "execution_source.npy", allow_pickle=False)
    if sources.shape != (n,):
        raise ValueError(f"Missing per-action executor in {path}")
    if sources.dtype.kind in "iub":
        if not np.isin(sources, [0, 1]).all():
            raise ValueError(f"Unknown executor code in {path}")
        return np.where(sources, "teacher", "student")
    sources = sources.astype(str)
    if not np.isin(sources, ["teacher", "student"]).all():
        raise ValueError(f"Unknown executor name in {path}")
    return sources


class CorrectionPool:
    def __init__(self, old_data, old_ids, members, vocab, device):
        old = discover(old_data, "train", old_ids)
        additions = []
        for member in members:
            directory = Path(member).resolve(strict=True)
            if not (directory / "expert_action_target.npy").is_file():
                raise ValueError(f"New data has no independently recorded expert label: {directory}")
            meta = json.loads((directory / "metadata.json").read_text())
            if meta["scene_id"] not in ("tr_nominal", "tr_offset", "tr_load") or meta["split"] != "train":
                raise ValueError(f"Development/test member supplied for BC: {directory}")
            additions.append((directory, meta))
        additions.sort(key=lambda item: item[1]["episode_id"])
        episodes = old + additions
        dataset = EpisodeDataset(old_data, "train", vocab, device, episodes=episodes)
        self.dataset = dataset
        self.ids = {"old": [m["episode_id"] for _, m in old], "new": [m["episode_id"] for _, m in additions]}
        self.groups = {"old": {}, "new": {}}
        self.episode_records = []
        self.eligible_count = {"old": 0, "new": 0}
        self.global_task_keys = sorted((scene, side, goal) for scene in ("tr_nominal", "tr_offset", "tr_load")
                                       for side in ("pull", "push") for goal in (15, 25))
        digest = hashlib.sha256()
        for index, (directory, meta) in enumerate(episodes):
            pool = "old" if index < len(old) else "new"
            start, n = dataset.starts[index], dataset.lengths[index]-1
            lo, hi = np.searchsorted(dataset.expert_rows, [start, start+n])
            qualified = dataset.expert_rows[lo:hi]
            local = qualified - start
            key = (meta["scene_id"], meta["side"], int(meta["target_deg"]))
            if key not in self.global_task_keys:
                raise ValueError(f"Unregistered task {key} for {directory}")
            if pool == "old":
                sources = np.full(n, meta["source"])
            else:
                executors = _executors(directory, n)
                # Source policy, episode type and actual executor identify distinct behaviour strata.
                role = "recovery" if meta.get("anchor_tick") is not None and meta.get("parent_episode") else meta["source"]
                policy = str(meta.get("source_policy") or meta["source"])
                sources = np.char.add(f"{policy}/{role}/", executors)
            phases = np.asarray(np.load(directory / "phase.npy", allow_pickle=False))
            phase_names = meta["phases"]
            phase_counts = Counter(phase_names[int(p)] for p in phases[local])
            source_counts = {}
            for source in sorted(np.unique(sources).tolist()):
                rows = qualified[sources[local] == source]
                source_counts[str(source)] = len(rows)
                if len(rows):
                    by_source = self.groups[pool].setdefault(key, {}).setdefault(str(source), {})
                    by_source[index] = rows
                digest.update(str(source).encode())
                digest.update(rows.astype("<i8", copy=False).tobytes())
            self.eligible_count[pool] += len(local)
            digest.update(meta["episode_id"].encode())
            digest.update(np.array([start, n], dtype="<i8").tobytes())
            self.episode_records.append({"episode_id": meta["episode_id"], "directory": str(directory),
                                        "pool": pool, "scene": key[0], "side": key[1], "target_deg": key[2],
                                        "round": meta.get("round"), "policy": meta.get("source_policy"),
                                        "row_start": start, "num_actions": n, "qualified_labels": len(local),
                                        "qualified_executor_strata": source_counts,
                                        "qualified_teacher_phases": dict(phase_counts)})
        self.membership_signature = digest.hexdigest()

    def draw(self, name, size, rng):
        """For each sample draw task, available behaviour, eligible episode and row in that order."""
        output = np.empty(size, dtype=np.int32)
        tasks = sorted(self.groups[name])
        task_choice = rng.integers(len(tasks), size=size)
        for task_index, task in enumerate(tasks):
            which = np.flatnonzero(task_choice == task_index)
            by_source = self.groups[name][task]
            sources = sorted(by_source)
            source_choice = rng.integers(len(sources), size=len(which))
            for source_index, source in enumerate(sources):
                source_positions = which[source_choice == source_index]
                by_episode = by_source[source]
                episodes = sorted(by_episode)
                episode_choice = rng.integers(len(episodes), size=len(source_positions))
                for episode_index, episode in enumerate(episodes):
                    locations = source_positions[episode_choice == episode_index]
                    rows = by_episode[episode]
                    output[locations] = rows[rng.integers(len(rows), size=len(locations))]
        return output

    def schedule(self, path, seed, updates):
        import fcntl
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta_path = path.with_suffix(".json")
        fallback = [name for name in ("old", "new") if not self.eligible_count[name]]
        if len(fallback) == 2:
            raise ValueError("No qualified BC labels in either training pool")
        recipe = {"seed": seed, "updates": updates, "batch_size": 256,
                  "membership_signature": self.membership_signature, "empty_pool_fallback": fallback}
        with path.with_suffix(".lock").open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if path.exists() and meta_path.exists():
                saved = json.loads(meta_path.read_text())
                sequence = np.load(path, allow_pickle=False)
                if (any(saved[k] != v for k, v in recipe.items())
                        or hashlib.sha256(sequence.tobytes()).hexdigest() != saved["row_order_sha256"]):
                    raise ValueError(f"BC schedule disagrees with its registered membership or rows: {path}")
                return sequence, saved
            rng = np.random.default_rng(seed)
            blocks = []
            sampled_pools = []
            for desired in ("old", "new"):
                chosen = desired if self.eligible_count[desired] else ("new" if desired == "old" else "old")
                sampled_pools.append(chosen)
                blocks.append(self.draw(chosen, updates*128, rng).reshape(updates, 128))
            sequence = np.concatenate(blocks, axis=1)
            counts = np.bincount(sequence.ravel(), minlength=len(self.dataset.states["action"]))
            for rec in self.episode_records:
                row0 = rec["row_start"]
                rec["actual_draws"] = int(counts[row0:row0+rec["num_actions"]].sum())
            recipe.update({"sampled_pools_first_and_second_half": sampled_pools,
                           "row_order_sha256": hashlib.sha256(sequence.tobytes()).hexdigest(),
                           "qualified_rows": self.eligible_count, "final_generator_state": rng.bit_generator.state,
                           "missing_tasks": {k: [list(t) for t in self.global_task_keys if t not in self.groups[k]]
                                             for k in ("old", "new")}, "episodes": self.episode_records})
            with path.with_suffix(".npy.tmp").open("wb") as handle:
                np.save(handle, sequence, allow_pickle=False)
            path.with_suffix(".npy.tmp").replace(path)
            write_json(meta_path, recipe)
            return sequence, recipe

    def saturation(self, actor):
        import torch
        result = {}
        for pool in ("old", "new"):
            totals = defaultdict(int)
            for record in self.episode_records:
                if record["pool"] != pool:
                    continue
                start = record["row_start"]
                lo, hi = np.searchsorted(self.dataset.expert_rows, [start, start+record["num_actions"]])
                rows = torch.as_tensor(self.dataset.expert_rows[lo:hi], device=self.dataset.device)
                if not len(rows):
                    continue
                p = self.dataset.states["proprio"][rows]
                prev = self.dataset.states["previous"][rows]
                labels = self.dataset.states["action"][rows]
                totals["proprio_clipped"] += int((((p-actor.proprio_mean)/actor.proprio_std).abs() > 10).sum())
                totals["proprio_values"] += p.numel()
                totals["previous_clipped"] += int((((prev-actor.action_mean)/actor.action_std).abs() > 10).sum())
                totals["previous_values"] += prev.numel()
                totals["expert_at_action_bound"] += int((labels.abs() >= 1-1e-6).sum())
                totals["expert_values"] += labels.numel()
            result[pool] = dict(totals)
        return result
