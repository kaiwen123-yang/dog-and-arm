"""Collect validation-only Warp cohorts and score frozen door WMs on identical windows."""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
from supermimic.models import Dynamics

from learning.b0.contact_model import CONTEXT_NAMES, ContactRepresentation
from learning.b0.contact_policy import DoorMotions
from learning.b0.contact_training import ContactRun
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, make_model
from scripts.b0.h32_fit_recovery_wm import load_cohorts, validate
from scripts.b0.h32_recovery import write


def collect(args):
    weight = torch.load(args.actor, map_location="cpu", weights_only=False)
    cfg = dict(weight["cfg"], cohort_steps=40, worlds=64)
    reference_root = Path(cfg["reference_directory"])
    refs = [reference_root / name for name in cfg["references"]]
    out = Path("results/b0") / args.run
    raw = Path("results/raw_large/b0") / args.run
    out.mkdir(exist_ok=False)
    raw.mkdir(exist_ok=False)
    registration = dict(actor=str(args.actor), update=weight["updates"], behavior="frozen standard Actor with its training exploration",
                        reference_directory=str(reference_root), references=cfg["references"], worlds=cfg["worlds"],
                        policy_dt=cfg["policy_dt"], steps=40, collection_noise=cfg["collection_noise"],
                        seeds=args.seeds, split="validation", excluded_from_updates_and_replay=True,
                        backend="MuJoCo Warp; ten 2 ms substeps per target")
    write(out / "registration.json", registration)
    run = ContactRun(cfg, refs, refs, weight, weight, "cuda:0")
    rows = []
    for seed in args.seeds:
        torch.manual_seed(seed)
        np.random.seed(seed)
        name = f"validation_{seed}"
        folder = raw / name
        row = run.collect(folder, training=False)
        row.update(split="validation", group=name, seed=seed, path=str(folder))
        rows.append(row)
        print(name, row, flush=True)
    if len(run.replay.chunks):
        raise RuntimeError("Validation collection entered replay")
    write(out / "cohorts.json", rows)


def verify_intervals(folder, bank, *, has_substep_states):
    def read(key):
        return np.load(folder / f"{key}.npy", mmap_mode="r")

    valid = read("valid")
    if has_substep_states:
        active, steps = read("active"), read("physics_steps")
        if not np.all(steps[valid] == 10) or np.any(valid & ~active):
            raise ValueError(f"{folder}: invalid 20 ms span")
        for post, successor in (("sub_qpos_post", "next_qpos"), ("sub_qvel_post", "next_qvel")):
            if not np.array_equal(read(post)[:, :, -1][valid], read(successor)[valid]):
                raise ValueError(f"{folder}: final physical substep differs from {successor}")
    cont = valid[1:] & valid[:-1]
    if not np.array_equal(read("prev_action")[1:][cont], read("clipped")[:-1][cont]):
        raise ValueError(f"{folder}: previous action mismatch")
    frame = read("frame")
    ends = bank.motion_ends.cpu().numpy()
    motion = np.searchsorted(ends, frame, side="right")
    if np.any((motion[1:] != motion[:-1])[cont]) or np.any(np.diff(frame, axis=0)[cont] != 1):
        raise ValueError(f"{folder}: mismatched consecutive reference frames")
    if np.any((frame[valid] + 1) >= ends[motion[valid]]):
        raise ValueError(f"{folder}: successor outside motion")
    counts = valid.sum(0)
    return dict(attempted_lanes=len(counts), valid_lanes=int((counts > 0).sum()), valid_transitions=int(counts.sum()),
                valid_h32_lanes=int((counts >= 32).sum()), valid_h32_windows=int(np.maximum(counts - 31, 0).sum()),
                physical_failures=int((valid & (read("first_fail_substep") > 0)).sum()),
                full_terminal_included=True)


def score(args):
    registration = json.loads((args.data / "registration.json").read_text())
    rows = json.loads((args.data / "cohorts.json").read_text())
    # Registered paths are relative to the workspace that collected each dataset.
    source_root = args.data.resolve().parents[2]
    challenge = args.data.name == "recovery_b_grip_challenge_r1"
    if challenge:
        rows = [row for row in rows if row["split"] == "validation"]
        seeds = [seed for split, seed in registration["allocation"] if split == "validation"]
        anchor = source_root / registration["anchor"]
        refs = json.loads((anchor.parent / "actual_config.json").read_text())["cfg"]["references"]
    else:
        if registration["split"] != "validation" or any(row["split"] != "validation" for row in rows):
            raise ValueError("Expected validation-only cohorts")
        seeds = registration["seeds"]
        refs = registration["references"]
    if [row["seed"] for row in rows] != seeds:
        raise ValueError("Cohort seeds differ from registration")
    for row in rows:
        row["path"] = str(source_root / row["path"])
    model = make_model()
    rep = ContactRepresentation(model, args.device)
    paths = [source_root / registration["reference_directory"] / name for name in refs]
    bank = DoorMotions(paths, rep, args.device)
    counts = {row["group"]: verify_intervals(Path(row["path"]), bank, has_substep_states=not challenge) for row in rows}
    episodes, _ = load_cohorts(rows, paths, bank, model, args.device)
    mapping = ActionMap(model)
    weight = torch.load(args.wm, map_location="cpu", weights_only=False)
    hidden = weight["hidden"] if "hidden" in weight else weight["cfg"]["wm_hidden"]
    dyn = Dynamics(rep, 23, len(CONTEXT_NAMES), tensor(mapping.scale, args.device),
                   tensor(mapping.offset, args.device), tuple(hidden)).to(args.device)
    dyn.load_state_dict(weight["dyn"])
    if args.normalizers_from is not None:
        source = torch.load(args.normalizers_from, map_location="cpu", weights_only=False)["dyn"]
        for name in ("state_normalizer", "action_normalizer"):
            prefix = name + "."
            getattr(dyn, name).load_state_dict({key[len(prefix):]: value for key, value in source.items()
                                                if key.startswith(prefix)})
    dyn.eval()
    out = Path("results/b0") / args.run
    out.mkdir(exist_ok=False)
    write(out / "sources.json", dict(wm=str(args.wm), data=str(args.data), device=args.device,
          registration=registration, counts=counts, window_cap=args.window_cap, sampling_seed=301,
          normalizers_from=str(args.normalizers_from) if args.normalizers_from is not None else None,
          substep_state_check="every valid row matched recorded final physical substep" if not challenge else
                              "historical challenge stored per-substep forces and complete successor; no substep pose file",
          modes="first interval: physical finger loads and commanded reference phase; recontact uses branch-local contact history",
          predictor="open-loop propagation with measured clipped commands; comparison uses identical windows and successors",
          nonfinite="count per predictor, metric, side, horizon and mode; large finite errors retained in maximum"))
    validate(rep, dyn, model, episodes, out / "errors.csv", args.window_cap, window_details=True)
    print(out, counts, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    src = sub.add_parser("collect")
    src.add_argument("--actor", type=Path, required=True)
    src.add_argument("--seeds", type=int, nargs="+", required=True)
    src.add_argument("--run", required=True)
    val = sub.add_parser("score")
    val.add_argument("--wm", type=Path, required=True)
    val.add_argument("--data", type=Path, required=True)
    val.add_argument("--run", required=True)
    val.add_argument("--window-cap", type=int, default=512)
    val.add_argument("--device", default="cpu")
    val.add_argument("--normalizers-from", type=Path, help="Diagnostic forward pass: replace only WM state/action normalizer buffers")
    args = parser.parse_args()
    if Path(args.run).name != args.run or args.run in ("", ".", ".."):
        parser.error("Fresh output run name required")
    if args.command == "collect":
        if len(set(args.seeds)) != len(args.seeds):
            parser.error("Repeated validation cohort seed")
        collect(args)
    else:
        if args.window_cap < 1:
            parser.error("Positive window cap required")
        score(args)


if __name__ == "__main__":
    main()
