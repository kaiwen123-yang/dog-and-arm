"""Summarize each independent teacher's clock, masks, measured corrections and outcome."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from scripts.b0.recovery_teacher import FROZEN, OUT, RAW, REGISTER


def index(trial):
    episode_id = trial["episode_id"]
    path = RAW / episode_id
    ref = FROZEN / f'{trial["side"]}_{trial["goal"]}_train'
    meta = json.loads((path/"metadata.json").read_text())
    result = json.loads((OUT/(episode_id+".json")).read_text())
    timing = json.loads((OUT/(episode_id+"_clock.json")).read_text())
    nominal = np.load(ref/"qpos.npy",mmap_mode="r")[0]
    q = np.load(path/"qpos.npy",mmap_mode="r")
    initial = q[0]
    delta_yaw = np.rad2deg(2*(np.arctan2(initial[6],initial[3])-np.arctan2(nominal[6],nominal[3])))
    perturb = trial["perturbation"]
    np.testing.assert_allclose(initial[:2]-nominal[:2],[perturb.get("dx",0),perturb.get("dy",0)],atol=1e-7)
    np.testing.assert_allclose([delta_yaw,np.rad2deg(initial[-1])],[perturb.get("yaw",0),perturb.get("door",0)],atol=1e-5)
    valid = np.load(path/"valid_full_interval.npy")
    pos = np.load(path/"bc_positive_mask.npy")
    pulse = np.load(path/"intervention.npy")
    physical = np.load(path/"physical_target.npy",mmap_mode="r")
    frozen = np.load(ref/"physical_target.npy",mmap_mode="r")
    missing_bilateral = sampled_substeps = first_regain = None
    if pulse.any():
        start = int(np.flatnonzero(pulse)[0])*10
        stop = (int(np.flatnonzero(pulse)[-1])+1)*10
        fingers = np.load(path/"substeps/finger_load_N.npy",mmap_mode="r")
        both = (fingers[start:min(len(fingers),stop+250)] > .01).all(1)
        missing_bilateral, sampled_substeps = int((~both).sum()), len(both)
        first_regain = next((start+i for i in range(stop-start,len(both)-49) if both[i:i+50].all()),None)
        np.testing.assert_allclose(physical[pulse,-1],.09,rtol=0,atol=1e-8)
    np.testing.assert_equal(pos.sum(),timing["bc_positive_frames"])
    n = min(50,len(frozen),len(physical))
    deform = physical[:n]-frozen[:n]
    terminal = np.flatnonzero(np.load(path/"terminated.npy"))
    if terminal.tolist() != [len(physical)-1] or len(q) != len(physical)+1 or len(valid) != len(physical):
        raise ValueError(f"Terminal successor invariant failed for {path}")
    offsets = timing["phase_end_offset_s"]
    return dict(episode=episode_id, side=trial["side"], split=trial["split"], family=trial["family"],
                host=meta["collector_hostname"], success=result["physical_teacher_pass"],
                failure=result["failure"], first_failed_physics_interval=result["first_failure_interval"],
                physical_steps=result["physics_steps"], fixed_dt_transitions=int(valid.sum()),
                terminal_interval_substeps=int(np.diff(np.load(path/"physics_step.npy"))[-1]),
                post_failure_completed_substeps=result["post_failure_completed_physics_steps"],
                bc_positive_frames=int(pos.sum()), phase_mismatch_or_outside=timing["complete_phase_mismatch_or_outside_reference"],
                intervention_issued=int(pulse.sum()), intervention_requested=trial["hold_open_policy_ticks"],
                pulse_window_no_bilateral_substeps=missing_bilateral,
                pulse_window_substeps_to_end_or_post_500ms=sampled_substeps,
                first_post_pulse_100ms_bilateral_start_substep=first_regain,
                peak_resultant_n=result["peak_net_door_force_N"], final_door_deg=result["final_deg"],
                arrival_offset_s=offsets.get("approach_base"), open_end_offset_s=offsets.get("open"),
                maximum_abs_phase_end_offset_s=max(map(abs,offsets.values()),default=None),
                initial_dx_m=initial[0]-nominal[0], initial_dy_m=initial[1]-nominal[1],
                initial_dyaw_deg=delta_yaw,initial_door_deg=np.rad2deg(initial[-1]),
                first_second_actual_wheel_label_delta_rms_radps=float(np.sqrt(np.square(deform[:,12:16]).mean())),
                first_second_actual_arm_label_delta_rms_rad=float(np.sqrt(np.square(deform[:,16:22]).mean())),
                labels="training_only" if trial["split"] == "train" else "validation_only")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--allow-partial",action="store_true",help="print available cases; do not write the final index")
    args=p.parse_args()
    design=json.loads(REGISTER.read_text())["cases"]
    rows=[]
    for trial in design:
        if args.allow_partial and not (OUT/(trial["episode_id"]+"_clock.json")).is_file():
            continue
        rows.append(index(trial))
    if args.allow_partial:
        print(json.dumps(rows,indent=2,allow_nan=False))
    else:
        with (OUT/"episode_index.csv").open("x") as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
