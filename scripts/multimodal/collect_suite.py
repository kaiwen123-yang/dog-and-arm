"""Collect the registered P6 episodes, retaining failures, masks and physical receipts."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import contextlib
import json
import multiprocessing as mp
from pathlib import Path
import time

from scripts.multimodal.collect import SCENES, collect_case, load_scenes


def cases(recovery=False):
    spec = load_scenes()
    if recovery:
        extra = json.loads((SCENES.parent/"scenes_recovery.json").read_text())
        scene = next(s for s in spec["scenes"] if s["id"] == extra["scene"])
        return [(scene, side, extra["target_deg"], probe) for side in extra["sides"] for probe in extra["probes"]]
    rows = [(scene, side, goal, {}) for scene in spec["scenes"]
            for side in spec["sides"] for goal in spec["goal_deg"]]
    for item in spec["training_interventions"]:
        scene = next(s for s in spec["scenes"] if s["id"] == item["scene"])
        rows.append((scene, item["side"], item["goal"], item))
    return rows


def run_one(root, row):
    scene, side, goal, intervention = row
    eid = f"{scene['id']}_{side}_{goal}_{intervention.get('name','held')}"
    saved = root / "data" / eid / "metadata.json"
    if saved.exists():
        result = json.loads(saved.read_text())
        if (result["episode_id"], result["split"], result["target_deg"]) != (eid, scene["split"], goal):
            raise ValueError(f"Invalid saved identity for {eid}")
    else:
        logpath = root / "logs" / f"data_{eid}.log"
        with logpath.open("a", buffering=1) as stream, contextlib.redirect_stdout(stream):
            result = collect_case(root/"data", root/"teacher-physics", scene, side, goal, intervention)
    fields = ("episode_id", "scene_id", "split", "side", "target_deg", "source", "success", "failure",
              "last_phase", "physics_steps", "valid_transitions", "bc_labels", "frames", "episode_wall_s",
              "image_wall_s", "depth_valid_fraction", "both_contact_intervals", "final_hinge_deg",
              "overridden_action_indices")
    return {key: result[key] for key in fields}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--recovery", action="store_true", help="Run the separate four training-scene recovery probes")
    args = parser.parse_args()
    (args.root/"logs").mkdir(parents=True, exist_ok=True)
    rows = cases(args.recovery)
    t0 = time.monotonic()
    results = []
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context("spawn")) as pool:
        futures = [pool.submit(run_one, args.root, row) for row in rows]
        for job in as_completed(futures):
            row = job.result()
            results.append(row)
            print(json.dumps(row), flush=True)
    data = dict(workers=args.workers, wall_s=time.monotonic()-t0, completed=len(results),
                rows=sorted(results, key=lambda r: r["episode_id"]))
    (args.root/"teacher_dataset.json").write_text(json.dumps(data, indent=2)+"\n")


if __name__ == "__main__":
    main()
