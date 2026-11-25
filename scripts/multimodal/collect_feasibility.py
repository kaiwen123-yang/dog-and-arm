"""Screen full P6 teacher trajectories for instruction-conditioned MM-01 tasks."""
import argparse
import json
from pathlib import Path

from scripts.b0.collect_contact import HeldTeacher
from p6_scene import settings
from p6_single_door import run


def teacher_config(side, goal, scene=None):
    cfg = settings("mobile" if side == "pull" else "push", 1)
    cfg.update(target_angle_deg=float(goal), grip_hold_s=1.5,
               segment_end_after_retreat_hold=False, policy_decimation=10)
    cfg["final_reference_hold_s"] = cfg["post_hold_s"] + 1.0
    if scene is not None:
        cfg.update(case=scene["id"], perturbation=dict(scene["perturbation"]))
    return cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=["pull", "push"], required=True)
    parser.add_argument("--goal", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    cfg = teacher_config(args.side, args.goal)
    run(cfg, args.out, False, False, False, held_teacher=HeldTeacher())
    summary = json.loads((args.out / "summary.json").read_text())
    print(json.dumps({k: summary[k] for k in (
        "target_deg", "final_deg", "stage_pass", "task_success",
        "last_phase", "failure", "physics_steps", "wall_s")}), flush=True)


if __name__ == "__main__":
    main()
