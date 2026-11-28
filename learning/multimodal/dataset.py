"""Episode-local causal windows with image exposure/decision-time checks."""
from functools import cached_property
import json
from pathlib import Path

import numpy as np
import torch

from .actor import HISTORY, Vocabulary, command_angle_rad


def discover(root, split, episode_ids=None):
    root = Path(root)
    wanted = set(episode_ids) if episode_ids is not None else None
    result = []
    for path in sorted(root.rglob("metadata.json")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        meta = json.loads(path.read_text())
        identity = meta.get("episode_id")
        if meta.get("split") != split or wanted is not None and identity not in wanted:
            continue
        if identity is None or "task_text" not in meta:
            continue
        result.append((path.parent, meta))
    identities = [m["episode_id"] for _, m in result]
    if len(identities) != len(set(identities)):
        raise ValueError(f"Duplicate {split} episode IDs")
    if wanted is not None and set(identities) != wanted:
        raise ValueError(f"Missing {split} episodes: {sorted(wanted - set(identities))}")
    if not result:
        raise ValueError(f"No {split} MM-01 episodes in {root}")
    return result


def training_vocabulary(root, episode_ids=None):
    return Vocabulary.fit(m["task_text"] for _, m in discover(root, "train", episode_ids))


def pack_state_rows(parts, device):
    """Copy one column to its final storage in bounded chunks, preserving NumPy promotion."""
    dtype = np.result_type(*{part.dtype for part in parts})
    shape = parts[0].shape[1:]
    total = sum(len(part) for part in parts)
    tensor = torch.empty((total, *shape), device=device, dtype=torch.from_numpy(np.empty(0, dtype=dtype)).dtype)
    block_rows = max(1, (32 << 20) // (dtype.itemsize * int(np.prod(shape))))
    first_part = start = end = 0
    for i, part in enumerate(parts, 1):
        end += len(part)
        if end - start >= block_rows or i == len(parts):
            block = np.concatenate(parts[first_part:i], axis=0, dtype=dtype)
            tensor[start:end].copy_(torch.from_numpy(block))
            first_part, start = i, end
    return tensor


class EpisodeDataset:
    """Contiguous device-side tensors; states and camera frames retain independent clocks."""
    def __init__(self, root, split, vocab, device, episode_ids=None, *, episodes=None, map_images=False,
                 compact_rows=False):
        self.device = torch.device(device)
        self.episodes = discover(root, split, episode_ids) if episodes is None else list(episodes)
        self.episode_ids = [m["episode_id"] for _, m in self.episodes]
        if len(self.episode_ids) != len(set(self.episode_ids)) or any(
                m["split"] != split for _, m in self.episodes):
            raise ValueError(f"Duplicate episode or incorrect split in {split} data")
        arrays = {key: [] for key in ("proprio", "previous", "sensor", "action", "image", "episode")}
        images = {"rgb": [], "depth": [], "depth_valid": []}
        self.mapped_images = {}
        if map_images:
            from .mm03_image_rows import MappedFrames
            self.mapped_images = {k: MappedFrames() for k in images}
        self.starts, self.history_starts, self.lengths = [], [], []
        expert_rows, contact_rows, transition_rows = [], [], []
        add_transitions, add_experts, add_contacts = (
            rows.append if compact_rows else rows.extend for rows in (transition_rows, expert_rows, contact_rows))
        tasks, angles = [], []
        pos = 0
        frame = 1  # Row zero is an explicitly missing frame.
        for i, (directory, meta) in enumerate(self.episodes):
            def load(name):
                # State and image blocks are concatenated below. Eager reads release each
                # descriptor before the next episode, including large sets of short forks.
                return np.load(directory / (name + ".npy"), allow_pickle=False)
            correction = (directory / "expert_action_target.npy").is_file()
            action = load("executed_action_clipped" if correction else "action_clipped")
            expert = load("expert_action_target") if correction else action
            n = len(action)
            t = load("t")
            image_t, idx = load("image_t"), load("image_index").astype(np.int64)
            if len(t) != n+1 or idx.shape != t.shape or np.any(np.diff(t) <= 0):
                raise ValueError(f"Invalid decision boundaries in {directory}")
            valid_image = idx >= 0
            if np.any(idx[valid_image] >= len(image_t)):
                raise ValueError(f"Invalid image index in {directory}")
            age = np.zeros_like(t)
            age[valid_image] = t[valid_image] - image_t[idx[valid_image]]
            if np.any(age < -1e-6):
                raise ValueError(f"Future image joined to decision in {directory}")
            expected = np.searchsorted(image_t, t + 1e-7, side="right") - 1
            if np.any(idx[valid_image] != expected[valid_image]):
                raise ValueError(f"Image index does not identify the latest available frame in {directory}")
            s = load("proprio")
            previous = load("previous_action")
            if s.shape != (n+1, 52) or previous.shape != (n+1, 23) or action.shape != (n, 23):
                raise ValueError(f"State/action layout error in {directory}")
            if not np.allclose(previous[1:], action, atol=1e-6):
                raise ValueError(f"Previous action is not the executed action in {directory}")
            if correction and (directory / "history_prefix_proprio.npy").is_file():
                past_p = load("history_prefix_proprio")
                past_u = load("history_prefix_previous_action")
                expected_prefix = 0 if len(past_p) == 0 and abs(t[0]) <= 1e-6 else HISTORY-1
                if past_p.shape != (expected_prefix, 52) or past_u.shape != (expected_prefix, 23):
                    raise ValueError(f"Invalid causal prefix in {directory}")
            else:
                past_p, past_u = s[:0], previous[:0]
                if (correction and abs(t[0]) > 1e-6) or not np.allclose(previous[0], 0, atol=1e-7):
                    raise ValueError(f"Non-reset episode without restored history in {directory}")
            eligible = load("valid_transition").astype(bool)
            if correction:
                # A query's independent qualification survives subsequent task/transition failure.
                labeled = load("expert_label_valid").astype(bool)
                if expert.shape != (n, 23) or not np.isfinite(expert[labeled]).all() or (
                        np.abs(expert[labeled]) > 1.000001).any():
                    raise ValueError(f"Invalid eligible normalized expert targets in {directory}")
            else:
                labeled = eligible & load("action_supervision_mask").astype(bool)
            contact = np.asarray(load("contact"))
            if eligible.shape != (n,) or labeled.shape != (n,) or contact.shape != (n, 2):
                raise ValueError(f"Transition mask/contact layout error in {directory}")
            prefix = len(past_p)
            first = pos + prefix
            add_transitions(first + np.flatnonzero(eligible))
            add_experts(first + np.flatnonzero(labeled))
            add_contacts(first + np.flatnonzero(labeled & (contact.max(axis=1) > 0.05)))
            arrays["proprio"].extend((past_p, s))
            arrays["previous"].extend((past_u, previous))
            clock = t if correction else t - t[0]
            sensor = np.stack((np.maximum(age, 0), valid_image, clock), axis=-1).astype(np.float32)
            arrays["sensor"].extend((np.zeros((prefix, 3), np.float32), sensor))
            arrays["action"].extend((np.zeros((prefix, 23), np.float32), expert, np.zeros((1,23), np.float32)))
            arrays["image"].extend((np.zeros(prefix, np.int64), np.where(valid_image, frame + idx, 0)))
            arrays["episode"].append(np.full(prefix+n+1, i, np.int64))
            for k in images:
                if map_images:
                    self.mapped_images[k].append(directory / (k + ".npy"), len(image_t))
                    continue
                value = load(k)
                if len(value) != len(image_t):
                    raise ValueError(f"Image/time count differs in {directory}/{k}")
                if not images[k]:
                    images[k].append(np.zeros((1, *value.shape[1:]), dtype=value.dtype))
                images[k].append(value)
            self.starts.append(first)
            self.history_starts.append(pos)
            self.lengths.append(n+1)
            pos = first+n+1
            frame += len(image_t)
            text = meta["task_text"]
            angle = command_angle_rad(text)
            if abs(np.rad2deg(angle) - float(meta["target_deg"])) > 1e-5:
                raise ValueError(f"Text/supervised target differs in {directory}")
            tasks.append(vocab.encode(text))
            angles.append(angle)
        self.start_tensor = torch.as_tensor(self.starts, device=self.device)
        self.history_start_tensor = torch.as_tensor(self.history_starts, device=self.device)
        self.length_tensor = torch.as_tensor(self.lengths, device=self.device)
        self.backward_offsets = torch.arange(1-HISTORY, 1, device=self.device)
        self.tasks = torch.tensor(tasks, dtype=torch.long, device=self.device)
        self.angles = torch.tensor(angles, dtype=torch.float32, device=self.device)
        if compact_rows:
            self.states = {k: pack_state_rows(arrays.pop(k), device) for k in tuple(arrays)}
        else:
            self.states = {k: torch.from_numpy(np.concatenate(rows, axis=0)).to(device) for k, rows in arrays.items()}
        self.images = {k: torch.from_numpy(np.concatenate(rows, axis=0)).to(device)
                       for k, rows in images.items() if rows}
        if compact_rows:
            self.valid_rows, self.expert_rows, self.contact_rows = (
                np.concatenate(parts) for parts in (transition_rows, expert_rows, contact_rows))
        else:
            self.valid_rows = np.asarray(transition_rows, dtype=np.int64)
            self.expert_rows = np.asarray(expert_rows, dtype=np.int64)
            self.contact_rows = np.asarray(contact_rows, dtype=np.int64)
            _ = self.moving_rows

    @cached_property
    def moving_rows(self):
        # The generic sampler uses motion quartiles. MM03 supplies its own frozen row order.
        if not len(self.expert_rows):
            return self.expert_rows
        rows = torch.as_tensor(self.expert_rows, device=self.device)
        targets = self.states["action"][rows]
        delta = ((targets - self.states["previous"][rows]) / targets.std(0, unbiased=False).clamp_min(.018))
        motion = delta.square().mean(-1).sqrt().cpu().numpy()
        return self.expert_rows[motion >= np.quantile(motion, 0.75)]

    def sample_indices(self, rng, size):
        if not len(self.expert_rows):
            raise ValueError("No valid teacher action labels in this dataset")
        n_contact = size // 6 if len(self.contact_rows) else 0
        n_moving = size // 3
        chunks = [rng.choice(self.expert_rows, size-n_moving-n_contact), rng.choice(self.moving_rows, n_moving)]
        if n_contact:
            chunks.append(rng.choice(self.contact_rows, n_contact))
        rows = np.concatenate(chunks)
        rng.shuffle(rows)
        return rows

    def batch(self, episode_indices, local_ticks):
        episode = torch.as_tensor(episode_indices, device=self.device, dtype=torch.long)
        tick = torch.as_tensor(local_ticks, device=self.device, dtype=torch.long)
        if bool(((tick < 0) | (tick >= self.length_tensor[episode])).any()):
            raise IndexError("Episode-local state index out of range")
        return self.batch_rows(self.start_tensor[episode] + tick)

    def batch_rows(self, rows):
        rows = torch.as_tensor(rows, device=self.device, dtype=torch.long)
        episode = self.states["episode"][rows]
        history = torch.maximum(rows[:,None] + self.backward_offsets, self.history_start_tensor[episode, None])
        image_id = self.states["image"][rows]
        if self.mapped_images:
            indices = image_id.detach().cpu().numpy()
            frames = {k: v.gather(indices).to(self.device) for k,v in self.mapped_images.items()}
        else:
            frames = {k: v[image_id] for k, v in self.images.items()}
        return {**frames, "image_id": image_id,
                "tokens": self.tasks[episode], "command_angle_rad": self.angles[episode],
                "proprio_history": self.states["proprio"][history], "previous_history": self.states["previous"][history],
                "sensor": self.states["sensor"][rows], "action": self.states["action"][rows]}

    def sample(self, batch_size, rng):
        return self.batch_rows(self.sample_indices(rng, batch_size))
