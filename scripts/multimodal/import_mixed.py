"""Re-render the archived, scored native 546-channel mixed trajectory as training-only data."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from learning.b0.physics import build
from scripts.multimodal.collect import EpisodeWriter, load_scenes


def convert(source, destination):
    lineage = json.loads((source / "source.json").read_text())
    result = json.loads((source / "result.json").read_text())
    if not result["passed"] or result["first_failure"] or result["side"] != "push":
        raise ValueError("Expected the completed archived native push trajectory")
    arrays = {}
    for name, entry in lineage["files"].items():
        path = source / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Historical array mismatch: {path}")
        arrays[path.stem] = np.load(path, mmap_mode="r")
    cfg = result["actual_config"]
    goal = int(cfg["target_angle_deg"])
    scene = next(row for row in load_scenes()["scenes"] if row["id"] == "tr_nominal")
    if cfg["perturbation"] != scene["perturbation"] or goal != 25:
        raise ValueError("Historical task does not equal the registered training condition")
    model = build(cfg)
    name = "tr_nominal_push_25_mixed_native_u1"
    output = EpisodeWriter(model, cfg, scene, "push", goal, name, "legacy_546_hybrid_u1")
    q, v, ticks = (arrays[key] for key in ("qpos", "qvel", "physics_step"))
    raw, clipped, events = (arrays[key] for key in ("raw_action", "clipped_action", "physical_events_2ms"))
    columns = result["physical_event_columns"]
    fingers = [columns.index("finger1_n"), columns.index("finger2_n")]
    pid = columns.index("phase_id")
    if ticks[0] != 0 or ticks[-1] != len(events) or len(q) != len(v) or len(ticks) != len(raw)+1:
        raise ValueError("Incomplete archived trajectory")
    if not np.array_equal(events[:,columns.index("step")], np.arange(1,len(events)+1)):
        raise ValueError("Physical event steps do not align with the saved states")
    try:
        for k, (begin, end) in enumerate(zip(ticks[:-1], ticks[1:])):
            output.boundary(float(begin*model.opt.timestep),q[k],v[k])
            phase = result["phases"][int(events[begin,pid])]
            output.action(raw[k],clipped[k],output.mapping.offset+output.mapping.scale*clipped[k],
                          phase,supervised=True)
            for j in range(begin,end):
                output.substep(None,events[j,fingers])
        output.boundary(float(ticks[-1]*model.opt.timestep),q[-1],v[-1])
        meta = output.save(destination/name,True,None,extra=dict(
            source_lineage=lineage, physical_judge_source=lineage["result_path"],
            last_phase="final", teacher_events=result["events"],
            image_source="synthetic wrist re-render of archived, integrated native 3.3.0 states",
            applied_ctrl_available=False,
            teacher="546-goal mixed u1, reference feedforward, prior 15000 action-BC steps and analytical stance compensation",
            actions_source="verified archived raw and post-clamp actions, physically executed at original policy rate"))
        print(json.dumps({k:meta[k] for k in ("episode_id","valid_transitions","bc_labels","frames","final_hinge_deg")}))
    finally:
        output.sensors.close()


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("destination", type=Path)
    args=p.parse_args()
    convert(args.source, args.destination)
