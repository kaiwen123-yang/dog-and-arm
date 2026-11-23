"""Register and collect independent full-clock 20 ms Warp teachers for paired BC."""
import argparse
import json
from pathlib import Path

import numpy as np


RAW = Path("results/raw_large/b0/recovery_a_teacher_r1")
OUT = Path("results/b0/recovery_a_teacher_r1")
REGISTER = Path("config/b0/recovery_a_teacher_r1.json")
FROZEN = Path("results/raw_large/b0/full_warp_hold_park_r1")


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        json.dump(obj, f, indent=2, allow_nan=False)
        f.write("\n")


def register():
    seed = 231123
    rng = np.random.default_rng(seed)
    cases = []
    protocols = [
        ("train", "xy"), ("train", "combined"), ("validation", "combined"),
        ("train", "xy"), ("train", "yaw"), ("train", "door"),
        ("train", "combined_recover"), ("validation", "combined_drop"),
    ]
    for i, (split, family) in enumerate(protocols):
        for side, goal in (("pull", 60), ("push", 25)):
            perturb = {}
            if family == "xy" or family.startswith("combined"):
                perturb.update(dx=float(rng.uniform(-.045,.045)), dy=float(rng.uniform(-.045,.045)))
            if family == "yaw" or family.startswith("combined"):
                perturb["yaw"] = float(rng.uniform(-4.8,4.8))
            if family == "door" or family.startswith("combined"):
                perturb["door"] = float(rng.uniform(.3,4.8))
            cases.append(dict(episode_id=f"aug_{side}_{i+1:02d}_{split}_{family}", side=side,
                              goal=goal, split=split, family=family, perturbation=perturb,
                              hold_open_policy_ticks={"combined_recover": 2, "combined_drop": 16}.get(family,0)))
    return dict(seed=seed, generator="numpy default_rng PCG64; independent uniform continuous draws per side and family",
                ranges=dict(dx_m=[-.045,.045], dy_m=[-.045,.045], yaw_deg=[-4.8,4.8], door_deg=[.3,4.8]),
                selection="all 16 draws retained; no performance filtering or replacement; finite in-range root and hinge starts",
                reference=str(FROZEN), clock="simulation frame k = frozen same-side reference frame k from 0; no retiming",
                teacher="P6 closed loop, one clamped physical target for ten 2 ms steps; measure all 13 phases and both parking windows",
                intervention="only named hold-opening pulses; resume teacher after pulse if physical judgement still alive; failed intervals retained",
                split="entire independent physical episode; validation never used for supervised fitting",
                cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--episode")
    parser.add_argument("--index",action="store_true",help="only rebuild masks and clock metrics from completed physical measurement")
    args = parser.parse_args()
    if args.register:
        if args.episode:
            parser.error("registration and collection are separate")
        write(REGISTER, register())
        return
    spec = json.loads(REGISTER.read_text())
    trials = {c["episode_id"]: c for c in spec["cases"]}
    if args.episode not in trials:
        parser.error("choose an episode_id from the registered conditions")
    trial = trials[args.episode]
    from scripts.b0.collect_contact import collect
    case = trial["episode_id"]
    evidence = OUT / (case + ".json")
    delegation = RAW / "external_assignments.json"
    if not args.index and delegation.exists() and case in json.loads(delegation.read_text()):
        print(f"{case} assigned to other training host, skipping on this host")
        return
    if not args.index:
        collect(trial["side"], trial["goal"], trial["split"], RAW, evidence,
            hold_seconds=1.5, full_task=True, backend="warp", extra_final_park=True, trial=trial)
    index_teacher_clock(trial, RAW, OUT)


def index_teacher_clock(trial, raw, out):
    case=trial["episode_id"]
    evidence=out/(case+".json")
    tr = json.loads(evidence.read_text())
    folder = raw / case
    clock = np.load(folder/"t.npy")
    steps = np.load(folder/"physics_step.npy")
    if not np.isfinite(clock).all() or not np.all(np.diff(clock) > 0):
        raise ValueError("Invalid physical times")
    frozen = FROZEN / f'{trial["side"]}_{trial["goal"]}_train'
    ref = json.loads((frozen/"summary.json").read_text())
    md = json.loads((folder/"metadata.json").read_text())
    if md["condition"] != case or md["wm_split"] != trial["split"]:
        raise ValueError("Invalid split or condition identity")
    np.testing.assert_allclose(np.load(folder/"actual_dt.npy"), np.diff(steps)*.002, atol=1e-8)
    if len(steps) != len(np.load(folder/"action_clipped.npy"))+1:
        raise ValueError("Missing transition successor")
    phase_table = np.asarray(md["phases"])
    phase = phase_table[np.load(folder/"phase.npy")]
    ref_metadata = json.loads((frozen/"metadata.json").read_text())
    ref_phase = np.asarray(ref_metadata["phases"])[np.load(frozen/"phase.npy")]
    def phase_ends(path, meta, completed):
        sub = np.load(path/"substeps"/"phase.npy",mmap_mode="r")
        ends = np.r_[1+np.flatnonzero(np.diff(sub)),len(sub)]
        return {meta["phases"][int(sub[end-1])]:int(end) for end in ends
                if meta["phases"][int(sub[end-1])] in completed}
    actual_end = phase_ends(folder, md, tr["event_end_steps"])
    ref_end = phase_ends(frozen, ref_metadata, [e["phase"] for e in ref["events"]])
    timing = {p:round((end-ref_end[p])*.002,6) for p,end in actual_end.items() if p in ref_end}

    ref_valid = np.load(frozen/"valid_full_interval.npy")
    shared = min(len(phase),len(ref_phase))
    aligned = np.zeros(len(phase),dtype=bool)
    aligned[:shared] = (phase[:shared] == ref_phase[:shared]) & ref_valid[:shared]
    pulse = np.zeros_like(aligned)
    pulse[np.flatnonzero(phase == "hold")[:trial["hold_open_policy_ticks"]]] = True
    # HeldTeacher selects with the new physical phase at substep 10*k, even
    # if phase transition occurred between the two previous boundaries.
    valid = np.load(folder/"valid_full_interval.npy")
    safe = np.ones_like(aligned)
    if tr["first_failure_interval"] is not None:
        safe = steps[1:] <= tr["first_failure_interval"]
    positive = valid & aligned & safe & ~pulse
    for name,values in [("intervention",pulse),("reference_phase_match",aligned),("bc_positive_mask",positive)]:
        np.save(folder/(name+".npy"),values,allow_pickle=False)
    import socket
    md.update(collector_hostname=md.get("collector_hostname",socket.gethostname()), condition=case, reference_identity=frozen.name,
              fixed_reference_directory=str(FROZEN), eligible_as_reference=False,
              augmented_teacher_generator_seed=231123,
              intervention_policy_frames=np.flatnonzero(pulse).tolist(),
              supervision_mask="bc_positive_mask.npy; complete/nonterminal-failure-free, phase-matched to same side same clock, excluding open-pulse commands",
              scene_seed=None)
    (folder/"metadata.json").write_text(json.dumps(md,indent=2,allow_nan=False)+"\n")
    ev = dict(collector_hostname=md["collector_hostname"], episode=case, split=md["wm_split"], reference=frozen.name,
          phase_end_offset_s=timing, recorded_time_vs_integer_step_max_s=float(np.abs(clock-steps*.002).max()),
          policy_dt_s=.02, attempted_hold_open_ticks=trial["hold_open_policy_ticks"],
          initial_root_xy_m=md["initial_qpos"][:2], fixed_dt_transitions=tr["fixed_dt_transitions"],
          partial_substeps=tr["partial_terminal_substeps"], failure=tr["failure"],
          bc_positive_frames=int(positive.sum()), complete_phase_match=int((valid&aligned).sum()),
          complete_phase_mismatch_or_outside_reference=int((valid&~aligned).sum()),
          intervention_frames=np.flatnonzero(pulse).tolist(), failure_frames=np.flatnonzero(~safe).tolist(),
          clock_s_source="integer physical substeps at 2ms; completed phase ends are taken from dense per-substep phase, not rounded float time")
    clock_file = out / (case+"_clock.json")
    tmp = clock_file.with_suffix(".pending")
    tmp.write_text(json.dumps(ev,indent=2,allow_nan=False)+"\n")
    tmp.replace(clock_file)


if __name__ == "__main__":
    main()
