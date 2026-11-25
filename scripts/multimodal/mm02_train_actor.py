"""Execute and recover one registered MM-02 pilot, trainable-encoder BC or paired block."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import random
import time

import numpy as np
import torch

from learning.multimodal.actor import MultimodalActor, load_actor
from learning.multimodal.correction_sampling import CorrectionPool, write_json
from scripts.multimodal.train_actor import atomic_save, bc_objective, peak, synchronize


SCHEMA = "M1Piper-Multimodal-DAggerWM-v2-actor-v1"
METHOD = "M1Piper-Multimodal-DAggerWM-v2"
ENCODER_PREFIX = ("rgb_encoder.", "depth_encoder.", "visual_projection.", "embedding.", "token_weight.",
                  "text_projection.")
PILOT = ("fixed", "adaptive_slope_only")
CHAINS = ("supervised_aggregate", "model_trajectory")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def restore_optimizer(actor, old_actor, parent):
    old = parent["optimizer"]
    if "optimizer_names" in parent:
        old_names = parent["optimizer_names"]
    elif parent["schema"] == "M1Piper-Multimodal-v1-actor-v1" and len(old["param_groups"]) == 1:
        # MM-01 train_actor.py constructed AdamW(actor.parameters()) on the fixed architecture.
        old_names = [[name for name, _ in old_actor.named_parameters()]]
    else:
        raise ValueError("No known name mapping for parent AdamW")
    old_ids = {}
    for group, names in zip(old["param_groups"], old_names, strict=True):
        for name, pid in zip(names, group["params"], strict=True):
            if name in old_ids:
                raise ValueError(f"Duplicate old AdamW name: {name}")
            old_ids[name] = pid
    named = dict(actor.named_parameters())
    groups = [[n for n in named if n != "servo_slope"]]
    if "servo_slope" in named:
        groups.append(["servo_slope"])
    param_groups = []
    for names in groups:
        param_groups.append({"params": [named[n] for n in names],
                             "lr": 1e-4, "weight_decay": 0. if names == ["servo_slope"] else 1e-5})
    optimizer = torch.optim.AdamW(param_groups)
    restored = optimizer.state_dict()
    for group, names in zip(restored["param_groups"], groups, strict=True):
        source_opts = old["param_groups"][1 if names == ["servo_slope"] and len(old_names) == 2 else 0]
        group.update({k: v for k, v in source_opts.items() if k not in ("params", "param_names", "lr", "weight_decay")})
        for name, new_id in zip(names, group["params"], strict=True):
            if name not in old_ids:
                if name != "servo_slope":
                    raise ValueError(f"Missing old AdamW state for {name}")
                continue
            oid = old_ids[name]
            if oid not in old["state"]:
                raise ValueError(f"No accumulated AdamW state for {name}")
            state = old["state"][oid]
            if state["exp_avg"].shape != named[name].shape or state["exp_avg_sq"].shape != named[name].shape:
                raise ValueError(f"AdamW moment does not match {name}")
            restored["state"][new_id] = state
    if not set(old_ids).issubset(named):
        raise ValueError("Source optimizer contains parameters absent from destination")
    optimizer.load_state_dict(restored)
    return optimizer, groups, {"restored_names": list(old_ids), "new_names": sorted(set(named) - set(old_ids)),
                               "groups": [{"names": names, "lr": g["lr"], "weight_decay": g["weight_decay"]}
                                          for names, g in zip(groups, optimizer.param_groups, strict=True)]}


@torch.no_grad()
def verify_initial(old_actor, actor, batch, channels):
    def raw(net):
        return net.act_features_raw(net.encode_visual(batch["rgb"], batch["depth"], batch["depth_valid"]),
                                    net.encode_text(batch["tokens"]), batch["proprio_history"],
                                    batch["previous_history"], batch["sensor"])
    reference = raw(old_actor)
    candidate = raw(actor)
    scale = torch.tensor([x["scale"] for x in channels], device=candidate.device)
    offset = torch.tensor([x["offset"] for x in channels], device=candidate.device)
    c1, c2 = candidate.clamp(-1, 1), reference.clamp(-1, 1)
    result = {"tested_decisions": len(reference), "max_raw_diff": (candidate-reference).abs().max().item(),
              "max_clipped_diff": (c1-c2).abs().max().item(),
              "max_physical_target_diff": ((offset+scale*c1)-(offset+scale*c2)).abs().max().item(),
              "all_state_tensors_identical": all(torch.equal(v, old_actor.state_dict()[name])
                                                 for name, v in actor.state_dict().items())}
    if not result["all_state_tensors_identical"] or any(result[k] != 0. for k in (
            "max_raw_diff", "max_clipped_diff", "max_physical_target_diff")):
        raise ValueError(f"Parent action function changed on migration: {result}")
    return result


def stage_blocks(stage, round_number, branch, parent):
    if stage == "pilot":
        if (round_number != 0 or branch not in PILOT or parent["schema"] != "M1Piper-Multimodal-v1-actor-v1"
                or parent["update"] != 12000 or "optimizer" not in parent):
            raise ValueError("Pilot requires its registered original full 12000-update parent")
        return branch, 1702, 0, 512, 512
    if branch not in CHAINS or not 1 <= round_number <= 6 or parent["schema"] != SCHEMA:
        raise ValueError("Unregistered main branch, round or parent")
    previous = parent["configuration"]
    if stage == "bc" and not (
        (round_number == 1 and previous["stage"] == "pilot" and parent["update"] == 512)
        or (previous["stage"] == "paired" and previous["round"] == round_number-1
            and previous["branch"] == branch and parent["update"] == 512)
    ):
        raise ValueError("Incorrect longitudinal BC parent")
    if stage == "paired" and (previous["stage"] != "bc" or previous["round"] != round_number
                             or previous["branch"] != branch or parent["update"] != 2048):
        raise ValueError("Paired block requires this branch's current 2048 BC checkpoint")
    return (parent["affine_mode"], 27020+round_number, 0 if stage == "bc" else 2048,
            2048 if stage == "bc" else 512, 2560)


def run(args):
    device = torch.device(args.device)
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    if device.type == "cuda":
        torch.cuda.set_device(device)
        torch.cuda.reset_peak_memory_stats(device)
    old_actor, vocab, parent = load_actor(args.parent, device)
    mode, seed, offset, steps, horizon = stage_blocks(args.stage, args.round, args.branch, parent)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    actor = MultimodalActor(vocab, mode).to(device)
    actor.load_state_dict(parent["actor"], strict=True)
    actor.set_encoder_grad(args.stage == "bc")
    actor.train()
    optimizer, names, migration = restore_optimizer(actor, old_actor, parent)
    old_ids = parent.get("original_train_ids", parent["membership"]["train"])
    members = json.loads(args.members.read_text())
    if not isinstance(members, list):
        raise ValueError("--members must be a JSON list of training episode directories")
    pool = CorrectionPool(args.old_data, old_ids, members, vocab, device)
    if len(old_ids) != 17 or pool.eligible_count["old"] != 35026:
        raise ValueError(f"Original 17-source/35026-label membership changed: {pool.eligible_count}")
    sequence, schedule = pool.schedule(args.schedule, seed, horizon)
    selected = sequence[offset:offset+steps]
    batch_order = hashlib.sha256(selected.tobytes()).hexdigest()
    configuration = {"stage": args.stage, "branch": args.branch, "round": args.round, "affine_mode": mode,
                     "method": METHOD, "parent": str(args.parent.resolve()), "parent_sha256": sha(args.parent),
                     "lr": 1e-4, "steps": steps, "seed": seed, "batch_size": 256,
                     "encoder_trainable": args.stage == "bc", "schedule": str(args.schedule.resolve()),
                     "schedule_slice": [offset, offset+steps], "sequence_sha256": batch_order,
                     "all_batches_sha256": schedule["row_order_sha256"], "membership_signature": pool.membership_signature,
                     "old_label_count": pool.eligible_count["old"], "new_label_count": pool.eligible_count["new"],
                     "h32_bundle": str(args.h32_bundle.resolve()) if args.h32_bundle else None,
                     "h32_bundle_sha256": sha(args.h32_bundle) if args.h32_bundle else None}
    out = args.output
    config_path = out / "configuration.json"
    if config_path.exists() and json.loads(config_path.read_text()) != configuration:
        raise ValueError(f"Training invocation has changed for {out}")
    write_json(config_path, configuration)
    write_json(out / "optimizer_migration.json", migration)
    as_h32 = args.stage == "paired" and args.branch == "model_trajectory"
    if as_h32 != bool(args.h32_bundle):
        raise ValueError("Only the model branch's paired block requires --h32-bundle")
    if (out / "deploy.pt").exists() and (out / "final.pt").exists() and (out / "receipt.json").exists():
        print(json.dumps({"restored_completed_stage": str(out)}), flush=True)
        return
    initial = verify_initial(old_actor, actor, pool.dataset.batch_rows(selected[0]),
                             pool.dataset.episodes[0][1]["action_channels"])
    del old_actor
    if args.stage == "pilot":
        write_json(out / "initial_function.json", initial)
    write_json(out / "normalization_coverage.json", pool.saturation(actor))
    baseline = {n: x.detach().clone() for n, x in actor.state_dict().items()
                if n.startswith(ENCODER_PREFIX) or n == "servo_slope"}
    membership = {"train": pool.ids["old"]+pool.ids["new"], "validation": parent["membership"]["validation"]}
    objective = None
    valid_anchors = 0
    if as_h32:
        from learning.multimodal.mm02_trajectory import RecoveryObjective
        objective = RecoveryObjective(args.h32_bundle, device, vocab, seed=37020+args.round)
        objective.verify_actor(actor)
        valid_anchors = len(objective)
    recover_path = out / "last.pt"
    resume = out / "final.pt" if (out / "final.pt").exists() else recover_path
    start, history, wall_prior = 0, [], 0.
    if resume.exists():
        saved = torch.load(resume, map_location=device, weights_only=False)
        if saved["configuration"] != configuration:
            raise ValueError("Current progress matches a different recipe")
        actor.load_state_dict(saved["actor"])
        optimizer.load_state_dict(saved["optimizer"])
        start, history = saved["update"], saved["updates"]
        wall_prior = saved["training_wall_s"]
        random.setstate(saved["rng"]["python"])
        np.random.set_state(saved["rng"]["numpy"])
        torch.set_rng_state(saved["rng"]["torch"].cpu())
        if device.type == "cuda":
            torch.cuda.set_rng_state(saved["rng"]["cuda"].cpu(), device)
        if valid_anchors:
            objective.load_state_dict(saved["h32_sampler_state"])
    if as_h32 and start == 0:
        diagnosis = (objective.diagnose(actor) if valid_anchors else {"complete_training_anchors": 0,
                     "reason": "no complete current training recovery branch"})
        write_json(out / "trajectory_diagnostic.json", diagnosis)
    step_log = out / "applied_steps.txt"
    existing = sum(1 for _ in step_log.open()) if step_log.exists() else 0
    rollback = existing-start
    if rollback < 0 or rollback > 512:
        raise ValueError(f"Inconsistent Actor application ledger: checkpoint {start}, attempts {existing}")
    old_parameters = [p for n, p in actor.named_parameters() if n != "servo_slope" and p.requires_grad]
    h32_executed = bool(valid_anchors and as_h32)
    records = {}
    synchronize(device)
    begun = time.perf_counter()
    since = 0
    with step_log.open("a", buffering=1) as journal:
        for i in range(start, steps):
            batch = pool.dataset.batch_rows(selected[i])
            action = actor(batch)
            bc = bc_objective(actor, action, batch["action"])
            loss = bc
            values = {"bc": bc.detach()}
            if h32_executed:
                extra, scalars = objective(actor)
                loss = loss + extra
                values["weighted_h32"] = extra.detach()
                values.update({key: torch.as_tensor(val, device=device).detach() for key, val in scalars.items()})
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            values["old_group_gradient_norm"] = torch.nn.utils.clip_grad_norm_(old_parameters, 2.,
                                                                               error_if_nonfinite=True).detach()
            if mode == "adaptive_slope_only":
                values["slope_gradient_norm"] = torch.nn.utils.clip_grad_norm_([actor.servo_slope], 2.,
                                                                                error_if_nonfinite=True).detach()
            optimizer.step()
            journal.write(f"{i+1}\n")
            since += 1
            for key, v in values.items():
                records[key] = records.get(key, 0) + v
            if (i+1) % 64 == 0 or i+1 == steps:
                synchronize(device)
                elapsed = time.perf_counter()-begun+wall_prior
                row = {"step": i+1, "wall_s": elapsed, **{k: float(v/since) for k,v in records.items()}}
                history.append(row)
                print(json.dumps(row, allow_nan=False), flush=True)
                records, since = {}, 0
                saved = {"schema": SCHEMA, "method": METHOD, "affine_mode": mode,
                         "actor": actor.state_dict(), "vocabulary": vocab.tokens, "optimizer": optimizer.state_dict(),
                         "optimizer_names": names, "configuration": configuration, "membership": membership,
                         "data_directories": [str(path) for path, _ in pool.dataset.episodes],
                         "original_train_ids": old_ids, "sampler_state": {"schedule": configuration["schedule"],
                         "schedule_sha256": schedule["row_order_sha256"], "next_row": offset+i+1,
                         "schedule_generator_state": schedule["final_generator_state"]},
                         "rng": {"python": random.getstate(), "numpy": np.random.get_state(),
                                 "torch": torch.get_rng_state(),
                                 "cuda": torch.cuda.get_rng_state(device) if device.type == "cuda" else None},
                         "h32_sampler_state": objective.state_dict() if h32_executed else None,
                         "updates": history, "update": i+1, "training_wall_s": elapsed,
                         "retained_h32_updates": i+1 if h32_executed else 0,
                         "inherited_original_common_steps": 12000,
                         "lineage_new_actor_steps": parent.get("lineage_new_actor_steps", 0)+i+1}
                atomic_save(out / ("final.pt" if i+1 == steps else "last.pt"), saved)
                write_json(out / "progress.json", {"update": i+1, "steps": steps, "rollback": rollback, **row})
    final_path = out / "final.pt"
    encoder_delta_sq = {prefix[:-1]: 0. for prefix in ENCODER_PREFIX}
    for name, value in actor.state_dict().items():
        if name.startswith(ENCODER_PREFIX):
            encoder_delta_sq[name.split(".", 1)[0]] += (value-baseline[name]).double().square().sum().item()
    encoder_delta = sum(encoder_delta_sq.values()) ** .5
    slope_delta = (actor.servo_slope.detach()-baseline["servo_slope"]).cpu().tolist()
    if (args.stage != "bc" and encoder_delta != 0) or (args.stage == "bc" and encoder_delta == 0):
        raise RuntimeError("Observed encoder parameter change disagrees with registered trainable block")
    if mode == "fixed" and any(slope_delta):
        raise RuntimeError("Fixed servo slopes changed")
    deployed = {"schema": SCHEMA, "method": METHOD, "affine_mode": mode, "operation": "inference",
                "actor": actor.state_dict(), "vocabulary": vocab.tokens, "update": steps,
                "configuration": configuration, "source_sha256": sha(final_path)}
    atomic_save(out / "deploy.pt", deployed)
    verify, _, _ = load_actor(out / "deploy.pt", device)
    deployment_check = verify_initial(actor, verify, pool.dataset.batch_rows(selected[-1]),
                                      pool.dataset.episodes[0][1]["action_channels"])
    receipt = {**configuration, "original_parent_common_steps": 12000, "retained_actor": steps,
               "retained_h32_actor": steps if h32_executed else 0,
               "h32_imagined_queries": steps*32*32 if h32_executed else 0,
               "h32_sampling": objective.sampling_summary() if as_h32 else None,
               "total_applied_actor": existing+(steps-start), "rollback_actor": rollback,
               "qualified_complete_h32_anchors": valid_anchors if as_h32 else None,
               "actual_bc_rows": steps*256, "training_wall_s": saved["training_wall_s"], **peak(device),
               "encoder_delta_l2": encoder_delta, "slope_change_23": slope_delta,
               "encoder_component_delta_l2": {name: value**.5 for name, value in encoder_delta_sq.items()},
               "full_checkpoint": str(final_path.resolve()), "full_sha256": deployed["source_sha256"],
               "deployment_sha256": sha(out / "deploy.pt"), "deployment_function_check": deployment_check,
               "lineage_new_actor_steps": saved["lineage_new_actor_steps"]}
    write_json(out / "receipt.json", receipt)
    print(json.dumps(receipt, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("pilot", "bc", "paired"), required=True)
    parser.add_argument("--branch", choices=PILOT+CHAINS, required=True)
    parser.add_argument("--round", type=int, required=True)
    for key in ("members", "schedule", "parent", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--h32-bundle", type=Path)
    parser.add_argument("--old-data", type=Path, default=Path("/root/autodl-tmp/mm01-20261125/data"))
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "training.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        run(args)


if __name__ == "__main__":
    main()
