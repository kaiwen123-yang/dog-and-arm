"""Summarize measured temporal WM budgets and the frozen u0 physical control."""
import csv
import json
from pathlib import Path

import numpy as np


OUT = Path("results/b0/standard_temporal_20261124")
BASE = OUT.parent
FIELD = Path("/root/autodl-tmp/dog-and-arm-b0-temporal-v1")


def read(path):
    return json.loads(path.read_text())


def budget(arm, sources, start_indices, source_ids):
    rows = [json.loads(s) for s in (OUT/f"{arm}_training.jsonl").read_text().splitlines()]
    if [r["k"] for r in rows] != list(range(1, 1001)):
        raise ValueError(f"Incomplete or repeated real steps, {arm}")
    horizons = np.array([r["h"] for r in rows])
    assert np.array_equal(horizons, np.where(np.arange(1000) % 10 < 2, 1, 7))
    counts = {}
    for h in (1, 7):
        matches = source_ids[horizons == h]
        counts[h] = {name:int(np.count_nonzero(matches == i)) for i,name in enumerate(sources)}
        assert sum(counts[h].values()) == int((horizons == h).sum()) * 256
    assert start_indices.shape == source_ids.shape == (1000,256) and start_indices.min() >= 0
    goals = int(256*horizons.sum())
    times = {i: max(r["elapsed_s"] for r in rows if r["process_start_at"] == i) for i in (0,50,200)}
    return dict(h1=200,h7=800,batch=256,total_windows=256000,source_draws=counts,
        stored_positions=goals+256000,supervised_successors=goals,
        net_forward_examples=goals*(10 if arm=="T2" else 1),
        training_loop_seconds_by_restart=times,training_loop_seconds=sum(times.values()),
        timing_scope="shared GPU; after loading data, weights and optimizers, excluding final save and validation",
        peak_allocated_bytes=max(r["peak_allocated_bytes"] for r in rows),
        peak_reserved_bytes=max(r["peak_reserved_bytes"] for r in rows),
        clip_norm=1.,clipped_batches=sum(r["grad_norm"]>1 for r in rows),
        nonfinite_batches=sum(not np.isfinite([r["grad_norm"],*r["losses"].values()]).all() for r in rows),
        checkpoints=[str(FIELD/"results/raw_large/b0/temporal_pair_v1"/arm/f"wm_{s:06}.pt") for s in (0,50,200,1000)])


def anchor():
    rows=[]
    for tag in ("v1","hold_margin_v2"):
        root=BASE/f"temporal_anchor_u0_warp_{tag}"
        previous=BASE/f"response_s0_v1_u0_warp_{tag}"
        for f in sorted(root.glob("*/*/nominal/result.json")):
            j,r,old=read(f),read(f.with_name("return.json")),read(previous/f.relative_to(root))
            fail=j["first_failure"]
            rows.append(dict(side=j["side"],segment=j["segment"],case="nominal",protocol=tag,
                passed=j["passed"],first_failure=fail["reason"],failure_tick=fail["first_failure_substep"],
                first_failure_net_force_n=fail["door_net_force_n"],peak_net_force_n=j["measured_peak_net_force_n"],
                events=len(j["events"]),prefix_steps=j["prefix_physics_steps"],
                physics_steps=j["physics_steps"],wall_s=j["physical_wall_seconds"],
                fixed_effort=r["normalized_fixed_effort"],planned_s=r["planned_duration_s"],
                executed_steps=r["executed_substeps"],absorbed_steps=r["absorbed_substeps"],
                historical_u0_failure_tick=old["first_failure"]["first_failure_substep"],
                historical_u0_failure=old["first_failure"]["reason"],source=str(f)))
    assert len({(r['side'],r['segment']) for r in rows}) == len(rows) == 10
    with (OUT/"anchor_nominal.csv").open("w") as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return dict(frozen="results/b0/response_s0_v1/checkpoint_000000.pt",cases=len(rows),
        passed=sum(r["passed"] for r in rows),first_2ms_overforce=sum(r["failure_tick"]==1 and r["first_failure"]=="door_force_limit" for r in rows),
        events=sum(r["events"] for r in rows),policy_physics_substeps=sum(r["physics_steps"] for r in rows),
        prefix_substeps=sum(r["prefix_steps"] for r in rows),sum_case_wall_s=sum(r["wall_s"] for r in rows),
        source="anchor_nominal.csv",identity="new single-world Warp formal rerun of archived u0, zero new Actor updates")


def main():
    old=read(BASE/"standard_response_20261124/baseline_manifest.json")
    sources=read(OUT/"paired_sources.json")
    with np.load(OUT/"paired_indices.npz") as d:
        costs={arm:budget(arm,sources["names"],d["start"],d["source"]) for arm in ("C20","T2")}
    costs["total_network_forward_examples"]=sum(cost["net_forward_examples"] for cost in costs.values())
    costs["total_supervised_successors_counted_per_arm"]=sum(costs[a]["supervised_successors"] for a in ("C20","T2"))
    m=dict(method=old["method"],stage="B0-04",final_candidate=None,selected_wm=None,
        full_bilateral_return=None,standard_transfer_complete=False,goal=old["goal"],near=old["near"],
        plan_commit="b5831d747289cb5e302151214759f3add26c7700",
        sealed_previous="753f1bcca6d4f5dd48b1b2886e3523036c7d366d",
        implementation="b806b96905b01d260a6a152f732f372255b46c7b",upstream=old["upstream"],
        field_root=str(FIELD),device=old["device"],config="config/b0/standard_temporal_v1.yaml",
        challenge_plan="docs/B0_TEMPORAL_COMPATIBILITY_PLAN_20261124.md",
        physical=dict(backend="MuJoCo-Warp 3.16.0, Warp 1.18.0",dt_s=.002,policy_dt_s=.020,
            score="fixed_effort_successor_2ms_v1",door_force_limit_N=6,
            contact_cases=["config/b0/contact_dev_v1.json","config/b0/contact_dev_hold_margin_v2.json"],
            references="config/b0/standard_response_v1.yaml and its inherited held reference paths",
            full_protocol="docs/B0_PAPER_BASELINE_PROTOCOL.md"),
        registered_source="registration.json",new_response=read(OUT/"solver_source_qualification.json")["physical_recollection"],
        source_trajectories=dict(train=4,validation=2),starts=dict(train=12,validation=6),
        legal_window_inventory=sources["legal_windows"],raw_response=str(FIELD/"results/raw_large/b0/temporal_entries_v1"),
        independent_response="solver_fixed_closure/temporal_closure.json",solver_before="solver_before.json",solver_retest="solver_retest.json",
        inherited=old["inherited"],previous_unselected_warm=old["added_warm"],previous_joint=old["joint_total"],
        previous_recovery=old["recovery"],initializer="results/b0/response_wm_v1/wm_000000.pt",
        initialization="identical initialization tensors and fixed statistics, fresh official Muon + Adam for each arm",
        numerical_adaptation="T2 uses independent 2ms inner Dynamics, c=1, sustained 0.1 over all 31 increment channels, ten autoregressive calls per 20ms action; C20 uses c=0.55",
        paired_indices="paired_indices.npz",paired_sources="paired_sources.json",wm_budget=costs,
        process_timing="process_timing.json",wm_nodes="wm_validation/node_summary.json",selection="None of the eight nodes combines bilateral response, retained long validation and consistent internal path.",
        new_h32_updates=0,new_joint_critic_batches=0,new_online_actor_training_intervals=0,formal_anchor=anchor(),
        no_new_candidate_cases=True,not_reached=["new seed0 H32 main chain","D","full Warp nominal/C","full native3.3 nominal","seed1/2","frozen H"],
        timing_note="Counts of internal forwards are individual batch examples, exclude reverse operations, scoring and diagnostics. Historical budgets remain separate.",
        protocol_deviation=dict(arm="T2",at=200,late_discovery="H7 interval preclip p95=8.68e6, max=6.07e8; the endpoint decision inspected finite forward metrics and last gradient, missing intermediate spikes.",
            extra_completed_wm_batches=800,extra_internal_forward_examples=11878400,included_in_total=True,
            disposition="Post-hoc diagnostic evidence, excluded from candidate promotion. Added per-interval gradient receipts and rechecked the +200 checkpoint."),
        evidence=dict(actor="historical_u1_actor.json",old_u1_loss="wm_validation/historical_u1_loss.json",
            original_loss_retest="wm_validation/paired_source_loss.json",
            backward_retest="wm_validation/recurrence_u200.json",
            backend_retests=["nonterminal_wrist_replay_3.3.0.json","nonterminal_wrist_replay_3.16.0.json"],
            fixed_statistics="wm_validation/input_support.json",
            native_sample_saturation="native_wrist_draws_3.16.0.json",
            servo="hold_actuation_audit.json",actual_draws="hold_actual_draws.csv",video="hold_videos.json"),
        report="reports/B0_TEMPORAL_TRANSFER_RESULTS_20261124.md")
    (OUT/"baseline_manifest.json").write_text(json.dumps(m,indent=2,allow_nan=False)+"\n")


if __name__ == "__main__":
    main()
