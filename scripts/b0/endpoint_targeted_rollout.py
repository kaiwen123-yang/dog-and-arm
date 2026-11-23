"""Run one separately identified full-task physical episode with the frozen endpoint policy."""
import argparse
import json
from pathlib import Path

from learning.b0.contact_policy import load_policy
from scripts.b0.eval_contact_segments import evaluate_segment
from scripts.b0.fit_endpoint_policy import FROZEN, REF


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",required=True)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--side",required=True,choices=tuple(REF))
    p.add_argument("--case",type=int,required=True)
    a=p.parse_args()
    if Path(a.run).name!=a.run or not 1<=a.case<=20:
        p.error("use a named run and a registered C01–C20")
    out=Path("results/b0")/a.run
    raw=Path("results/raw_large/b0")/a.run
    paths=[FROZEN/r for r in REF.values()]
    ep=FROZEN/REF[a.side]
    policy=load_policy(a.checkpoint,paths,"cuda:0")
    label="nominal" if a.case==1 else f"C{a.case:02d}"
    relative=Path(a.side)/"full"/label
    row=evaluate_segment(policy,ep,"full",dict(p6_case=a.case),"warp",out/relative,
             device="cuda:0",raw_dir=raw/relative,video=True)
    with (out/relative/"policy_source.json").open("x") as f:
        json.dump(dict(checkpoint=str(a.checkpoint),references=[str(x) for x in paths],p6_case=a.case,
             evaluation="standard evaluate_segment(full,backend=warp) from continuous_initial; no teacher"),f,indent=2)
    print(a.side,label,row["passed"],row["first_failure"],flush=True)


if __name__=="__main__":
    main()
