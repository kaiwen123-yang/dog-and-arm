"""Reconcile completed contact runs with their source receipts, replay clocks and sampler states."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.representations import NUM_GOAL_FRAMES, GOAL_FRAME_STRIDE


def read_json(path):
    return json.loads(path.read_text())


def motion_exposure(directory):
    actual = read_json(directory/"actual_config.json")
    cfg = actual["cfg"]
    paths = [Path(cfg["reference_directory"])/name for name in cfg["references"]]
    lengths = [1 + int(np.load(path/"valid_full_interval.npy").sum()) for path in paths]
    ends = torch.tensor(np.cumsum(lengths))
    start = 0
    eligible = []
    for path, length in zip(paths, lengths, strict=True):
        meta = read_json(path/"metadata.json")
        phase = np.load(path/"substeps/phase.npy")[:10*(length-1):10]
        clock = np.arange(length-1)
        legal = np.isin(np.asarray(meta["phases"])[phase],cfg["rsi_phases"]) & (clock>=11) & (
                       clock<length-1-33-cfg["cohort_steps"])
        eligible.append(torch.as_tensor(clock[legal])+start)
        start += length
    ckpt = torch.load(directory/"cohort_state.pt",mmap=True,weights_only=False,map_location="cpu")
    sampler = ckpt.get("return_sampler_state")
    global_bins = int(int(ends[-1])//(.2/cfg["policy_dt"]))+1
    edges = torch.arange(global_bins+1)*(ends[-1]-2)//global_bins
    def projected(probs):
        mass = []
        for e in eligible:
            b = torch.bucketize(e, edges[1:], right=True)
            mass.append((probs[b]/edges.diff()[b]).sum())
        mass = torch.stack(mass)
        return (mass/mass.sum()).tolist()
    prior = projected(torch.ones(global_bins))
    final = projected(sampler["probabilities"]) if sampler else None

    f = directory/"cohorts.jsonl"
    rows = [json.loads(s) for s in (f if f.exists() else directory/"updates.jsonl").read_text().splitlines()]
    names = cfg["references"]
    starts = np.sum([r["starts_per_motion"] for r in rows],axis=0)
    included = {}
    measured = np.zeros((len(names),4),dtype=np.int64)
    def observe(k, frames, valid, term, source):
        motion = torch.searchsorted(ends,frames[:,0].contiguous(),right=True)
        fail = (valid & term).any(1)
        survived = valid.sum(1).eq(cfg["cohort_steps"]) & ~fail
        observed = torch.stack([torch.bincount(motion,weights=weights.double(),minlength=len(names)).long()
                                for weights in (torch.ones_like(motion),valid.sum(1),fail,survived)],dim=1).numpy()
        row = rows[k-1]
        if (not np.array_equal(observed[:,0],row["starts_per_motion"]) or observed[:,1].sum()!=row["valid_transitions"]
                or observed[:,2].sum()!=row["failed_lanes"] or observed[:,3].sum()+observed[:,2].sum()!=len(motion)):
            raise ValueError(f"{directory} cohort {k}: unresolved terminals or counts disagree with physical ledger")
        if k in included:
            if not np.array_equal(included[k][0],observed):
                raise ValueError(f"Raw and replay disagree in cohort {k}")
            included[k][1].append(source)
        else:
            measured[:] += observed
            included[k]=(observed,[source])

    kept = [i for i,row in enumerate(rows,1) if row["valid_transitions"]][-len(ckpt["replay"]):]
    for k,(data,idx) in zip(kept,ckpt["replay"], strict=True):
        valid = torch.zeros_like(data["terminated"])
        i,t = idx[1].unbind(-1)
        valid[i,t] = True
        observe(k,data["motion_time"],valid,data["terminated"],"final_replay")
    raw = Path("results/raw_large/b0")/directory.name
    for folder in sorted(raw.glob("cohort_*")):
        k = int(folder.name.split("_")[-1])
        def read(key):
            return torch.from_numpy(np.load(folder/(key+".npy"))).T
        observe(k,read("frame"),read("valid"),read("first_fail_substep")>0,"raw")
    full_fail = sum(r["failed_lanes"] for r in rows)
    invalid = sum(r["prefix_invalid"] for r in rows)
    cols = ("starts","valid_20ms_transitions","terminated_lanes","survived_to_40_lanes")
    by_motion = {}
    for i, name in enumerate(names):
        subset = dict(zip(cols,measured[i].tolist(), strict=True))
        subset["termination_fraction"] = subset["terminated_lanes"]/subset["starts"]
        by_motion[name] = dict(eligible_starts=len(eligible[i]),total_starts=int(starts[i]),
                observed_reset_fraction=float(starts[i]/starts.sum()),initial_mask_conditioned_return_prior=prior[i],
                final_mask_conditioned_return_probability=final[i] if final else None,retained_cohorts=subset)
    return dict(run=directory.name,all_physical_cohorts=len(rows),all_starts=int(starts.sum()),
                all_valid_20ms=sum(r["valid_transitions"] for r in rows),all_failed_lanes=full_fail,
                all_prefix_invalid=invalid,all_survived_to_40=int(starts.sum())-full_fail-invalid,
                retained_cohort_ids=sorted(included),retained_sources={k:v[1] for k,v in sorted(included.items())},
                retained_starts=int(measured[:,0].sum()),by_motion=by_motion)


def load_run(directory):
    spec = read_json(directory / "actual_config.json")
    cfg = spec["cfg"]
    outcome = read_json(directory / "outcome.json")
    ckpt = torch.load(directory / "cohort_state.pt", mmap=True, weights_only=False, map_location="cpu")
    rows = [json.loads(line) for line in (directory / "updates.jsonl").read_text().splitlines()]
    endpoint = spec["requested_endpoint"]
    if ([r["update"] for r in rows] != list(range(1, endpoint + 1))
          or endpoint != outcome["actor_updates"] or endpoint != ckpt["updates"]):
        raise ValueError(f"Incomplete or resumed update sequence: {directory}")
    logs = directory / "cohorts.jsonl"
    cohorts = [json.loads(line) for line in logs.read_text().splitlines()] if logs.is_file() else rows
    valid = sum(r["valid_transitions"] for r in cohorts)
    attempted = sum(r["simulated_lane_intervals"] for r in cohorts)
    if not (valid == outcome["valid_online_transitions"] == ckpt["collected"]
            and attempted == outcome["simulated_lane_intervals"] == ckpt["simulated"]):
        raise ValueError("Mismatch between rollout receipts and state")
    schedule = ckpt.get("ratio_state")
    if schedule and (len(cohorts) != schedule["cohorts"] or
                     sum(r["due"] for r in cohorts) != len(rows) + schedule["pending"]):
        raise ValueError("Unaccounted update repeats")
    state = ckpt["return_sampler_state"]
    if not torch.isclose(state["probabilities"].sum(),torch.tensor(1.)):
        raise ValueError("Invalid final reset distribution")
    cfg_path = next(path for path in spec["execution_source_sha256"] if path.startswith("config/"))
    checked = {}
    for path, at_runtime in spec["execution_source_sha256"].items():
        if path in {cfg_path, "learning/b0/contact_training.py", "learning/b0/contact_warp.py",
                    "learning/b0/contact_sampling.py", "learning/b0/contact_policy.py", "scripts/b0/train_contact.py"}:
            checked[path] = dict(runtime_sha256=at_runtime, matches_audit_checkout=(
                                  hashlib.sha256(Path(path).read_bytes()).hexdigest() == at_runtime))
    code = Path(".local-pair") / (directory.name + ".exit")
    exit_status = int(code.read_text()) if code.exists() else None
    def total(key):
        return sum(r[key] for r in rows)
    stats = dict(online_positions=total("wm_online_stored_positions"),
                 offline_positions=total("wm_offline_stored_positions"),
                 online_targets=total("wm_online_successor_targets"), offline_targets=total("wm_offline_successor_targets"),
                 imagined_policy_steps=total("imagined_policy_steps"))
    stats["stored_positions_per_valid_insertion"] = (stats["online_positions"]+stats["offline_positions"])/valid
    starts = [sum(r["starts_per_motion"][k] for r in cohorts) for k in range(len(cfg["references"]))]
    source = Path(cfg["reference_directory"])
    ends = torch.tensor(np.cumsum([1+int(np.load(source/name/"valid_full_interval.npy").sum())
                                   for name in cfg["references"]]))
    tail_offset = (NUM_GOAL_FRAMES - 1) * GOAL_FRAME_STRIDE
    retained, physical_tail, possible_imagined = 0, 0, 0
    for data, indices in ckpt["replay"]:
        lanes, t = indices[1].unbind(1)
        frame = data["motion_time"][lanes, t]
        end = ends[torch.searchsorted(ends, frame, right=True)]
        retained += len(frame)
        physical_tail += int((frame + tail_offset >= end).sum())
        possible_imagined += int((frame + cfg["actor_horizon"] - 1 + tail_offset >= end).sum())
    return dict(run=directory.name, config=cfg_path, requested_endpoint=endpoint, exit_code=exit_status,
                receipt=str(code), restart_file=str(directory/"cohort_state.pt"),
                command=f"bash scripts/b0/env.sh python scripts/b0/train_contact.py --config {cfg_path} --updates {endpoint} --run {directory.name}",
                contact_reset_sampling=cfg["contact_reset_sampling"],
                schedule=cfg.get("contact_update_schedule","one_per_cohort"),reference_tail=cfg.get("reference_tail","zero"),
                valid_insertions=valid,attempted_intervals=attempted,physical_cohorts=len(cohorts),
                offline_online_and_imagination=stats,ratio_checkpoint=schedule,
                due_counts_per_cohort={str(v):sum(r.get("due",1)==v for r in cohorts)
                                       for v in sorted(set(r.get("due",1) for r in cohorts))},
                physical_prefix_substeps_executed=sum(sum(r["starts_per_motion"])*r["prefix_steps_per_lane"] for r in cohorts),
                sampler_bins_measured=int((state["count"]>0).sum()), sampler_bins_total=len(state["count"]),
                sampler_updates_buffered_steps=state["_step"],references=cfg["references"],starts_per_reference=starts,
                final_replay_tail_exposure=dict(retained_valid_rows=retained,observed_frame_with_tail=physical_tail,
                    rows_with_tail_reachable_within_H32=possible_imagined,
                    latter_count="potential given a start row, not a count of actually sampled imagined starts"),
                actor_updates=endpoint,wm_minibatches=outcome["wm_minibatches"],critic_minibatches=outcome["critic_minibatches"],
                elapsed_process_s=outcome["elapsed_process_s"],started_unix=outcome["started_unix"],
                finished_unix=outcome["finished_unix"],source_receipts=checked)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="Completed fresh runs with complete update logs")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--motion-exposure",action="store_true",
                        help="Compare all reset counts and per-reference outcomes on unique retained cohorts")
    args = parser.parse_args()
    if args.motion_exposure:
        result = dict(runs=[motion_exposure(d) for d in args.runs],split="training diagnostic",
                      population="all reset draws in u1..u50 cohorts; all reported prefix and physical termination totals",
                      per_motion_outcomes="unique raw cohorts plus final 32 replay cohorts, compared on overlaps; other cohorts have no retained per-motion termination breakdown",
                      prior="uniform external bins on global timeline, conditioned on exactly the legal frame support",
                      success_scope="surviving 40 x 20ms collection horizon, not formal case success")
    else:
        result = dict(runs=[load_run(d) for d in args.runs],shared_gpu=True,physical_reference_timing="20ms with 2ms early terminal for RSI",
                      wm_ratio_denominator="full numeric replay-eligible contact lane intervals",
                      bins="pinned global 0.2s bins; illegal reset support removed at sampling")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(result, out, indent=2)
        out.write("\n")
