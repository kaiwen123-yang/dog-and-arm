"""Check the clock-independent MM-01 judge on full physically driven P6 runs."""
import argparse
import json
from pathlib import Path

from learning.multimodal.judge import DoorTaskJudge
from scripts.b0.collect_contact import HeldTeacher
from scripts.multimodal.collect_feasibility import teacher_config
from p6_single_door import run


def check(side, goal, output):
    output.mkdir(parents=True, exist_ok=False)
    cfg = teacher_config(side, goal)
    judge = None
    def observe(model, data, t, q, v, target, phase, contacts):
        nonlocal judge
        if judge is None:
            judge = DoorTaskJudge(model, cfg, side, goal)
        if not (judge.passed or judge.failure):
            judge.observe(data, q, v, contacts)
    physical = run(cfg, output, False, False, False, held_teacher=HeldTeacher(), step_observer=observe)
    result = dict(side=side,target_deg=goal,source="P6_held_20ms_score_check",p6_complete=physical,**judge.result())
    (output/"mm01_judgment.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:result[k] for k in ("side","target_deg","p6_complete","success","first_failure")}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("side", choices=["pull","push"])
    p.add_argument("goal", type=int, choices=[15,25])
    p.add_argument("output", type=Path)
    args=p.parse_args()
    check(args.side,args.goal,args.output)
