"""Build the bounded C20/H32 round manifest from original per-update and per-case receipts."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path("results/b0/standard_dynamics_20261124")
RAW = Path("results/raw_large/b0/dynamics_20261124")


def read(path):
    def reject_nonfinite(value):
        raise ValueError(f"Nonfinite entry {value} in {path}")
    return json.loads(path.read_text(), parse_constant=reject_nonfinite)


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def offline(arm):
    blocks = sorted(ROOT.glob(f"{arm}_train_*.jsonl"))
    rows = [row for path in blocks for row in records(path)]
    if not rows or [r["k"] for r in rows] != list(range(1,len(rows)+1)):
        raise ValueError(f"Incomplete or repeated offline updates for {arm}")
    horizons = [r["h"] for r in rows]
    if len(rows)>1000 or horizons != [1 if i%10<2 else 7 for i in range(len(rows))]:
        raise ValueError(f"Offline H1/H7 budget or order differs for {arm}")
    nodes = {}
    for node in (50,200,1000):
        p=ROOT/f"{arm}_stability_{node:06}.json"
        if p.exists():
            nodes[node] = dict(disposition=read(p)["disposition"],interval_gradients=str(ROOT/f"{arm}_gradients_{node:06}.json"),
                               physical_units=str(ROOT/f"{arm}_fixed_probe_{node:06}.json"))
    return dict(updates=len(rows),h1=horizons.count(1),h7=horizons.count(7),windows=256*len(rows),
                supervised_successors=256*sum(horizons),source_identity=str(ROOT/"c20_data_identity.json"),
                node_stability=nodes,loop_seconds=sum(records(path)[-1]["elapsed_s"] for path in blocks))


def formal(tag):
    source=ROOT/"h32"/f"{tag}_formal.json"
    j=read(source)
    found={}
    for row in j["rows"]:
        record=read(Path(row["source"]))
        key=(record["side"],record["segment"])
        if key in found or record["backend"]!="warp" or row["passed"] != record["passed"]:
            raise ValueError(f"Formal case identity mismatch {tag} {key}")
        found[key]=record
        returned=read(Path(row["source"]).with_name("return.json"))
        if returned["executed_substeps"]!=record["physics_steps"]:
            raise ValueError("Formal physical and effort horizons disagree")
    if len(found)!=10 or j["passed"]!=sum(r["passed"] for r in found.values()):
        raise ValueError("Formal denominator or successes disagree")
    return dict(cases=10,passes=j["passed"],first_2ms_overforce=j["at_first_2ms_overforce"],events=j["events"],
        hold_first_force_n={s:(found[s,"stable_grip"]["first_failure"] or {}).get("door_net_force_n") for s in ("pull","push")},
        contact_policy_world_steps=sum(r["physics_steps"] for r in found.values()),
        prefix_world_steps=sum(r["prefix_physics_steps"] for r in found.values()),source=str(source))


def pilot(arm):
    folder=ROOT/"h32"/arm
    outcome=read(folder/"outcome.json")
    rows=records(folder/"updates.jsonl")
    if [r["update"] for r in rows]!=list(range(1,11)):
        raise ValueError("Pilot did not finish the ten registered updates")
    for r in rows:
        u=r["update"]
        if r["optimizer_steps"]!={"actor":u,"wm":10*u,"critic":20*u}:
            raise ValueError("Actual optimizer counter mismatch")
    if outcome["actual_steps"]!=rows[-1]["optimizer_steps"]:
        raise ValueError("Pilot receipt does not match actual counters")
    j=read(folder/"recovery.json")
    for k in ("policy_checkpoint","complete_state"):
        if not Path(j[k]).is_file():
            raise FileNotFoundError(j[k])
    return dict(h32=outcome["H32"],joint_wm=outcome["WM"],critic=outcome["Critic"],valid=outcome["valid"],
                simulated_policy_intervals=outcome["simulated"],training_physics_steps=80*outcome["simulated"],
                process_loop_wall_s=outcome["elapsed_s"],ratio=outcome["ratio"],online_physics=str(folder/"online_physics.json"),
                recovery=j["complete_state"],last_checkpoint=j["policy_checkpoint"],
                original_target_pre_u1=str(folder/"preflight.json"))


def paired_first_update():
    small, raw = ROOT/"h32", RAW/"h32"
    checks = {}
    for filename in ("preflight_draws.npz","u1_actual_wm_draws.npz","draws_u01.npz"):
        with np.load(small/"control"/filename) as a, np.load(small/"experiment"/filename) as b:
            if set(a.files)!=set(b.files):
                raise ValueError("Different recording fields in paired first draws")
            for name in a.files:
                np.testing.assert_array_equal(a[name],b[name],err_msg=name)
            checks[filename]=len(a.files)
    fields=("episode","motion_time","draw_phase","draw_mode","terminated","sim_ctx",
            "history","prev_action","state","first_command")
    with np.load(raw/"control/u1_true_actor_batch.npz") as a, np.load(raw/"experiment/u1_true_actor_batch.npz") as b:
        for name in fields:
            np.testing.assert_array_equal(a[name],b[name],err_msg=name)
        return dict(index_groups=checks,compared_fields=fields,actual_actor_batch=len(a["episode"]),
                    unique_episodes=int(np.unique(a["episode"]).size),input_and_first_command_exact=True)


def build(disposition):
    decision=read(disposition)
    reg=read(ROOT/"pilot_registration.json")
    data=read(ROOT/"c20_data_identity.json")
    pick=read(ROOT/"pilot_wm_locked.json")
    lock=read(ROOT/"pilot_execution_lock.json")
    if pick["pilot_wm"]!=lock["checkpoints"]["experiment"] or pick["control_wm"]!=lock["checkpoints"]["control"]:
        raise ValueError("Executed WM differs from the locked selection")
    preflight=read(ROOT/"h32"/"preflight_pair.json")
    if not preflight["passed"]:
        raise ValueError("Paired H32 graph failed")
    budget={arm:offline(arm) for arm in ("C20","rebase")}
    pilots={arm:pilot(arm) for arm in ("control","experiment")}
    scores={tag:formal(tag) for tag in ("shared_u0","control_u1","control_u10","experiment_u1","experiment_u10")}
    common=read(ROOT/"shared_collection.json")
    valid=sum(p["valid"] for p in pilots.values())-common["collected"]
    simulated=sum(p["simulated_policy_intervals"] for p in pilots.values())-common["simulated"]
    return dict(method="SuperMimic-M1Piper-standard-v1",created_beijing=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        reviewed_plan_commit=reg["plan_commit"],implementation_start_commit="20cc9ecc7f5d85f3b55e278f824123cd04b84cd1",
        supermimic="abc124c1bd5976341034668af3d12c087f2f1f55",mjlab_research="dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd",
        physical_windows=str(ROOT/"warp_windows/time_step_decision.json"),data_qualification=str(ROOT/"data_qualification.json"),
        physics_identity=data["physics_identity"],training_dt_s=data["physics_dt"],policy_dt_s=.02,servo_dt_s=.002,
        gencoord_c=data["substep_coeff"],formal_warp_dt_s=.002,formal_native_version="3.3.0",force_limit_n=6,
        experiment_kind=reg["experiment_kind"],prior_selected_wm=None,prior_wm_retention_passed=False,
        pilot_wm=pick["pilot_wm"],pilot_selection=str(ROOT/"pilot_wm_locked.json"),
        actual_pair_lock=str(ROOT/"pilot_execution_lock.json"),h32_preflight=str(ROOT/"h32/preflight_pair.json"),
        common_initial_collection=common["collected"],actual_first_pair=paired_first_update(),offline_wm=budget,pilots=pilots,
        pilot_totals=dict(h32=sum(p["h32"] for p in pilots.values()),wm=sum(p["joint_wm"] for p in pilots.values()),
                          critic=sum(p["critic"] for p in pilots.values()),unique_online_valid_intervals=valid,
                          unique_online_simulated_intervals=simulated,unique_online_world_steps=80*simulated),
        formal_nominal=scores,unique_pilot_formal_cases=sum(v["cases"] for v in scores.values()),
        unique_pilot_formal_passes=sum(v["passes"] for v in scores.values()),prior_response_formal_cases_excluded=60,
        prior_temporal_u0_cases_excluded=10,new_T2_batches=0,raw_root=str(RAW.resolve()),**decision)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision",type=Path,required=True)
    args=parser.parse_args()
    manifest=build(args.decision)
    (ROOT/"baseline_manifest.json").write_text(json.dumps(manifest,indent=2,allow_nan=False)+"\n")
