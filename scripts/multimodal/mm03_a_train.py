"""Fit the command-conditioned wheel/leg layer and causal velocity estimator."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np
import torch
from torch import nn

from learning.multimodal.mm03_low import LowPolicy


def write_json(path, value):
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix="."+path.name, delete=False) as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")
    os.replace(f.name, path)


def save(path, value):
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix="."+path.name, delete=False) as f:
        torch.save(value, f)
    os.replace(f.name, path)


def causal_features(p, previous):
    def mean_ten(x):
        # Repeat measured frame zero and the real frame-zero previous action.
        padded = np.concatenate((np.repeat(x[:1], 9, axis=0), x), axis=0)
        cumulative = np.concatenate((np.zeros_like(padded[:1]), np.cumsum(padded, axis=0, dtype=np.float64)))
        return ((cumulative[10:]-cumulative[:-10])*.1).astype(np.float32)
    return np.concatenate((p, mean_ten(p), previous, mean_ten(previous)), axis=1).astype(np.float32)


def physical_velocity(q, v):
    w, x, y, z = q[:, 3:7].T
    body_forward_world = np.stack((1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y)), 1)
    vertical_in_body = np.stack((2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)), 1)
    return np.stack(((body_forward_world*v[:, :3]).sum(1), (vertical_in_body*v[:, 3:6]).sum(1)), 1).astype(np.float32)


def contact_mask(path, prefix):
    meta = json.loads((path/"metadata.json").read_text())
    if meta["split"] != "train" or meta["scene_id"] not in ("tr_nominal", "tr_load", "tr_offset"):
        raise ValueError(f"Non-training contact membership {path}")
    if not (path/"expert_request.npy").is_file():
        return None
    phase = np.asarray(meta["phases"])[np.load(path/"phase.npy")]
    valid = np.load(path/"valid_transition.npy") & np.load(path/"expert_label_valid.npy")
    valid &= np.isin(phase, ("grasp", "open", "hold", "release"))
    if prefix:
        source = np.load(path/"execution_source.npy")
        if not (np.any(source == 1) and np.any(source == 0)):
            return None
        valid &= source == 0
    finger = np.any(np.load(path/"contact.npy") > .01, axis=1)
    # Include release after contact. A state never in contact with the door does
    # not become a door-disturbance example solely because of its phase label.
    valid &= finger | ((phase=="release") & np.maximum.accumulate(finger))
    return valid, finger


def contact_members(root, block):
    state = root/"A"
    manifest = state/f"block{block}_contact_members.json"
    with (state/f"block{block}_contact_members.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return snapshot_contact(root, block, manifest)


def snapshot_contact(root, block, manifest):
    if manifest.exists():
        return json.loads(manifest.read_text())["members"]
    while True:
        members = []
        if (root/"B"/"teacher_cases.json").is_file():
            teachers = sorted((root/"B"/"teachers").glob("*/episode/metadata.json"))
            continuations = sorted((root/"B"/"rounds").glob("r*/collect/*/episode/metadata.json"))
            for prefix, paths in ((False, teachers), (True, continuations)):
                for meta in paths:
                    try:
                        mask = contact_mask(meta.parent, prefix)
                    except FileNotFoundError:
                        # A case still publishing may complete before the next snapshot.
                        continue
                    if mask is not None and np.any(mask[0]):
                        members.append(dict(path=str(meta.parent), pool="contact_prefix" if prefix else "contact_teacher",
                                            eligible=int(mask[0].sum()), actual_contact=int((mask[0]&mask[1]).sum())))
            terminal_r1 = (root/"B"/"rounds"/"r01"/"collection_complete.json").exists()
            if terminal_r1 or any(m["pool"]=="contact_prefix" for m in members):
                write_json(manifest, dict(block=block, members=members, r1_collection_complete=terminal_r1,
                                           snapshot_utc=datetime.now(timezone.utc).isoformat()))
                return members
        time.sleep(10)


def members_for(root, seed, block):
    low = root/"A"/"low"/f"seed{seed}"
    folder = low/f"block{block}"
    index = folder/"members.json"
    if index.is_file():
        return json.loads(index.read_text())
    result = [dict(path=str(p.parent), pool="teacher") for p in sorted((root/"A"/"command_teacher").glob("*/result.json"))]
    if len(result)!=96:
        raise ValueError(f"Expected 96 complete initial command trials, found {len(result)}")
    for b in range(1, block+1):
        corrected = sorted((low/f"block{b}"/"correction").glob("*/result.json"))
        if len(corrected)!=32:
            raise ValueError(f"Correction block {b} has {len(corrected)} of 32 cases")
        result.extend(dict(path=str(j.parent), pool="corrected") for j in corrected)
    if block:
        result.extend(contact_members(root, block))
    write_json(index, result)
    return result


def assemble(members, device):
    sets = {key: [] for key in ("features", "command", "teacher", "velocity", "pool")}
    counts = {}
    pools = {"teacher": 0, "corrected": 1, "contact_teacher": 2, "contact_prefix": 3}
    for m in members:
        path = Path(m["path"])
        def read(key):
            return np.load(path/(key+".npy"), mmap_mode="r")
        if m["pool"].startswith("contact_"):
            valid, _ = contact_mask(path, m["pool"]=="contact_prefix")
            n = len(valid)
            x = causal_features(read("proprio")[:n], read("previous_action")[:n])
            cmd, target = read("expert_request"), read("expert_action_target")[:, :16]
            velocity = physical_velocity(read("qpos")[:n], read("qvel")[:n])
        else:
            valid = read("valid")
            x = causal_features(read("proprio"), read("previous"))
            cmd, target, velocity = read("command"), read("teacher16"), read("velocity")
        if not valid.any():
            counts[m["pool"]] = counts.get(m["pool"], 0)
            continue
        for key, value in (("features", x), ("command", cmd), ("teacher", target), ("velocity", velocity)):
            values = np.asarray(value[valid], dtype=np.float32)
            if not np.isfinite(values).all():
                raise ValueError(f"Nonfinite eligible {key} in {path}")
            sets[key].append(values)
        count = int(valid.sum())
        sets["pool"].append(np.full(count, pools[m["pool"]], np.uint8))
        counts[m["pool"]] = counts.get(m["pool"], 0) + count
    packed = {k:torch.from_numpy(np.concatenate(v)).to(device) for k,v in sets.items()}
    return packed, counts


def fit(root, seed, block):
    torch.set_num_threads(1)
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
                                          text=True).strip()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable for the MM03 low-level training job")
    device = torch.device("cuda")
    low = root/"A"/"low"/f"seed{seed}"
    folder = low/f"block{block}"
    folder.mkdir(parents=True, exist_ok=True)
    if (folder/"train_result.json").exists():
        return
    members = members_for(root, seed, block)
    data, counts = assemble(members, device)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    draw = torch.Generator(device=device).manual_seed(seed)
    model = LowPolicy().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=.0004)
    latest = folder/"latest.pt"
    parent = low/f"block{block-1}"/"latest.pt" if block else None
    target = 4000 if block else 12000
    start = 0
    loaded = latest if latest.is_file() else parent
    accumulated = 0.
    lifted = False
    if loaded:
        old = torch.load(loaded, map_location="cpu", weights_only=False)
        lifted = model.inherit(old["model"])
        old_opt = old["optimizer"]
        if lifted:
            # Existing names/order are identical. Newly appended stationary
            # parameters start with Adam's normal lazy zero moments.
            current = opt.state_dict()["param_groups"][0]["params"]
            original = old_opt["param_groups"][0]["params"]
            if original != current[:len(original)] or len(current)-len(original)!=4:
                raise ValueError("Original Adam ordering changed at correction transfer")
            old_opt["param_groups"][0]["params"] = current
            model.leg_scale.copy_(data["teacher"][:, :12].std(0, unbiased=False).clamp_min(.02))
        opt.load_state_dict(old_opt)
        lifted = lifted or bool(old.get("stationary_feedback_introduced_here", False) and loaded == latest)
        draw.set_state(old["draw"])
        torch.set_rng_state(old["cpu_rng"])
        torch.cuda.set_rng_state(old["cuda_rng"])
        if loaded == latest:
            start = old["update"]
            accumulated = old["wall_s"]
        del old
    else:
        model.calibrate(data["features"], data["teacher"])
    pool_ids = [(data["pool"]==i).nonzero().squeeze(-1) for i in range(4)]
    names = ("teacher", "corrected", "contact_teacher", "contact_prefix")
    available = [(name, ids) for name, ids in zip(names, pool_ids) if len(ids)]
    active = [ids for _, ids in available]
    if not active:
        raise RuntimeError("No eligible low-level training rows")
    # Genuine prefix-contact rows can number in tens while full teacher rows
    # number in tens of thousands. Square-root allocation keeps each source in
    # every batch without giving a few repeated examples a fixed quarter.
    weights = np.sqrt([len(ids) for ids in active])
    exact = (512-len(active))*weights/weights.sum()
    quotas = np.floor(exact).astype(int)+1
    remainder = 512-int(quotas.sum())
    for i in np.argsort(-(exact-np.floor(exact)), kind="stable")[:remainder]:
        quotas[i] += 1
    quotas = quotas.tolist()
    draws_per_pool = dict(zip((name for name,_ in available), quotas))
    tick = time.monotonic()
    loss_log = []
    model.train()
    def checkpoint(i):
        return dict(schema=model.schema, seed=seed, block=block, update=i, model=model.state_dict(),
                    stationary_feedback_introduced_here=lifted,
                    code_commit=code_commit, architecture="low_v1_with_learnable_stationary_residual",
                    optimizer=opt.state_dict(), cpu_rng=torch.get_rng_state(), cuda_rng=torch.cuda.get_rng_state(),
                    draw=draw.get_state(), membership=str(folder/"members.json"),
                    wall_s=accumulated+time.monotonic()-tick, parent_full=str(parent) if parent else None,
                    features="10 consecutive causal states and previous actual actions, current and mean",
                    action="pre-bias normalized legs12 and wheel4; learned increments and homogeneous velocity head",
                    velocity="estimated body-forward m/s and vertical gyro rad/s; true velocity training supervision only")
    print(json.dumps(dict(seed=seed, block=block, restored=start, target=target, rows=counts, train_pid=os.getpid())), flush=True)
    for i in range(start+1, target+1):
        idx = torch.cat([ids[torch.randint(len(ids), (n,), generator=draw, device=device)] for ids,n in zip(active, quotas)])
        x = data["features"][idx]
        estimated, v = model.from_features(x, data["command"][idx])
        labels = data["teacher"][idx]
        leg = ((estimated[:, :12]-labels[:, :12])/model.leg_increment_scale).square().mean()
        wheel = ((estimated[:, 12:]-labels[:, 12:])/model.wheel_loss_scale).square().mean()
        velocity = ((v-data["velocity"][idx])/model.velocity_units).square().mean()
        loss = leg + wheel + .5*velocity
        opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 3., error_if_nonfinite=True)
        opt.step()
        loss_log.append(torch.stack((leg.detach(), wheel.detach(), velocity.detach())))
        if i%128==0 or i==target:
            losses = torch.stack(loss_log).mean(0).tolist()
            loss_log.clear()
            receipt = dict(seed=seed, block=block, update=i, rows=counts, batch=512, losses=losses, code_commit=code_commit,
                           draws_per_batch_by_pool=draws_per_pool,
                           extra_trained_parameters=sum(p.numel() for p in model.parameters()),
                           stationary_feedback_introduced_here=lifted,
                           wall_s=accumulated+time.monotonic()-tick, gpu_peak_bytes=torch.cuda.max_memory_allocated())
            save(latest, {**checkpoint(i), "last_metrics": receipt})
            write_json(folder/"progress.json", receipt)
            print(json.dumps(receipt), flush=True)
    # The latest snapshot is atomic before the deploy path becomes visible to B.
    save(folder/"deploy.pt", dict(schema=model.schema, model=model.state_dict(), seed=seed, block=block, code_commit=code_commit,
         updates_this_block=target, full_checkpoint=str(latest)))
    receipt = torch.load(latest, map_location="cpu", weights_only=False)["last_metrics"]
    write_json(folder/"progress.json", receipt)
    write_json(folder/"train_result.json", {**receipt, "updates": target, "bc_rows": target*512,
               "total_seed_updates": 12000+4000*block, "latest": str(latest), "deploy": str(folder/"deploy.pt"),
               "resume_parent": str(parent) if parent else None, "seed_scope": "new L16 and estimator initialization"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--block", type=int, required=True)
    args = parser.parse_args()
    fit(args.root.resolve(), args.seed, args.block)
