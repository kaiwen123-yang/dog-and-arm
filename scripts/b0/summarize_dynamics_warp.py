"""Compute time-aligned differences for every repeated Warp window; preserve dimensions and clocks."""
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from learning.b0.physics import make_model
from scripts.b0.dynamics_warp_windows import OUT, RAW, dump, read


def write_csv(path, rows):
    with path.open("w") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def scalars(arr):
    # Timed keys include the phase of the physical observation.
    q,v=arr["qpos"],arr["qvel"]
    return {"J4_q_rad":("end",q[:,26]),"J6_q_rad":("end",q[:,28]),
            "J4_v_rad_s":("end",v[:,25]),"J6_v_rad_s":("end",v[:,27]),
            "finger1_q_mm":("end",q[:,29]*1000),"finger2_q_mm":("end",q[:,30]*1000),
            "finger1_v_m_s":("end",v[:,28]),"finger2_v_m_s":("end",v[:,29]),
            "opening_mm":("end",(q[:,29]-q[:,30])*1000),"TCP_mm":("start",arr["tcp_start"]*1000),
            "handle_mm":("start",arr["handle_start"]*1000),"door_q_deg":("end",np.rad2deg(q[:,31])),
            "door_v_rad_s":("end",v[:,30]),"eq_pos_mm":("start",arr["eq_residual_start"]*1000),
            "finger_symmetry_residual_mm":("end",(q[:,29]+q[:,30])*1000),
            "net_door_force_N":("start",np.linalg.norm(arr["door_robot_force_N"],axis=1)),
            "door_force_vector_N":("start",arr["door_robot_force_N"]),"finger1_load_N":("start",arr["finger_load_N"][:,0]),
            "finger2_load_N":("start",arr["finger_load_N"][:,1])}


def differences(early,later,kind):
    a,b=early[0],later[0]
    stride=b["ratio"]//a["ratio"]
    out=dict(id=a["id"],route=a["route"],comparison=kind,h_coarse_ms=a["h_s"]*1000,
             h_fine_ms=b["h_s"]*1000,rep_a=a["repeat"],rep_b=b["repeat"])
    for k,(side,xa) in early[1].items():
        xb=later[1][k][1][0 if side=="start" else stride-1::stride]
        delta=np.abs(xa-xb) if xa.ndim==1 else np.linalg.norm(xa-xb,axis=1)
        out["max_"+k]=float(delta.max())
        out["rms_"+k]=float(np.sqrt((delta**2).mean()))
    return out


def longest_span(bits):
    edges=np.diff(np.r_[False,bits,False].astype(int))
    spans=np.flatnonzero(edges<0)-np.flatnonzero(edges>0)
    return int(max(spans,default=0))


def features(r, d):
    f=np.linalg.norm(d["door_robot_force_N"],axis=1)
    dual=(d["finger_load_N"]>.01).all(1)
    h,ratio=r["h_s"],r["ratio"]
    c=d["ctrl"].reshape(10,ratio,-1)
    t=d["force_site_start_s"]
    q0=d["q0"]
    drift=float(abs(d["time_device"]-d["time_device"][0]-(d["qv_end_s"]-h)).max())
    cache=d["servo_cached_bias"].reshape(10,ratio,-1)[:,0]
    internal=d["internal_bias_start"].reshape(10,ratio,-1)
    new=dict(id=r["id"],route=r["route"],h_ms=h*1000,rep=r["repeat"],source_split=r["registration"]["split"],
             branch=r["registration"]["branch"][1],source=r["training_metadata"]["source"],
             phase=r["training_metadata"]["phase"],raw=r["raw"],n=len(f),qv_time_max_drift_s=drift,
             ctrl_held_error=float(abs(c-c[:,:1]).max()),prior_servo_cache_error=float(abs(cache[1:]-internal[:-1,0]).max()),
             largest_within_2ms_internal_bias_change=float(abs(internal-internal[:,:1]).max()),
             training_q_at_start_max_drift=r["original_2ms_reconstruction"].get("exact_archive_q_max",r["original_2ms_reconstruction"]["window_q_max"]),
             training_v_at_start_max_drift=r["original_2ms_reconstruction"].get("exact_archive_v_max",r["original_2ms_reconstruction"]["window_v_max"]),
             archive_q_trace_discrepancy=r["archive_max_q_delta_at_2ms"],archive_v_trace_discrepancy=r["archive_max_v_delta_at_2ms"],
             J4_q_start_rad=float(q0[26]),J6_q_start_rad=float(q0[28]),
             force_peak_n=r["max_force_n"],force_peak_start_s=r["force_peak_sample_s"],force_abs_impulse_Ns=float(f.sum()*h),
             gt6_first_start_s=r["first_gt6N_sample_s"],gt6_first_judge_call_s=r["first_gt6N_judge_call_s"],
             initial_solve_net_force_n=float(f[0]),complete_dual=bool(dual.all()),dual_time_s=float(dual.sum()*h),
             dual_longest_s=float(longest_span(dual)*h),dual_initial_s=float((np.where(~dual)[0][0] if not dual.all() else len(dual))*h),
             left_finger_peak_N=float(d["finger_load_N"][:,0].max()),right_finger_peak_N=float(d["finger_load_N"][:,1].max()),
             J4_peak_abs_rad_s=r["wrist_peak_abs_rad_s"][0],J6_peak_abs_rad_s=r["wrist_peak_abs_rad_s"][1],
             J4_peak_end_s=r["wrist_peak_end_s"][0],J6_peak_end_s=r["wrist_peak_end_s"][1],
             J4_reverse_end_s=json.dumps(r["wrist_reversal_end_s"][0]),J6_reverse_end_s=json.dumps(r["wrist_reversal_end_s"][1]),
             J4_v_end_rad_s=float(d["qvel"][-1,25]),J6_v_end_rad_s=float(d["qvel"][-1,27]),
             opening_end_mm=float(1000*(d["qpos"][-1,29]-d["qpos"][-1,30])),
             door_angle_end_rad=float(d["qpos"][-1,31]),
             eq_constraint_max_mm=float(abs(d["eq_residual_start"]).max()*1000),
             phase_events=len(r["events"]),judge_failure=(r["event_failure"] or {}).get("reason"),
             judge_first_call_s=r["judge_first_call_with_failure_s_from_window"],
             prefix_steps=(r["real_prefix"] or {}).get("steps"),full_state_prefix_s=.2,
             already_failed_before_window=r["judge_failed_before_window"])
    assert np.all(d["eq_row0_type"]==0)
    assert new["ctrl_held_error"]==0 and new["prior_servo_cache_error"] < 1e-6 and not r["buffer_overflow"]
    assert np.all(np.isfinite(d["qvel"])) and np.all(np.isfinite(f))
    return new


def main():
    reg=read(OUT/"registration.json")
    model=make_model()
    for name,q,v in [("piper_joint4",26,25),("piper_joint6",28,27),("piper_gripper_joint1",29,28),
                     ("piper_gripper_joint2",30,29),("door_single_hinge",31,30)]:
        assert model.joint(name).qposadr.item()==q and model.joint(name).dofadr.item()==v
    groups=defaultdict(dict)
    features_out=[]
    receipts=list((RAW/"receipts").glob("*__rep*.json")) or list(OUT.glob("*__rep*.json"))
    for f in sorted(receipts):
        r=read(f)
        with np.load(r["raw"]) as buf:
            d=dict(buf)
        features_out.append(features(r,d))
        groups[(r["id"],r["route"])][(r["ratio"],r["repeat"])]=(r,scalars(d))
    diffs=[]
    for (ident,route), runs in groups.items():
        ratios=sorted({key[0] for key in runs})
        for ratio in ratios:
            diffs.append(differences(runs[ratio,0],runs[ratio,1],"same-command repeat"))
        for a,b in zip(ratios,ratios[1:]):
            for rep in (0,1):
                diffs.append(differences(runs[a,rep],runs[b,rep],"adjacent step"))
    write_csv(OUT/"features.csv",features_out)
    write_csv(OUT/"comparisons.csv",diffs)
    basics=[r for r in features_out if r["route"]=="archive_ctrl" and r["h_ms"] in (.5,1.,2.)]
    bridge=[r for r in features_out if r["route"]=="live_servo" and r["h_ms"] in (.125,.25)]
    rows_by_route={rt:len([r for r in features_out if r["route"]==rt]) for rt in sorted(set(r["route"] for r in features_out))}
    total_ticks=sum(r["n"] for r in features_out)
    accounts={"recorded_window_selected_lane_substeps":total_ticks,
              "all_28_lanes_window_substeps":28*total_ticks,
              "live_servo_additional_200ms_prefix_selected_lane_substeps":sum(r["prefix_steps"] or 0 for r in features_out),
              "live_servo_additional_pre_window_selected_lane_substeps":sum(read(f)["counts"]["live_servo_preceding_branch_ticks"] for f in receipts),
              "timing_scope":"Wall per receipt excludes reconstructing archived full live snapshots once per case per process. Includes per-repeat writes. CPU runs excluded."}
    assert len(basics)==66 and len(set(r["id"] for r in bridge))==4
    critical=sorted(set(r["id"] for r in bridge))
    window_t={item["trace_id"]:item["transition"] for item in reg["items"]}
    # Computation ledger for the five completed invocations: all-window live/exact initial
    # sweeps, then four-window exact refinement, snapshot servo and full-prefix servo.
    common_preparation=2*sum(100+10*t for t in window_t.values())+3*sum(100+10*window_t[k] for k in critical)
    archive_alignment=sum(10*t for t in window_t.values())+2*sum(10*window_t[k] for k in critical)
    all_ticks=total_ticks+accounts["live_servo_additional_200ms_prefix_selected_lane_substeps"]+accounts["live_servo_additional_pre_window_selected_lane_substeps"]+common_preparation+archive_alignment
    accounts.update(live_snapshot_preparation_per_lane_substeps=common_preparation,
                    exact_state_reconstruction_per_lane_substeps=archive_alignment,total_integration_calls=all_ticks,
                    total_Warp_world_substeps=28*all_ticks,worlds_in_each_invocation=28,
                    cpu_integration_calls=2*sum(10*r+10*window_t[k] for r in (1,2,4,8,16) for k in ("pull_5_train_grasp/t7/b23","push_0_validation_grip_hold/t0/b0")))
    notable=[]
    for k in critical:
        metrics=[]
        for r in bridge:
            if r["id"]==k:
                metrics.append({name:r[name] for name in ("h_ms","rep","force_peak_n","force_abs_impulse_Ns","dual_time_s","J4_v_end_rad_s","J6_v_end_rad_s","judge_failure","gt6_first_start_s","judge_first_call_s")})
        notable.append(dict(id=k,continuous_prefix_fine=metrics))
    dump(OUT/"time_step_decision.json",dict(registered_windows=len(reg["items"]),primary_observations=len(basics),
         observers_by_route=rows_by_route,units_and_alignment="Native adjacent-pair common times. Force/site/equality solve residual sampled at starts, integrated q/v at ends. Each unit has separate max absolute and RMS; TCP/force vector differences use Euclidean norm.",
         critical_windows=critical,key_window_selection="Decisive force/contact mode changes and wrist reversals: unique pull train maximum jointly representing both wrists, push train initial extreme, and both u0 hold windows. Original two u0/ref_arm checks have negligible force and no step-dependent decision.",
         exact_initial_state="An initial full-live reconstruction of the registered windows differed from archived q/v by up to ~0.0031/~0.066. The primary sweep reapplied archive q/v, controls and available solver state, replaying prior solves at 2ms with recorded states before saving one full 28-world snapshot. During the measured window all dynamics evolved freely. Both routes retained.",
         key_evidence=notable,raw=str(RAW),features="features.csv",differences="comparisons.csv",counts=accounts,
         fine_training_dt_s=.00025,actor_dt_s=.02,external_servo_dt_s=.002,external_bias_delay_s=.002,
         steps_per_actor=80,gen_coord_c=81/160,formal_warp_dt_s=.002,native_formal="MuJoCo 3.3.0 original",
         obligation="Regenerate the affected Warp training and validation pools with the new identity. Native pool not implicated in these Warp wrist-saturation targets remains individually eligible. No old-physics candidate promoted.",
         qualification="Four decisive windows had independent continuous 200ms prefixes and replayed preceding canonical commands at each tested h. At 0.25 vs 0.125ms the main wrist/endpoint response, coarse event outcomes and peak shape are retained. Exact 6N force cutoffs, action/servo cadence and original formal evaluation stay unchanged.",
         unresolved="High-frequency contact impulse timing is still sensitive. In fine push grasp pointwise aligned forces can differ by ~31N despite similar peaks, impulses and endpoint velocity. Fine Warp remains an approximation for coarse H1/H7 labels. A single brief missing dual sample can vary across repeated live pull-grasp prefixes.",
         same_command_ctrl_and_cache="For every recorded trace: complete ctrl has zero within-2ms drift; servo cache at t=previous interval's first-solve bias, max discrepancy <1e-6. Engine internal bias was allowed to update on every physics step.",
         recovery="Run scripts.b0.dynamics_warp_windows with same registered windows and CLI; full exact starts and raw time series, controls, bias, warmstart, phase judge and cost receipts under raw. CPU-only bounds are separate."))


if __name__=="__main__":
    main()
