"""Run paired, preassigned physical cases with one native process per case."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
from pathlib import Path
import subprocess
import sys


def run(args):
    base=Path(__file__).resolve().parents[2]
    registration=json.loads((base/"config/multimodal/evaluation.json").read_text())
    cases=registration["comparison"]["formal_physics"]
    if args.feedback and args.branch!="common_12000":
        raise ValueError("Only the common trained parent supplies this round's interactive replay")
    if not args.feedback and args.branch not in cases["branches"]:
        raise ValueError("Unknown frozen branch")
    scenes=["tr_nominal"] if args.feedback else cases["scenes"]
    if args.feedback and args.partition!="all":
        raise ValueError("Training feedback has a single prespecified set of four cases")
    if args.partition=="development":
        scenes=[s for s in scenes if s!="te_combination"]
    elif args.partition=="test":
        scenes=[s for s in scenes if s=="te_combination"]
    tasks=list(itertools.product(scenes,registration["sides"],registration["goals_deg"]))
    output=args.run/("parent_cases" if args.feedback else "formal_cases")
    options=["--checkpoint",str(args.checkpoint),"--branch",args.branch,"--output",str(output),
             "--first-video-dir",str(args.run/"videos/student")]
    if args.feedback:
        options+=["--feedback-dir",str(args.run/"data")]
    def one(task):
        scene,side,goal=task
        name=f"{args.branch}_{scene}_{side}_{goal}"
        command=[sys.executable,"-m","scripts.multimodal.evaluate",*options,
                 "--scene",scene,"--side",side,"--goal",str(goal)]
        with (args.run/"logs"/f"{name}.log").open("x") as log:
            ret=subprocess.run(command,cwd=base,stdout=log,stderr=subprocess.STDOUT).returncode
        if ret:
            return dict(case_id=name,command=command,process_exit=ret)
        record=json.loads((output/name/"result.json").read_text())
        print(json.dumps({k:record[k] for k in ("case_id","success","next_phase","physics_steps")}),flush=True)
        return record
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows=list(pool.map(one,tasks))
    (args.run/f"{args.branch}_{args.partition}_physics.json").write_text(json.dumps(rows,indent=2,allow_nan=False)+"\n")
    if any(x.get("process_exit") for x in rows):
        raise RuntimeError("A physical case did not produce a judgment; see its log")
    for ix in range(0,len(rows),2):
        if rows[ix]["initial_state_sha256"]!=rows[ix+1]["initial_state_sha256"]:
            raise ValueError("Two instructions did not receive identical reset states")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--branch",required=True)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--partition",choices=["all","development","test"],default="all")
    p.add_argument("--feedback",action="store_true")
    run(p.parse_args())
