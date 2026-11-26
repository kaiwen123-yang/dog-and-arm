"""MM03 frozen-parent model optimization on native simulation anchors."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

REPO = Path(__file__).resolve().parents[2]
MM02 = Path("/root/autodl-tmp/mm02-20261125")
TORCH = REPO / ".conda/envs/arm-and-dog/bin/python"
SEEDS = (1701, 1702, 1703)
VARIANTS = ("C0", "C8", "C32", "C32G", "CF32")


def read(path):
    return json.loads(Path(path).read_text())


def report(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    tmp.replace(path)


def bind_bridge(actor, vocab, wm_path, members, train_recovery, output, round_id,
                binding_identity, device):
    """Fit one new bridge to this *specific* frozen encoder and physical-model checkpoint."""
    import torch
    from torch.nn import functional as F
    from learning.multimodal.mm02_trajectory import encoder_id
    from learning.multimodal.world_model import PerceptualDynamics, VisualBridge
    from scripts.multimodal.mm02_dynamics import exposures, bridge_errors, metadata
    from scripts.multimodal.train_actor import atomic_save

    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    bundle = out / "trajectory_bundle.pt"
    dev = torch.device(device)
    encoder = encoder_id(actor)
    members = list(map(str, members))
    recoveries = list(map(str, train_recovery))
    config = dict(binding_identity=str(binding_identity), encoder_id=encoder, wm_path=str(wm_path),
                  members=members, train_recovery=recoveries, round=int(round_id))
    wm = torch.load(wm_path, map_location=dev, weights_only=False)
    if not members or any(metadata(p)["split"] != "train" for p in set(members + recoveries)):
        raise ValueError("Bind using actual training exposures and training-only anchor members")
    if len(set(members)) != len(members) or not set(recoveries).issubset(members):
        raise ValueError("Duplicate bridge members or recoveries outside physical replay")
    previous = torch.load(bundle, map_location=dev, weights_only=False) if bundle.exists() else None
    if previous and any(previous[key] != value for key, value in config.items()):
        raise ValueError("Bridge binding changed across resume")
    if previous and previous["bridge_updates"] == 600 and (out / "bridge.json").exists():
        return bundle
    model = PerceptualDynamics(wm["width"]).to(dev)
    model.load_state_dict(wm["model"], strict=True)
    model.eval().requires_grad_(False)
    print(f"bridge training exposures from {len(members)} episodes; encoder {encoder}",flush=True)
    x, y = exposures(actor, members, dev)
    generator = torch.Generator(device=dev).manual_seed(31701 + int(round_id))
    with torch.random.fork_rng(devices=[dev] if dev.type == "cuda" else []):
        torch.manual_seed(31701 + int(round_id))
        bridge = VisualBridge(y.shape[-1]).to(dev)
    bridge.mean.copy_(y.mean(0))
    bridge.scale.copy_(y.std(0, correction=0).clamp_min(.02))
    optimizer = torch.optim.AdamW(bridge.parameters(), lr=.001)
    start_step = 0
    if previous:
        bridge.load_state_dict(previous["bridge"])
        optimizer.load_state_dict(previous["bridge_optimizer"])
        generator.set_state(previous["bridge_rng"].cpu())
        start_step = previous["bridge_updates"]
    log = out / "bridge_applied.jsonl"
    attempts = sum(1 for _ in log.open()) if log.exists() else 0
    if attempts < start_step:
        raise ValueError("Missing bridge update records")
    objective = dict(horizon=32, imagination_batch=32, discount=.985, weight=.15, camera_period_ticks=5)
    started = time.perf_counter()
    for step in range(start_step + 1, 601):
        rows = torch.randint(len(x), (256,), generator=generator, device=dev)
        residual = (bridge(model.v_units(x[rows])) - y[rows]) / bridge.scale
        loss = F.smooth_l1_loss(residual, torch.zeros_like(residual))
        if not torch.isfinite(loss):
            raise FloatingPointError(f"Nonfinite bridge loss at {step}")
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()
        with log.open("a") as f:
            print(json.dumps(dict(step=step, loss=float(loss.detach()))), file=f)
        if step == 1 or step % 25 == 0:
            atomic_save(bundle, dict(**config, schema="mm03_bound_trajectory_v1",
                bridge=bridge.state_dict(), bridge_optimizer=optimizer.state_dict(), bridge_rng=generator.get_state(),
                bridge_updates=step, width=model.width, wm_updates=wm["updates"], model=model.state_dict(),
                vocabulary=vocab.tokens, actor_visual_dim=y.shape[-1], objective=objective))
            report(out / "progress.json", dict(stage="bridge", retained=step, paid=attempts+step-start_step))
    report(out / "bridge.json", dict(encoder_id=encoder, binding=str(binding_identity), wm_path=str(wm_path),
           retained=600, paid=attempts+600-start_step, exposures=len(x), batch=256,
           train=bridge_errors(model, bridge, x, y), last_run_wall_s=time.perf_counter()-started,
           bundle=str(bundle)))
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if Path(sys.executable).absolute() != TORCH.absolute() and TORCH.is_file():
        os.execv(str(TORCH), [str(TORCH), "-u", "-m", "scripts.multimodal.mm03_c", *sys.argv[1:]])
    import torch
    from learning.multimodal.actor import load_actor
    from learning.multimodal.mm02_trajectory import encoder_id
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.cuda.set_device(0)
    dev = torch.device("cuda:0")
    output = args.root / "C"
    if not 1 <= args.workers <= 25:
        raise ValueError("Invalid native worker count")
    manifest = read(REPO / "results/multimodal/mm02_20261125/manifest.json")
    sources = manifest["terminal_packages"]
    actor_path = Path(sources["supervised_aggregate/training"]["source"])
    wm_path = Path(sources["wm.pt"]["source"])
    actor, vocab, parent = load_actor(actor_path, dev)
    pcfg = parent["configuration"]
    if (pcfg["stage"], pcfg["branch"], pcfg["round"], parent["update"]) != ("paired", "supervised_aggregate", 6, 512):
        raise ValueError("C requires the supervised R6 terminal training checkpoint")
    if "optimizer" not in parent or "rng" not in parent or "sampler_state" not in parent:
        raise ValueError("Incomplete supervised R6 parent")
    wm = torch.load(wm_path, map_location="cpu", weights_only=False)
    if wm["round_updates"] != 1000 or wm["round"] != 6 or "optimizer" not in wm:
        raise ValueError("Incomplete physical dynamics parent")
    prior = torch.load(sources["trajectory_bundle.pt"]["source"], map_location="cpu", weights_only=False)
    actor.freeze_encoders()
    membership = read(MM02 / "round6/wm_membership.json")
    report(output / "parent.json", dict(actor=str(actor_path), wm=str(wm_path),
        inherited_lineage_actor=parent["lineage_new_actor_steps"], inherited_original_actor=parent["inherited_original_common_steps"],
        inherited_wm=wm["updates"], previously_bound_encoder=prior["encoder_id"], encoder=encoder_id(actor),
        old_bridge_copied=False, shared_bridge_updates=600, native_workers=args.workers, pid=os.getpid()))
    bundle = bind_bridge(actor, vocab, wm_path, wm["members"], membership["train_recovery"],
                         output / "bridge", 6, str(actor_path), dev)
    del prior, wm, parent
    from scripts.multimodal.mm03_c_train import compare
    compare(args.root, args.workers, actor_path, bundle, dev)


if __name__ == "__main__":
    main()
