"""Index measured windows, training cost, actual u1 gradients and frozen contact scores."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import subprocess

import numpy as np
import torch

from scripts.b0.training_entry_response import OUT, RAW, BASE
from scripts.b0.index_lane_round import block_counts, read, lines


def table(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def gradient_groups():
    a=np.load(RAW.parent/"response_s0_v1/u1_true_actor_batch.npz")
    rows=[]
    scope=np.isin(a["draw_phase"],[5,6])
    for name,mask in (("all",np.ones(len(scope),bool)),("open_hold",scope)):
        for ch in range(16,23):
            components={k.removeprefix("dreturn_dphysical_"):a[k][mask,ch].astype(float)
                        for k in a if k.startswith("dreturn_dphysical_")}
            full=components.pop("complete")
            resid=full-sum(components.values())
            rows.append(dict(scope=name,channel=ch,n=len(full),terms_mean={k:float(v.mean()) for k,v in components.items()},
                whole_mean=float(full.mean()),residual_mean=float(resid.mean()),residual_max=float(abs(resid).max()),
                residual_relative_l2=float(np.linalg.norm(resid)/np.linalg.norm(full))))
    return rows


def drawn(batches):
    draws=defaultdict(Counter)
    for b in batches:
        counts={s:v["samples"] for s,v in b["sources"].items()}
        assert sum(counts.values())==256 and b["successors"]==256*b["h"]
        assert all(v["split"]=="train" for v in b["sources"].values())
        draws[b["h"]].update(counts)
    return draws


def training(runs):
    records=[]
    recovery=[]
    history=[]
    parent=None
    for name in runs:
        d=BASE/name
        raw=RAW.parent/name
        cs=lines(d/"cohorts.jsonl")
        us=lines(d/"updates.jsonl")
        batches=lines(d/"wm_draws.jsonl")
        stats=block_counts(raw)
        assert stats["policy_valid"]==sum(c["valid_transitions"] for c in cs)
        assert stats["intervals"]==sum(c["simulated_lane_intervals"] for c in cs)
        grip=Counter()
        for path in raw.glob("lanes_*.npz"):
            with np.load(path) as a:
                mask=a["valid"] & np.isin(a["phase"],[5,6])
                grip["open_hold_valid"]+=int(mask.sum())
                grip["open_hold_terminal"]+=int((mask & (a["fail"]>0)).sum())
                grip["open_hold_dual_prefix_ticks"]+=int(a["dual_prefix"][mask].sum())
                grip["open_hold_full_dual_intervals"]+=int((mask & (a["finger_min"]>.01).all(-1)).sum())
        assert len(batches)==10*len(us)
        history.extend(u["update"] for u in us)
        records.append(dict(run=name,new_updates=[us[0]["update"],us[-1]["update"]],h32=len(us),wm=len(batches),
            critic=20*len(us),imagined_steps=sum(u["imagined_policy_steps"] for u in us),real=stats,contact=grip,
            shared_process_s=read(d/"outcome.json")["elapsed_process_s"],actual_draws=drawn(batches),
            draw_file=str(d/"wm_draws.jsonl"),stored=sum(b["stored"] for b in batches),
            successors=sum(b["successors"] for b in batches),sample_windows=len(batches)*256,
            prefix_rejections=sum(c["prefix_invalid"] for c in cs)))
        f=d/"cohort_state.pt"
        state=torch.load(f,map_location="cpu",weights_only=False)
        assert len(state["optimizers"])==6 and state["updates"]==us[-1]["update"]
        equal=None
        if parent:
            filename=f"checkpoint_{us[0]['update']-1:06d}.pt"
            a,b=[torch.load(BASE/n/filename,map_location="cpu",weights_only=False) for n in (parent,name)]
            equal={k:all(torch.equal(t,b[k][key]) for key,t in a[k].items()) for k in ("actor","critic","dyn")}
            assert all(equal.values())
        recovery.append(dict(run=name,restart=read(d/"resume_boundary.json") if parent else None,
            parent_endpoint_matches=equal,weights=[str(p) for p in sorted(d.glob("checkpoint_*.pt"))],
            full_state=str(f.resolve()),bytes=f.stat().st_size,optimizers=len(state["optimizers"]),
            replay_chunks=len(state["replay"]),rng_keys=[k for k in state if "rng" in k],
            ratio=state["ratio_state"],lane_boundary=state["lane_boundary"]))
        del state
        parent=name
    assert history==list(range(1,history[-1]+1))
    totals={k:sum(r[k] for r in records) for k in ("h32","wm","critic","imagined_steps","shared_process_s","stored","successors","sample_windows","prefix_rejections")}
    totals.update({k:sum(r["real"][k] for r in records) for k in ("intervals","prefix","policy_valid","post_failure_substeps")})
    totals["entire_interval_dual"]=sum(row["entire_interval_dual"] for r in records for row in r["real"]["by_side_phase"])
    return records,recovery,totals


def main(runs):
    previous=read(BASE/"standard_lanes_20261124/baseline_manifest.json")
    budgets,recovery,totals=training(runs)
    cases=table(OUT/"nominal_segments.csv")
    summary=read(OUT/"nominal_summary.json")
    assert len(cases)==10*len(summary["records"])
    receipts={}
    for p in sorted(Path(".local-response").glob("*.exit")):
        log=p.with_suffix(".log")
        born=int(subprocess.check_output(["stat","-c","%W",str(log)]))
        receipts[p.stem]=dict(exit=int(p.read_text()),log=str(log.resolve()),
                              wall_s_approx=round(p.stat().st_mtime-born,2) if born>0 else None)
    entries=read(OUT/"collection.json")
    success=[r for r in entries["entries"] if not r.get("rejected")]
    meta=read(BASE/runs[0]/"actual_config.json")
    manifest=dict(method=previous["method"],stage="B0-04",base="0c81d822019686e1f44101246321ea3035b99b24",
        upstream=previous["upstream"],implementation=meta["git_revision"],field_root=str(Path.cwd()),final_candidate=None,
        standard_transfer_complete=False,full_bilateral_return=None,goal=.90,near=.88,config="config/b0/standard_response_v1.yaml",
        initialization=meta["migration"],inherited=dict(**previous["inherited"],prior_lanes_warm=1000),
        added_warm=read(BASE/"response_wm_v1/outcome.json"),warm_draws=drawn(lines(BASE/"response_wm_v1/samples.jsonl")),
        selection=dict(selected=str(BASE/"response_wm_v1/wm_000000.pt"),considered=[0,200,1000],new_mb_in_selected_weights=0,
            decision="Added fits improved some bilateral first-action predictions but neither retained independent old-grip and multimode accuracy. Use the registered +0 with the new joint data path."),
        inventory=read(BASE/"response_wm_v1/config.json")["inventory"],recipe=meta["cfg"]["wm_data_recipe"],
        response=dict(registration=str(OUT/"registration.json"),raw=str(RAW.resolve()),requery=str((RAW.parent/"response_requery_v1").resolve()),
            trajectories=len(success),train=sum(r["row"]["split"]=="train" for r in success),validation=sum(r["row"]["split"]=="validation" for r in success),
            rejected=len(entries["entries"])-len(success),branches=sum(len(r["labels"]) for r in success),prefix_substeps=100,common_tail_intervals=31,
            wall_s=entries["wall_s"],response_tables=[p.name for p in sorted(OUT.glob("*.csv")) if p.name.startswith(("response_","previous_"))],
            local_directions="h1_local_directions.csv",post_failure="Diagnosis only after first hard terminal"),
        gradient=gradient_groups(),joint_segments=budgets,joint_total=totals,recovery=recovery,
        formal=dict(cases=len(cases),passes=sum(r["passed"]=="True" for r in cases),
            first_2ms_force=sum(r["failure"]=="door_force_limit" and r["measured_substeps"]=="1" for r in cases),
            events=sum(len([p for p in r["completed_phases"].split(",") if p]) for r in cases),checkpoints=summary["records"],
            case_table="nominal_segments.csv",details="nominal_score_details.jsonl",video="u50_push_approach_grasp.mp4",
            physical_wall_s=sum(float(r["physical_wall_seconds"]) for r in cases)),receipts=receipts,
        split_gates=dict(D=None,continuous_Warp=None,C=None,native_full=None,seed1=None,seed2=None,H=None),
        attributable_gpu_hours=None,device=meta["device"])
    manifest.update(round_snapshot="closed at u200", previous_field_receipt="previous_field_receipt.json",
        final_requery=str((RAW.parent/"response_requery_final_v1").resolve()),
        recovery_draw_check="resume_draw_check.json",event_clock_receipt="event_clock_receipt.json",
        report="reports/B0_CONTACT_RESPONSE_RESULTS_20261124.md",
        decision=dict(u50="Push release peak force fell and failure was later. Continue to u100.",
                      u100="Six entry forces decreased on both sides, push release survival improved. Continue to u200.",
                      u200="Requested endpoint. Push release improved but pull grip force rebounded, six entries still failed at 2 ms, zero stage events. No final candidate or further budget assigned."),
        next_evidence="Use existing 2 ms dynamics and matched branch repeats to localize H1 jaw integration residual and J2 cross-response. Keep the official loss, integrator and judge.",
        old_new_retention_control_runs=0)
    (OUT/"baseline_manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("runs",nargs="+")
    main(p.parse_args().runs)
