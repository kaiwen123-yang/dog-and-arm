"""Reconcile every adaptation block, the physical judgements, and the recoverable endpoint."""
import csv,json
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
from pathlib import Path
import numpy as np
import torch
from scripts.b0.joint_adapt import ck
from scripts.b0.joint_collection import RAW,OUT
from scripts.b0.dynamics_h32_pilot import read,write
from scripts.b0.dynamics_h32_probe import restore_rng
from scripts.b0.score_temporal_wm import csv_file

def main():
    reg=read(OUT/"registration.json")
    a=OUT/"adapt"
    q=read(a/"qualified.json") if (a/"qualified.json").exists() else None
    rows=[];prev=False;streak=[]
    keys=list(reg["limits"])
    for f in sorted(a.glob("node_*/scores.json")):
        n=int(f.parent.name[5:]);score=read(f)
        assert score["long_counts"]==reg["long_denominators"]
        vals=score["values"]
        if n:
            ch=read(f.parent/"check.json")
            assert ch["long_ok"]==all(vals[k]<=reg["limits"][k] for k in keys)
            assert ch["online_ok"]==all(vals[k]<rows[0][k] for k in vals if k.startswith("H"))
            if prev and ch["passed"]:streak.append(n)
            prev=ch["passed"]
        factor=max(vals[k]/reg["limits"][k] for k in keys)
        rows.append(dict(step=n,**vals,worst_multiple_of_limit=factor,above_limit="|".join(k for k in keys if vals[k]>reg["limits"][k]),
                         passes_all=bool(n and prev)))
    assert (q is None and not streak) or (q and q["second"]==streak[0])
    csv_file(a/"all_nodes.csv",rows)
    accounted=read(a/"draw_accounting.json")
    last=rows[-1]["step"]
    retained=accounted["persisted_batches"]
    extra=accounted["discarded"]["discarded_optimizer_steps"]
    assert retained==last and retained+extra<=reg["cumulative_max"]
    state=torch.load(ck(last),map_location="cpu",weights_only=False)
    assert set(state["rng"])=={"numpy","gpu","cpu"}
    assert state["batches"]==last and len(state["optimizers"])==2
    finite=all(torch.isfinite(v).all().item() for v in state["dyn"].values())
    opt_counts=[]
    for opt in state["optimizers"]:
        opt_counts.append(len(opt["state"]))
        for g in opt["state"].values():
            for k,v in g.items():
                if torch.is_tensor(v):assert torch.isfinite(v).all()
                if k=="step":assert int(v)==last
    assert finite and min(opt_counts)>0
    restore_rng(state["rng"])
    physics=read(OUT/"physics/physics_summary_shared_u0.json")
    formal=read(OUT/"h32/seed0_u0_formal.json")
    for r in formal["rows"]:
        source=Path(r["source"])
        orig=read(source);ret=read(source.with_name("return.json"))
        assert orig["passed"]==r["passed"] and orig["first_failure"]["reason"]==r["failure"]
        assert ret["executed_substeps"]==r["executed_steps"]
    assert 10==len(formal["rows"])
    nearest=min(rows[1:],key=lambda x:x["worst_multiple_of_limit"])
    moves=[]
    updates=OUT/"main/updates.jsonl"
    if updates.exists():moves=[json.loads(l) for l in updates.read_text().splitlines()]
    fail=read(OUT/"main/pre_actor_pause.json") if (OUT/"main/pre_actor_pause.json").exists() else None
    wm_main=fail["wm"] if fail else 10*len(moves)
    small=str(OUT)
    manifest=dict(method=reg["method"],review_commit="528a9d7ac1ddbf399a125a93b9ee21bc1af6fd9b",
        diagnostics_commit="816f1aaeeaf96cb73a49dec6a09d9f06235296ca",created_beijing=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        supermimic="abc124c1bd5976341034668af3d12c087f2f1f55",mjlab="dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd",
        stage="B0-04",final_candidate=None,full_bilateral_return=None,return_status="NA",
        training=dict(physics_id=reg["physics"],dt=.00025,servo_dt=.002,policy_dt=.02,coefficient=.50625),
        gate=dict(qualification=q,passing_block_ends=[r["step"] for r in rows if r["passes_all"]],
            consecutive_pairs=streak,full_fixed_window_denominators=reg["long_denominators"],limits=reg["limits"],
            e0=rows[0],nearest_by_worst_ratio=nearest,last=rows[-1],budget_remaining=1000-(retained+extra)),
        training_budget=dict(diagnostic_WM=30,adapt_retained=retained,adapt_discarded=extra,adapt_charged=retained+extra,
            qualified_seed0_H32=len(moves),qualified_seed0_joint_WM=wm_main,qualified_seed0_critic=20*len(moves),
            previous_u10_pending=[2,2],source_checkpoint_inherited_offline_WM=1000,actor_B003_inherited_updates=1000,actor_B003_collected=1088000),
        formal=dict(backend="original 2ms Warp",force_limit_N=6,new_shared_u0_cases=formal["cases"],shared_u0_passed=formal["passed"],
            shared_u0_events=formal["events"],first_substep_overforce=formal["at_first_2ms_overforce"],
            observed_microsteps=sum(r["executed_steps"] for r in formal["rows"]),prefix_microsteps=sum(r["prefix_steps"] for r in formal["rows"])),
        development_closedloop=physics["closed_loop"],boundary_budget=physics["boundary_budget"],
        source_draws=accounted["draws_by_horizon_and_source"],actual_boundary_H1_draws=accounted["boundary_h1"],
        new_collection={k:{key:read(OUT/"collection"/(k+".json"))[key] for key in ("seed","collector","h1","h7","terminal_first")} for k in ("train","development")},
        additional_stages=dict(D=None,full_Warp_nominal=None,C=None,native_3_3_full=None,independent_seeds=None,H=None),
        actual_package_recovery=dict(host="autodl-d57",cwd="/root/autodl-tmp/dog-and-arm-b0-temporal-v1",wm=str(ck(last)),wm_optimizer_entries=opt_counts,
            exact_rng_loaded=True,finite_weights_and_optimizer_state=True,wm_index=last,online_train=str(RAW/"collection/train/state.pt"),
            live_train_solver=str(RAW/"collection/train/solver.npz"),validation_only=str(RAW/"collection/development/state.pt"),
            shared_actor_and_critic=reg["actor_critic"],replay=str(RAW/"replay"),physics=str(RAW/"physics"),logs=str(RAW/"logs")),
        files=dict(registration=small+"/registration.json",reviewed_replay=small+"/replay/summary.json",block_scores=small+"/adapt/all_nodes.csv",
            per_case=small+"/h32/seed0_u0_formal.csv",original_judgements=small+"/formal",closedloop=small+"/physics/pure_actor_shared_u0_cases.csv",
            policy_videos=[small+"/physics/"+s+"_shared_u0_actor.mp4" for s in ("pull","push")],signed_servo=small+"/physics/archived_servo_rows.csv",
            eligible=small+"/collection/eligible_windows.csv",draw_accounting=small+"/adapt/draw_accounting.json",
            endpoint_directions=small+f"/adapt/node_{last:06}/derivative_summary.json"),
        main_pause=fail,score_reference=dict(paper_SONIC=.90,project_near=.88,full_return_available=False))
    write(OUT/"baseline_manifest.json",manifest)

if __name__=="__main__":
    main()
