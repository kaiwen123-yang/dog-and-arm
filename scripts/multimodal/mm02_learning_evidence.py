"""Reconcile the MM-02 training journals, shared row orders, fixed units and bound encoders."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from learning.multimodal.actor import load_actor
from learning.multimodal.correction_sampling import _executors, write_json
from learning.multimodal.mm02_trajectory import encoder_id
from scripts.multimodal.mm02_train_actor import CHAINS, ENCODER_PREFIX, PILOT


STATS = ("proprio_mean", "proprio_std", "action_mean", "action_std", "servo_mean", "residual_std")


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def applications(path):
    with Path(path).open() as stream:
        return sum(1 for _ in stream)


def normalized_coverage(data):
    out = {}
    for pool, v in data.items():
        out[pool] = {**v}
        for numerator, denom in (("proprio_clipped", "proprio_values"), ("previous_clipped", "previous_values"),
                                  ("expert_at_action_bound", "expert_values")):
            n = v.get(denom, 0)
            out[pool][numerator+"_fraction"] = v.get(numerator, 0)/n if n else None
    return out


def actor_evidence(path, original, totals, times):
    r = read(path/"receipt.json")
    actor, _, package = load_actor(path/"final.pt", "cpu")
    if (sha(path/"final.pt") != r["full_sha256"] or sha(path/"deploy.pt") != r["deployment_sha256"]
            or sha(r["parent"]) != r["parent_sha256"]):
        raise ValueError(f"Checkpoint provenance changed at {path}")
    updates = applications(path/"applied_steps.txt")
    if (r["total_applied_actor"] != updates or r["retained_actor"] != package["update"]
            or updates-package["update"] != r["rollback_actor"]):
        raise ValueError(f"Actor accounting disagrees at {path}")
    if any(not torch.equal(package["actor"][name], original[name]) for name in STATS):
        raise ValueError(f"MM-01 actor normalization changed at {path}")
    a, b = r["schedule_slice"]
    mat = np.load(r["schedule"], mmap_mode="r", allow_pickle=False)
    if (hashlib.sha256(mat[a:b].tobytes()).hexdigest() != r["sequence_sha256"]
            or [b-a, mat.shape[1]] != [r["retained_actor"], 256]):
        raise ValueError(f"Archived BC row sequence disagrees at {path}")
    totals["actor_actual"] += updates
    totals["actor_retained"] += r["retained_actor"]
    totals["actor_rollback"] += r["rollback_actor"]
    totals["bc_rows_retained"] += r["actual_bc_rows"]
    totals["bc_rows_applied"] += updates*256
    totals["h32_actor_retained"] += r["retained_h32_actor"]
    totals["h32_queries_retained"] += r["h32_imagined_queries"]
    if r["retained_h32_actor"]:
        if r["h32_imagined_queries"] != 32*package["h32_sampler_state"]["drawn"]:
            raise ValueError(f"H32 actual sampling count differs from policy query count at {path}")
        totals["h32_actor_applied"] += updates
        totals["h32_queries_applied"] += updates*32*32
    key = "pilot" if r["stage"] == "pilot" else r["branch"]+"_"+r["stage"]
    times[key] += r["training_wall_s"]
    optimizer_steps = {}
    for group, names in zip(package["optimizer"]["param_groups"], package["optimizer_names"], strict=True):
        for pid, name in zip(group["params"], names, strict=True):
            kind = "slope" if name == "servo_slope" else ("encoder" if name.startswith(ENCODER_PREFIX) else "policy")
            optimizer_steps.setdefault(kind, set()).add(int(package["optimizer"]["state"][pid]["step"]))
    details = {key: r[key] for key in ("affine_mode", "stage", "branch", "round", "parent_sha256",
        "full_sha256", "deployment_sha256", "retained_actor", "rollback_actor", "retained_h32_actor",
        "h32_imagined_queries", "qualified_complete_h32_anchors", "sequence_sha256", "membership_signature",
        "schedule_slice", "actual_bc_rows", "training_wall_s", "encoder_delta_l2", "slope_change_23",
        "lineage_new_actor_steps", "deployment_function_check")}
    details.update(training_checkpoint=str(path/"final.pt"), deployment=str(path/"deploy.pt"),
                   optimizer_components_steps={k: sorted(v) for k,v in optimizer_steps.items()},
                   h32_sampling=r.get("h32_sampling"), encoder_component_delta_l2=r.get("encoder_component_delta_l2"),
                   registered_rates=read(path/"optimizer_migration.json")["groups"],
                   first_monitor=package["updates"][0], last_monitor=package["updates"][-1],
                   normalization_unchanged=list(STATS), encoder_id=encoder_id(actor))
    details["registered_rates"] = [{k:v for k,v in group.items() if k!="names"} | {"tensors":len(group["names"])}
                                   for group in details["registered_rates"]]
    return details, actor


def model_difference(a, b):
    values = {name: {"max_abs": 0., "squared_l2": 0., "elements": 0}
              for name in ("encoder", "slope", "remaining_network")}
    paired = b.state_dict()
    for name, shape in a.state_dict().items():
        if name in STATS or name in ("clock_rates", "numeric_tokens"):
            continue
        group = "slope" if name == "servo_slope" else ("encoder" if name.startswith(ENCODER_PREFIX) else "remaining_network")
        delta = (shape-paired[name]).double()
        values[group]["max_abs"] = max(values[group]["max_abs"], float(delta.abs().max()))
        values[group]["squared_l2"] += float(delta.square().sum())
        values[group]["elements"] += delta.numel()
    for row in values.values():
        row["l2"] = row.pop("squared_l2")**.5
    return values


def schedule_evidence(path):
    info = read(path.with_suffix(".json"))
    matrix = np.load(path,mmap_mode="r",allow_pickle=False)
    last = max(member["row_start"]+member["num_actions"] for member in info["episodes"])
    draws = np.bincount(matrix.ravel(),minlength=last)
    pooled = {}
    present = {"old":{}, "new":{}}
    for member in info["episodes"]:
        row = pooled.setdefault(member["pool"], {"members":0,"empty_label_members":[],
            "expert_queries":0,"draws":0,"eligible_labels_per_teacher_phase":Counter(),
            "eligible_by_behavior":Counter(),"sampled_per_teacher_phase":Counter(),
            "sampled_by_behavior":Counter(),"qualified_partial_terminal_queries":0})
        row["members"] += 1
        row["expert_queries"] += member["qualified_labels"]
        row["draws"] += member["actual_draws"]
        if not member["qualified_labels"]:
            row["empty_label_members"].append(member["episode_id"])
        row["eligible_labels_per_teacher_phase"].update(member["qualified_teacher_phases"])
        row["eligible_by_behavior"].update(member["qualified_executor_strata"])
        source_dir = Path(member["directory"])
        meta = read(source_dir/"metadata.json")
        phase = np.load(source_dir/"phase.npy",allow_pickle=False)
        count = draws[member["row_start"]:member["row_start"]+member["num_actions"]]
        task = f'{member["scene"]}/{member["side"]}/{member["target_deg"]}'
        qualified = present[member["pool"]].setdefault(task,set())
        qualified.update(s for s,n in member["qualified_executor_strata"].items() if n)
        for idx in np.unique(phase):
            row["sampled_per_teacher_phase"][meta["phases"][int(idx)]] += int(count[phase==idx].sum())
        if member["pool"] == "new":
            ex = _executors(source_dir,len(phase))
            eligible = np.load(source_dir/"expert_label_valid.npy",allow_pickle=False).astype(bool)
            complete = np.load(source_dir/"valid_transition.npy",allow_pickle=False).astype(bool)
            row["qualified_partial_terminal_queries"] += int((eligible & ~complete).sum())
            for label in member["qualified_executor_strata"]:
                actual_executor = label.rsplit("/",1)[-1]
                row["sampled_by_behavior"][label] += int(count[ex==actual_executor].sum())
        else:
            row["sampled_by_behavior"][meta["source"]] += int(count.sum())
    missing = {}
    for pool, tasks in present.items():
        all_sources = set().union(*tasks.values())
        missing[pool] = {task: sorted(all_sources-available) for task,available in tasks.items()
                         if all_sources-available}
        if pool in pooled and sum(pooled[pool]["sampled_by_behavior"].values()) != pooled[pool]["draws"]:
            raise ValueError(f"Actual sample source counts disagree in {path}, pool {pool}")
    reference_phases = set(pooled.get("old", {}).get("eligible_labels_per_teacher_phase", {}))
    for value in pooled.values():
        value["absent_teacher_phases_relative_to_old_demos"] = sorted(
            reference_phases-set(value["eligible_labels_per_teacher_phase"]))
    return {"path": str(path), "shape": [info["updates"], info["batch_size"]], "seed": info["seed"],
            "row_order_sha256": info["row_order_sha256"], "membership_signature": info["membership_signature"],
            "pools":pooled, "empty_pool_fallback":info["empty_pool_fallback"], "missing_tasks":info["missing_tasks"],
            "behavior_strata_absent_within_task":missing}


def dynamics_evidence(out, round_num, terminal, after_bc, totals, times):
    wm, bridge, val = [read(out/name) for name in ("wm_training.json", "bridge_training.json", "wm_validation.json")]
    for key, prefix, record in (("wm", "round", wm), ("bridge", "bridge", bridge)):
        actual = applications(out/(key+"_applied_steps.txt"))
        kept = record[prefix+"_retained_updates"]
        discarded = record[prefix+"_rollback_updates"]
        if actual != record[prefix+"_applied_updates"] or actual != kept+discarded:
            raise ValueError(f"{key} application log disagrees in round {round_num}")
        totals[key+"_actual"] += actual
        totals[key+"_retained"] += kept
        totals[key+"_rollback"] += discarded
        times[key] += record["train_wall_s"]
    if not (bridge["encoder_id"] == encoder_id(terminal) == after_bc["encoder_id"]):
        raise ValueError(f"Bridge, post-2048 and paired terminal encoding differ in round {round_num}")
    if sha(bridge["actor_after_2048_bc"]) != after_bc["full_sha256"] or wm["checkpoint"] != bridge["parent_wm"]:
        raise ValueError(f"Actor/WM identity mismatch in bridge binding, round {round_num}")
    if val["fit_on_validation"] or sha(val["frozen_evaluated_actor"]) != sha(out.parent/CHAINS[1]/"paired/final.pt"):
        raise ValueError(f"Independent prediction validation actor mismatch in round {round_num}")
    result = {key:wm[key] for key in ("initial_cumulative_updates","final_cumulative_updates","round_retained_updates",
        "round_applied_updates","round_rollback_updates","legal_windows","contact_start_windows","fixed_units_restored",
        "normalization_coverage","train_wall_s","peak_allocated_MiB","action_source","early_history")}
    result.update(wm_training_path=str(out/"wm_training.json"), wm_full=str(out/"wm.pt"),
                  inherited_physical_members=len(wm["inherited_mm01_physical_episodes"]))
    result["bridge"] = {key:bridge[key] for key in ("parent_wm","actor_after_2048_bc","encoder_id","bundle",
        "initialization","bridge_retained_updates","bridge_applied_updates","bridge_rollback_updates","batch","objective",
        "train_wall_s","errors")}
    result["bridge"]["binding_verified_on_both_checkpoints"] = True
    result["prediction_validation"] = {}
    for name, group in val["strata"].items():
        horizons = group["horizons"]
        result["prediction_validation"][name] = {"episodes":len(group["episodes"]), "horizons": horizons}
        totals["validation_student_imagined_queries"] += sum(int(h)*v["windows"] for h,v in horizons.items())
    return result


def summarize(run, last_round, partial):
    torch.set_num_threads(1)
    result = {"method":"M1Piper-Multimodal-DAggerWM-v2","partial":partial, "run":str(run),
        "timing":"sum of synchronized optimizer block wall times; concurrent blocks overlap in elapsed time",
        "inherited_not_charged":{"actor_common":12000,"wm":2800,"bc_demo_members":17,
            "eligible_bc_rows":35026, "original_wm_physical_members":21,
            "original_wm_valid_transitions":44230, "copied_old_bridge_updates":0},
        "pilot":{}, "rounds":[]}
    totals = Counter({k:0 for k in ("actor_actual","actor_retained","actor_rollback","h32_actor_retained",
        "h32_actor_applied","h32_queries_retained","h32_queries_applied","bc_rows_retained","bc_rows_applied",
        "h32_diagnostic_queries","validation_student_imagined_queries","wm_actual","wm_retained","wm_rollback",
        "bridge_actual","bridge_retained","bridge_rollback","critic_actual","critic_retained","critic_rollback")})
    times = Counter()
    original_path = Path(read(run/"pilot/fixed/receipt.json")["parent"])
    original = torch.load(original_path,map_location="cpu",weights_only=False)["actor"]
    result["inherited_not_charged"].update(original_actor=str(original_path),original_actor_sha256=sha(original_path))
    for variant in PILOT:
        directory = run/"pilot"/variant
        item, _ = actor_evidence(directory, original, totals, times)
        item["initial_equivalence"] = read(directory/"initial_function.json")
        result["pilot"][variant] = item
    result["pilot"]["schedule"] = schedule_evidence(run/"pilot/schedule.npy")
    result["pilot"]["normalization"] = normalized_coverage(read(run/"pilot/fixed/normalization_coverage.json"))
    pilot_selection = run/"pilot/selection.json"
    if pilot_selection.is_file():
        result["pilot"]["physical_selection"] = read(pilot_selection)
    causal_check = run/"round1/actor_causal_restore_check.json"
    if causal_check.is_file():
        result["recovered_actor_inputs_compared_with_online"] = read(causal_check)
    prev = {}
    for n in range(1,last_round+1):
        directory = run/f"round{n}"
        if partial and not (directory/"dynamics/wm_validation.json").is_file():
            break
        data = {"round":n, "schedule":schedule_evidence(directory/"schedule.npy"),
                "normalization":normalized_coverage(read(directory/CHAINS[0]/"bc/normalization_coverage.json")),
                "branches":{k:{} for k in CHAINS}, "matched":{}}
        for stage in ("bc","paired"):
            net = {}
            for branch in CHAINS:
                entry, net[branch] = actor_evidence(directory/branch/stage, original, totals, times)
                if stage == "bc" and n == 1:
                    expected = result["pilot"][result["pilot"]["physical_selection"]["chosen"]]["full_sha256"]
                else:
                    expected = prev[branch] if stage=="bc" else data["branches"][branch]["bc"]["full_sha256"]
                if expected != entry["parent_sha256"]:
                    raise ValueError(f"Wrong ancestor for {branch}/{n}/{stage}")
                data["branches"][branch][stage] = entry
            x, y = (data["branches"][branch][stage] for branch in CHAINS)
            if (x["membership_signature"] != y["membership_signature"] or x["sequence_sha256"] != y["sequence_sha256"]
                    or x["retained_actor"] != y["retained_actor"]):
                raise ValueError(f"Unequal supervised row order, membership or budget in {stage}/{n}")
            data["matched"][stage] = {"same_rows_membership_and_actor_updates":True,
                "same_parent_weights":x["parent_sha256"] == y["parent_sha256"],
                "parameter_difference":model_difference(net[CHAINS[0]], net[CHAINS[1]])}
        prev = {b:data["branches"][b]["paired"]["full_sha256"] for b in CHAINS}
        data["dynamics"] = dynamics_evidence(directory/"dynamics",n,net[CHAINS[1]],data["branches"][CHAINS[1]]["bc"],
                                             totals,times)
        diagnosis = read(directory/CHAINS[1]/"paired/trajectory_diagnostic.json")
        data["first_h32_batch"] = {k:v for k,v in diagnosis.items() if k not in ("same_first_batch_indices","first_anchor_keys")}
        if diagnosis.get("complete_anchors", 0):
            extra = diagnosis.get("frozen_directional_derivative")
            calls = 1 + (1 + 2*len(extra["centered"]) if extra is not None else 0)
            totals["h32_diagnostic_queries"] += calls*32*32
        result["rounds"].append(data)
    totals["h32_actor_rollback"] = totals["h32_actor_applied"]-totals["h32_actor_retained"]
    totals["h32_queries_rollback"] = totals["h32_queries_applied"]-totals["h32_queries_retained"]
    result["actual_budget"] = dict(totals)
    result["optimizer_block_wall_s"] = dict(times)
    result["optimizer_block_wall_sum_s"] = sum(times.values())
    result["completed_rounds"] = len(result["rounds"])
    if not partial:
        if totals["actor_retained"] != 1024+5120*last_round or totals["wm_retained"] != 1000*last_round or totals["bridge_retained"] != 600*last_round:
            raise ValueError("Terminal retained totals disagree with the actual registered experiment length")
        if totals["actor_rollback"] > 512 or totals["wm_rollback"] > 200 or totals["bridge_rollback"] > 120:
            raise ValueError("Applied rollback exceeds its registered reserve")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--partial", action="store_true",
                        help="Report only completed rounds before the terminal decision.")
    args = parser.parse_args()
    if args.partial:
        rounds = 6
    else:
        rounds = read(args.run/"terminal_freeze.json")["round"]
    evidence = summarize(args.run,rounds,args.partial)
    destination = args.out or args.run/"learning_evidence.json"
    write_json(destination, evidence)
    print(json.dumps({"report":str(destination),"rounds":evidence["completed_rounds"],**evidence["actual_budget"]}))
