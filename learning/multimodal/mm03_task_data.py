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
    def __init__(self, membership, vocab, device, *, run_root=None, member_file=None, scopes=()):
        self.device = torch.device(device)
        self.strata = defaultdict(lambda: defaultdict(list))
        self.source_rows = Counter()
        self.available_by_episode = {}
        self.contiguous_lengths = defaultdict(Counter)
        self.paths = list(dict.fromkeys(membership["teachers"] + membership["corrections"]))
        teacher_set = set(membership["teachers"])
        episodes = [(Path(p), json.loads((Path(p) / "metadata.json").read_text())) for p in self.paths]
        image_bytes = sum((p / (k + ".npy")).stat().st_size for p, _ in episodes for k in
                          ("rgb", "depth", "depth_valid"))
        rows = sum(m["transitions"]+1+(9 if m.get("anchor_tick") is not None else 0) for _,m in episodes)
        resident = self.device
        reservation = None
        self.residency = dict(device=str(resident),source_image_file_bytes=image_bytes)
        from scripts.multimodal.mm03_b_parallel import compact_row_policy, mapped_image_policy, stream_row_policy
        mapped = bool(mapped_image_policy(run_root,member_file))
        compact = mapped and compact_row_policy(run_root, member_file)
        streamed = compact and stream_row_policy(run_root, member_file)
        if self.device.type=="cuda" and not mapped:
            from scripts.multimodal.mm03_b_parallel import (GPU_HEADROOM,GPU_WORK_PER_OPTIMIZER,
                                                            estimated_row_bytes,choose_row_device)
            if run_root is not None:
                reservation,self.residency=choose_row_device(run_root,member_file,scopes,image_bytes,rows,
                    lambda:torch.cuda.mem_get_info(self.device)[0])
                resident=self.device if self.residency["device"]=="cuda" else torch.device("cpu")
            elif estimated_row_bytes(image_bytes,rows)>torch.cuda.mem_get_info(self.device)[0]-GPU_HEADROOM-GPU_WORK_PER_OPTIMIZER:
                resident=torch.device("cpu")
                self.residency["device"]="cpu"
        retry_on_host = False
        try:
            self.data = EpisodeDataset(None,"train",vocab,resident,episodes=episodes,map_images=mapped,
                                       compact_rows=compact,stream_rows=streamed)
        except torch.OutOfMemoryError:
            if resident.type!="cuda":
                raise
            retry_on_host=True
        if retry_on_host:
            # No model or optimizer step has started. Rebuild the exact same arrays
            # on host if a concurrent allocation invalidated the earlier observation.
            import gc
            gc.collect()
            torch.cuda.empty_cache()
            resident=torch.device("cpu")
            self.residency.update(device="cpu",fallback="CUDA allocation unavailable during dataset construction")
            self.data=EpisodeDataset(None,"train",vocab,resident,episodes=episodes,map_images=mapped,
                                     compact_rows=compact,stream_rows=streamed)
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
                    cuts = np.r_[0, np.flatnonzero(np.diff(ids) != 1)+1, len(ids)]
                    lengths, occurrences = np.unique(np.diff(cuts),return_counts=True)
                    self.contiguous_lengths[source,group].update({
                        int(length):int(count) for length,count in zip(lengths,occurrences,strict=True)})
                    self.strata[source, group][(m["side"], m["target_deg"], m["scene_id"])].append(ids)
                    self.source_rows[source] += len(ids)
            self.available_by_episode[m["episode_id"]] = counts
        self.commands = commands
        self.command_valid = command_valid
        auxiliary = (self.data.start_tensor,self.data.history_start_tensor,self.data.length_tensor,
                     self.data.backward_offsets,self.data.tasks,self.data.angles,commands,command_valid)
        image_tensors = sum(t.numel()*t.element_size() for t in self.data.images.values())
        all_tensors = image_tensors + sum(t.numel()*t.element_size() for t in (*self.data.states.values(),*auxiliary))
        self.residency.update(status="ready",device=resident.type,actual_image_tensor_bytes=image_tensors,
                              actual_row_tensor_bytes=all_tensors,actual_aux_and_state_tensor_bytes=all_tensors-image_tensors)
        if mapped:
            self.residency.update(image_storage="shared_original_npy",
                                  mapped_image_bytes=sum(v.nbytes for v in self.data.mapped_images.values()),
                                  compact_state_rows=compact,stream_state_rows=streamed)
        if reservation is not None:
            from scripts.multimodal.mm03_b import emit
            emit(reservation,self.residency)
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
        coverage_path = path.with_suffix(".coverage.json")
        if not coverage_path.is_file():
            groups = {}
            for source in ("teacher","correction"):
                for group in range(6):
                    lengths = self.contiguous_lengths[source,group]
                    groups[f"{source}/{group}"] = dict(contiguous_runs=sum(lengths.values()),
                        eligible_rows=sum(k*v for k,v in lengths.items()), max_length=max(lengths,default=0),
                        length_histogram=dict(sorted(lengths.items())))
            emit(coverage_path,dict(membership=member_sig,time_per_row_s=.020,groups=groups,
                 definition="Contiguous complete 20ms intervals within a single physical episode and phase group; corrections require actual student execution."))
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
