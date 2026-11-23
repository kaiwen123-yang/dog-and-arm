"""Paired seed0 BC from a frozen joint Actor, using one clock per side."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions, PRIVILEGED_TRANSLATION, build_actor, sensor
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import ActionMap, make_model

ANCHOR = Path("results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt")
REFERENCE = Path("results/raw_large/b0/full_warp_hold_park_r1")
AUGMENT = Path("results/raw_large/b0/recovery_a_teacher_r1")
DESIGN = Path("config/b0/recovery_a_teacher_r1.json")
REF = {"pull": "pull_60_train", "push": "push_25_train"}


def dump(path, data):
    with path.open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)
        f.write("\n")


@torch.no_grad()
def episode(path, split, bank, rep, device):
    meta = json.loads((path / "metadata.json").read_text())
    if meta["wm_split"] != split or not (meta["finished"] and meta["held_action_replay"]):
        raise ValueError(f"Bad episode identity {path}")
    ref = REF[meta["task"]]
    length = int(bank.motion_ends[bank.ids[ref]]) - bank.starts[ref] - 1
    valid = np.load(path / "valid_full_interval.npy")
    n = min(length, len(valid))
    mask = valid[:n].copy()
    if path.parent == AUGMENT:
        mask &= np.load(path / "bc_positive_mask.npy")[:n]
    k = torch.as_tensor(np.flatnonzero(mask), device=device)
    if not len(k):
        raise ValueError(f"No aligned BC labels in {path}")
    q, v, prev = [tensor(np.load(path / (key + ".npy"), mmap_mode="r")[:n], device)
                  for key in ("qpos", "qvel", "last_action")]
    physical = sensor(rep, full_state(q, v), prev)
    h = physical[(k[:, None] + torch.arange(-9, 1, device=device)).clamp_min(0)]
    _, goal = bank.goals(rep, k + bank.starts[ref], q[k, :7])
    action = tensor(np.load(path / "action_clipped.npy")[:n], device)[k]
    return goal, h, action


def merge(items):
    return tuple(torch.cat(group) for group in zip(*items, strict=True))


def migrate(old, actor):
    """Append metric XYZ columns to each motion input tensor, keep old columns exact."""
    new = actor.state_dict()
    for name, value in old.items():
        if new[name].shape == value.shape:
            new[name] = value
            continue
        fill = {"encoders.motion.0.weight": 0., "goal_normalizers.motion._mean": 0.,
                "goal_normalizers.motion._std": .05, "goal_normalizers.motion._var": .05 ** 2}[name]
        if value.shape[-1] != 540 or new[name].shape[-1] != 570:
            raise ValueError(name)
        new[name].fill_(fill)
        new[name][..., :540].copy_(value)
    actor.load_state_dict(new, strict=True)


@torch.no_grad()
def score(actor, dataset, mapping):
    goals, history, labels = dataset
    outputs = [actor(build_actor_obs_td({"motion": g}, h))
               for g, h in zip(goals.split(256), history.split(256), strict=True)]
    mse = ((torch.cat(outputs) - labels) * tensor(mapping.scale, labels.device)).square()
    return dict(frames=len(goals), group_RMSE=[x.mean().sqrt().item()
                for x in mse.split((12, 4, 6, 1), -1)])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variant", choices=["A0", "A1", "A2", "A3"], required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--updates", type=int, default=128)
    ap.add_argument("--lr", type=float, default=2e-6)
    ap.add_argument("--validation-only", action="store_true", help="Score previously saved Actor on the four whole validation episodes")
    args = ap.parse_args()
    if Path(args.run).name != args.run or args.updates < 1 or args.lr <= 0:
        ap.error("Fresh run name and positive training budget required")
    out = Path("results/b0") / args.run
    if not args.validation_only:
        out.mkdir(exist_ok=False)
    device = "cuda:0"
    torch.manual_seed(0)
    torch.set_float32_matmul_precision("highest")
    source = torch.load(ANCHOR, map_location="cpu", weights_only=False)
    if source["updates"] or source["seed"] or source["collected"]:
        raise ValueError("Expected the frozen joint seed0 u0")
    cfg = dict(source["cfg"])
    expanded = args.variant in ("A1", "A3")
    augmented = args.variant in ("A2", "A3")
    cfg["actor_goal_schema"] = PRIVILEGED_TRANSLATION if expanded else "proprio_motion"
    cfg["reference_directory"] = str(REFERENCE)
    cfg["additional_bc_run"] = args.run
    model = make_model()
    mapping, rep = ActionMap(model), RobotRepresentation(model, device)
    bank = DoorMotions([REFERENCE / r for r in REF.values()], rep, device, actor_schema=cfg["actor_goal_schema"])
    actor, _ = build_actor(rep, cfg, model, device)
    migrate(source["actor"], actor)
    actor.eval()
    design = json.loads(DESIGN.read_text())["cases"]
    if args.validation_only:
        stored = torch.load(out / "checkpoint_000000.pt", map_location="cpu", weights_only=False)
        if stored["cfg"] != cfg or stored["additional_bc_updates"] != args.updates:
            raise ValueError("Checkpoint and requested training protocol disagree")
        actor.load_state_dict(stored["actor"])
        rows = {c["episode_id"]: score(actor, episode(AUGMENT / c["episode_id"], "validation", bank, rep, device), mapping)
                for c in design if c["split"] == "validation"}
        dump(out / "paired_validation.json", rows)
        return
    nominal = merge([episode(REFERENCE / name, "train", bank, rep, device) for name in REF.values()])
    old, _ = build_actor(rep, source["cfg"], model, device)
    old.load_state_dict(source["actor"])
    old.eval()
    with torch.no_grad():
        g, h, _ = (x[::31] for x in nominal)
        prior = old.raw(build_actor_obs_td({"motion": g[:, :540]}, h))
        diff = (actor.raw(build_actor_obs_td({"motion": g}, h)) - prior).abs().max().item()
        if diff > 1e-5:
            raise ValueError(f"Transfer failed, max action change {diff}")
    del old
    coverage = {}
    for c in design if augmented else ():
        if c["split"] == "train":
            coverage[c["episode_id"]] = episode(AUGMENT / c["episode_id"], "train", bank, rep, device)
    extra = merge(list(coverage.values())) if coverage else nominal
    dump(out / "actual_config.json", dict(variant=args.variant, seed=0, source=str(ANCHOR),
        reference=str(REFERENCE), source_bc_reference="full_held_warp_r1", schema=cfg["actor_goal_schema"],
        columns="0:480 joint q,v; 480:540 relative rotation6d; appended 540:570 ten root-frame reference XYZ when enabled",
        normalization="source frozen; XYZ zero mean, 0.05 m std fixed from declared translation scale, no held-out fit",
        initial_raw_action_max_abs=diff, optimizer="AdamW, no decay, fixed lr, all Actor parameters", lr=args.lr,
        batch=128, updates=args.updates, selected="last step", history=10, target="measured clipped logical action",
        nominal_frames=len(nominal[0]), extra_frames={k:len(v[0]) for k,v in coverage.items()},
        sampling="64 nominal + 64 pooled eligible coverage; both halves nominal for A0/A1; fixed sampling generator",
        extra_labels="positive mask only; physical failed/phase-mismatched/intervened intervals retained in raw data",
        losses="four equally weighted physical unit blocks; as in contact calibration; no artificial history noise",
        training_backend="recorded Warp held targets", wm_updates=0, h32_updates=0))
    weight = tensor(mapping.scale / np.repeat([.005, .1, .005, .0005], [12,4,6,1]), device) / 100
    opt = torch.optim.AdamW(actor.parameters(), lr=args.lr, weight_decay=0.)
    rng = torch.Generator(device=device).manual_seed(231123)
    with (out / "updates.jsonl").open("x", buffering=1) as log:
        for step in range(1, args.updates + 1):
            batches = []
            for data in (nominal, extra):
                ix = torch.randint(len(data[0]), (64,), device=device, generator=rng)
                batches.append(tuple(x[ix] for x in data))
            g, h, target = merge(batches)
            pred = actor.raw(build_actor_obs_td({"motion": g}, h))
            error = ((pred - target) * weight).square()
            loss = torch.stack([x.mean() for x in error.split((12,4,6,1), -1)]).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(actor.parameters(), 1.)
            opt.step()
            if step == 1 or step % 16 == 0 or step == args.updates:
                log.write(json.dumps(dict(step=step, loss=float(loss.detach())), allow_nan=False) + "\n")
    dump(out / "nominal_fit.json", score(actor, nominal, mapping))
    package = dict(source, cfg=cfg, actor=actor.state_dict(), additional_bc_updates=args.updates,
                   source=str(ANCHOR), additional_bc_variant=args.variant)
    torch.save(package, out / "checkpoint_000000.pt")
    torch.save(dict(optimizer=opt.state_dict(), generator=rng.get_state(), updates=args.updates),
               out / "bc_optimizer_rng.pt")


if __name__ == "__main__":
    main()
