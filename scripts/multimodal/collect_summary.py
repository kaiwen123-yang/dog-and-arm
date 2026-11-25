"""Summarize the executed MM-01 teacher split and its same-state goal pairs."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

import numpy as np


def summarize(root):
    inventory = json.loads((root / "teacher_dataset.json").read_text())
    rows = inventory["rows"]
    grouped = defaultdict(list)
    by_split = {}
    pairs = []
    dimensions = {}
    max_age = 0.
    disk_bytes = 0
    for row in rows:
        episode = root / "data" / row["episode_id"]
        meta = json.loads((episode / "metadata.json").read_text())

        def array(key):
            return np.load(episode / f"{key}.npy", mmap_mode="r", allow_pickle=False)

        t, a, prev = array("t"), array("action_clipped"), array("previous_action")
        stamps, indices = array("image_t"), array("image_index")
        if (not np.array_equal(prev[1:], a) or np.any(prev[0] != 0)
                or not np.array_equal(indices, np.searchsorted(stamps, t, side="right")-1)):
            raise ValueError(f"Image or executed action misalignment in {episode.name}")
        if np.any(array("action_supervision_mask") & ~array("valid_transition")):
            raise ValueError(f"Incomplete teacher labels in {episode.name}")
        valid = np.asarray(array("valid_transition"))
        if not np.isfinite(array("applied_ctrl")[valid]).all():
            raise ValueError(f"Missing sent servo control in {episode.name}")
        depth, mask = array("depth"), array("depth_valid")
        if np.any(depth[~mask] != 0) or np.any(depth[mask] < .05) or np.any(depth[mask] > 5):
            raise ValueError(f"Invalid depth encoding in {episode.name}")
        max_age = max(max_age, float(np.max(t - stamps[indices])))
        total = by_split.setdefault(meta["split"], {
            "episodes": 0, "successes": 0, "physics_steps": 0, "full_transitions": 0,
            "action_supervision_labels": 0, "frames": 0, "bilateral_contact_intervals": 0})
        for dst, value in [
                ("episodes", 1), ("successes", meta["success"]), ("physics_steps", meta["physics_steps"]),
                ("full_transitions", valid.sum()), ("action_supervision_labels", meta["bc_labels"]),
                ("frames", len(stamps)), ("bilateral_contact_intervals", meta["both_contact_intervals"])]:
            total[dst] += int(value)
        if meta["source"] == "P6_held_20ms":
            grouped[(meta["scene_id"], meta["side"])].append((episode, meta))
        for key in ("rgb", "depth", "proprio", "action_clipped", "applied_ctrl", "object_state", "contact"):
            dimensions[key] = list(array(key).shape[1:])
        disk_bytes += sum(f.stat().st_size for f in episode.iterdir() if f.is_file())
    for (scene_id, side), group in sorted(grouped.items()):
        (p, low), (q, high) = sorted(group, key=lambda e: e[1]["target_deg"])
        same = {}
        for key in ("qpos", "qvel", "rgb", "depth", "depth_valid", "proprio", "previous_action"):
            x, y = [np.load(base / f"{key}.npy", mmap_mode="r") for base in [p, q]]
            same[key] = bool(np.array_equal(x[0], y[0]))
        if not all(same.values()):
            raise ValueError(f"Inputs differ at the reset of {scene_id}/{side}: {same}")
        a, b = [np.load(base/"action_clipped.npy", mmap_mode="r") for base in [p, q]]
        n = min(len(a), len(b))
        difference = np.max(np.abs(a[:n]-b[:n]), axis=1)
        changed = np.flatnonzero(difference > 1e-5)
        pairs.append(dict(scene_id=scene_id, side=side, split=low["split"], target_deg=[low["target_deg"], high["target_deg"]],
                          first_action_difference_gt_1e_minus_5_s=float(changed[0]*.02) if len(changed) else None,
                          max_normalized_action_difference=float(difference.max()), initial_arrays_equal=same,
                          final_angle_deg=[low["final_hinge_deg"], high["final_hinge_deg"]],
                          full_success=[low["success"], high["success"]]))
    scenes = {split: sorted({r["scene_id"] for r in rows if r["split"] == split}) for split in by_split}
    if len({s for ids in scenes.values() for s in ids}) != sum(map(len, scenes.values())):
        raise ValueError("A physical scene crosses dataset splits")
    return dict(by_split=by_split, scene_ids=scenes, distinct_primary_scene_side_goal_pairs=pairs,
                dimensions_after_time=dimensions, max_input_frame_age_s=max_age, episode_bytes=disk_bytes,
                wall_s=inventory["wall_s"], aggregate_valid_transitions_per_wall_s=(
                    sum(v["full_transitions"] for v in by_split.values()) / inventory["wall_s"]),
                action_history_image_depth_and_valid_servo_rows_verified=len(rows))


def summarize_recovery(root):
    inventory = json.loads((root/"teacher_dataset.json").read_text())
    for row in inventory["rows"]:
        path = root/"data"/row["episode_id"]
        indices = np.asarray(row["overridden_action_indices"])
        first, last = int(indices.min()), int(indices.max())
        fraction = np.load(path/"both_contact_fraction.npy")
        steps = np.load(path/"substeps.npy")
        times = np.load(path/"t.npy")
        mask = np.load(path/"action_supervision_mask.npy")
        loads = np.load(path/"contact.npy")
        later = np.flatnonzero(fraction[last+1:] == 1.)
        regained = last + 1 + int(later[0]) if len(later) else None
        missing = int(np.rint(((1-fraction[indices])*steps[indices]).sum()))
        dt = float(json.loads((path/"metadata.json").read_text())["physics_dt_s"])
        row["recovery_event"] = dict(
            override_first_step=first, override_last_step=last, initial_bilateral_fraction=float(fraction[first-1]),
            bilateral_contact_fraction_by_override_tick=fraction[indices].tolist(),
            finger_peak_N_by_override_tick=loads[indices].tolist(),
            missing_bilateral_substeps_in_intervention=missing,
            no_bilateral_contact_s_in_intervention=missing*dt,
            first_fully_bilateral_after_nominal_resume=regained,
            time_to_end_of_first_full_contact_interval_after_nominal_resume_s=(
                float(times[regained+1]-times[last+1]) if regained is not None else None),
            all_override_labels_masked=bool(not mask[indices].any()),
            confirmed=bool(fraction[first-1] == 1 and missing > 0 and regained is not None and row["success"]))
    inventory.update(raw_root=str(root), registration=json.loads((root/"registration.json").read_text()),
                     role="independent train-scene recovery development data, excluded from both frozen comparison branches")
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--recovery", action="store_true")
    args = parser.parse_args()
    if args.recovery:
        result = summarize_recovery(args.root)
        name = "recovery_evidence.json"
        print({r["episode_id"]: r["recovery_event"]["confirmed"] for r in result["rows"]})
    else:
        result = summarize(args.root)
        name = "teacher_data_summary.json"
        print(json.dumps(result["by_split"]))
    (args.root/name).write_text(json.dumps(result, indent=2)+"\n")


if __name__ == "__main__":
    main()
