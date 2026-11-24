"""Train the C20/T2 numerical comparison on one persisted sequence of train-only windows."""
import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

import numpy as np
import torch
from tensordict import TensorDict
import yaml
from supermimic.learners import wm_learner
from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg, SCHEMA
from learning.b0.contact_sources import RegisteredWM, native_episodes
from learning.b0.physics import ActionMap, make_model
from learning.b0.temporal_dynamics import make_dynamics

OUT = Path("results/b0/standard_temporal_20261124")
RAW = Path("results/raw_large/b0/temporal_pair_v1")
SOURCE = Path("results/b0/response_wm_v1/wm_000000.pt")
RECIPE = Path("config/b0/standard_temporal_v1.yaml")
NODES = (0, 50, 200, 1000)
DEVICE = "cuda:0"


def build_pool(model, rep):
    prior = json.loads(Path("results/b0/lanes_wm_v1/config.json").read_text())
    paths = [Path(ep["path"]) for ep in prior["sources"] if ep["split"] == "train"]
    return RegisteredWM(yaml.safe_load(RECIPE.read_text()), model, rep, native_episodes(paths, DEVICE), DEVICE)


def register_draws(pool):
    RAW.mkdir(exist_ok=False, parents=True)
    names = ["native", *pool.recipe["sources"]]
    source_ids = np.empty((1000, 256), dtype=np.uint8)
    starts = np.empty((1000, 256), dtype=np.int32)
    inventory = {name: [dict(group=e.group, path=str(e.path), n=len(e.state), side=e.side)
                        for e in pool.pools[name, 1].episodes] for name in names}
    for k in range(len(starts)):
        h = 1 if k % 10 < 2 else 7
        native, warp = (pool.recipe["warm"][f"h{h}_{s}"] for s in ("native", "warp"))
        if native + warp != 256 or any((s, h) not in pool.pools for s in names):
            raise ValueError("The registered offline source allocation is incomplete")
        counts = [native] + [warp // (len(names)-1)] * (len(names)-1)
        for i in range(warp % (len(names)-1)):
            counts[1 + (k+i) % (len(names)-1)] += 1
        offset = 0
        for i, (name, count) in enumerate(zip(names, counts, strict=True)):
            indices, _ = pool.pools[name, h].sample_indices(count)
            sl = slice(offset, offset + count)
            source_ids[k, sl] = i
            starts[k, sl] = indices.cpu().numpy()
            offset += count
    np.savez_compressed(OUT/"paired_indices.npz", source=source_ids, start=starts)
    (OUT/"paired_sources.json").write_text(json.dumps(dict(
        seed=0, recipe=str(RECIPE), initializer=str(SOURCE), names=names, inventory=inventory,
        legal_windows=pool.inventory, index="absolute state offset in source-ordered concatenation",
        schedule="k%10 < 2 gives H1, otherwise H7; index file saved before either optimizer step"
    ), indent=2))


def replay_batch(pool, names, src, starts, h):
    parts = []
    for i, name in enumerate(names):
        group = pool.pools[name, h]
        first = torch.as_tensor(starts[src == i], device=DEVICE, dtype=torch.long)
        ix = first[:, None] + group.offset
        parts.append(TensorDict(dict(state=group.state[ix], action=group.action[ix],
                                     sim_ctx=group.context[ix]), batch_size=ix.shape))
    return torch.cat(parts)


def interval_diagnostics(rows):
    by_horizon = {}
    for horizon in (1, 7):
        norms = np.asarray([r['grad_norm'] for r in rows if r['h'] == horizon])
        by_horizon[f'H{horizon}'] = dict(
            batches=len(norms), preclip_p50=float(np.median(norms)),
            preclip_p95=float(np.percentile(norms, 95)), preclip_max=float(norms.max()),
            clipped_batches=int((norms > 1.).sum()))
    return dict(first=rows[0]['k'], last=rows[-1]['k'], gradients=by_horizon,
                peak_allocated_bytes=max(r['peak_allocated_bytes'] for r in rows))


def checkpoint_receipt(arm, rows):
    receipt = interval_diagnostics(rows)
    (OUT/f"{arm}_review_{rows[-1]['k']:06}.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt), flush=True)


def main(args):
    torch.manual_seed(0)
    torch.set_float32_matmul_precision("high")
    model = make_model()
    rep = ContactRepresentation(model, DEVICE)
    pool = build_pool(model, rep)
    if args.arm == "indices":
        return register_draws(pool)
    registry = json.loads((OUT/"paired_sources.json").read_text())
    for name in registry["names"]:
        episodes = pool.pools[name, 1].episodes
        actual = [dict(group=e.group, path=str(e.path), n=len(e.state), side=e.side) for e in episodes]
        if actual != registry["inventory"][name]:
            raise ValueError("Source order, boundaries or regenerated assets changed")
    with np.load(OUT/"paired_indices.npz") as f:
        src, starts = f["source"], f["start"]
    init = torch.load(SOURCE, weights_only=False, map_location="cpu")
    root = RAW / args.arm
    root.mkdir(exist_ok=args.resume > 0)
    dyn = make_dynamics(model, rep, ActionMap(model), init["hidden"], args.arm, DEVICE)
    state = (torch.load(root/f"wm_{args.resume:06}.pt", weights_only=False, map_location="cpu")
             if args.resume else init)
    dyn.load_state_dict(state["dyn"])
    learners = {h: wm_learner.WorldModelLearner(dyn, rep, ContactWorldModelCfg(
        batch_size=256, horizon=h+1, num_batches=1), DEVICE) for h in (1, 7)}
    optimizers = learners[7].optimizers
    learners[1].optimizers = optimizers
    if args.resume:
        for opt, saved in zip(optimizers, state["optimizers"], strict=True):
            opt.load_state_dict(saved)
    grad_norm = torch.zeros((), device=DEVICE)
    original_step = wm_learner._optimize_step

    def observe_norm(*a, **kw):
        result = original_step(*a, **kw)
        grad_norm.copy_(result.detach())
        return result

    wm_learner._optimize_step = observe_norm
    start_time = time.monotonic()
    def save(k):
        dest = root/f"wm_{k:06}.pt"
        tmp = dest.with_suffix(".tmp")
        torch.save(dict(dyn=dyn.state_dict(), schema=SCHEMA, temporal_id=args.arm,
                        seed=0, hidden=init["hidden"], minibatches=k, initializer=str(SOURCE),
                        optimizers=[o.state_dict() for o in optimizers],
                        cpu_rng=torch.get_rng_state(), cuda_rng=torch.cuda.get_rng_state()), tmp)
        tmp.replace(dest)
    if not args.resume:
        save(0)
    else:
        torch.set_rng_state(state["cpu_rng"])
        torch.cuda.set_rng_state(state["cuda_rng"])
    stats_path = OUT/f"{args.arm}_training.jsonl"
    with stats_path.open("a" if args.resume else "x", buffering=1) as log:
        interval = []
        for k in range(args.resume, args.stop):
            h = 1 if k % 10 < 2 else 7
            batch = replay_batch(pool, registry["names"], src[k], starts[k], h)
            metrics = learners[h].update([batch])
            row = dict(k=k+1, h=h, arm=args.arm, process_start_at=args.resume,
                       elapsed_s=time.monotonic()-start_time, grad_norm=float(grad_norm),
                       clip_max_norm=1., peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                       peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                       losses={key:float(v) for key,v in metrics.items()})
            if not np.isfinite([row["grad_norm"], *row["losses"].values()]).all():
                (OUT/f"{args.arm}_nonfinite.json").write_text(json.dumps(row))
                raise FloatingPointError(f"Nonfinite update {k+1}")
            log.write(json.dumps(row, allow_nan=False)+"\n")
            interval.append(row)
            if k+1 in NODES:
                save(k+1)
                checkpoint_receipt(args.arm, interval)
                interval.clear()
                print(f"{args.arm} +{k+1}, loss {row['losses']['Loss/state']}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("indices", "C20", "T2"))
    parser.add_argument("--resume", default=0, choices=NODES, type=int)
    parser.add_argument("--stop", default=50, choices=NODES[1:], type=int)
    main(parser.parse_args())
