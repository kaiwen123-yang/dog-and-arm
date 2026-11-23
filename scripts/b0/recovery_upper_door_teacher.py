"""Probe independent lower-pull or upper-push training angles with the same corrected physical teacher."""
import argparse
from functools import partial
import json
from pathlib import Path

import numpy as np

from scripts.b0.recovery_teacher import FROZEN,index_teacher_clock

DESIGN=Path("config/b0/recovery_endpoint_upper_angle.json")
RAW=Path("results/raw_large/b0/recovery_endpoint_upper_r1")
OUT=Path("results/b0/recovery_endpoint_upper_r1")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--register",action="store_true")
    p.add_argument("--pull-low",action="store_true",help="independent small-angle front pull using the same frozen-clock endpoint teacher")
    a=p.parse_args()
    design=DESIGN.with_name("recovery_endpoint_lower_pull.json") if a.pull_low else DESIGN
    raw=RAW.with_name("recovery_endpoint_lower_pull_r1") if a.pull_low else RAW
    out=OUT.with_name("recovery_endpoint_lower_pull_r1") if a.pull_low else OUT
    side,goal,seed,limits=(("pull",60,2026112306,(1.,2.6)) if a.pull_low else ("push",25,2026112305,(4.,4.8)))
    name="lower_pull_train_01" if a.pull_low else "upper_push_train_01"
    if a.register:
        trial=dict(side=side,goal=goal,split="train",family="lower_pull_door_angle" if a.pull_low else "upper_door_angle",episode_id=name,
                   perturbation=dict(door=float(np.random.default_rng(seed).uniform(*limits))),hold_open_policy_ticks=0)
        with design.open("x") as f:
            json.dump(dict(seed=seed,draw=f"first and sole PCG64 uniform[{limits[0]},{limits[1]}) degree draw, retain independent of outcome",
                     trial=trial,reference=str(FROZEN),teacher_variant="endpoint + frozen earliest release; same as push r2",
                     added_to_A0_A3=False),f,indent=2)
        return
    from scripts.b0.collect_contact import collect
    from scripts.b0.recovery_endpoint_teacher import EndpointTeacher
    from scripts.b0.score_recovery_teacher_clock import score
    trial=json.loads(design.read_text())["trial"]
    ep=trial["episode_id"]
    out.mkdir(parents=True,exist_ok=True)
    collect(side,goal,"train",raw,out/(ep+".json"),hold_seconds=1.5,full_task=True,backend="warp",
            extra_final_park=True,trial=trial,arm_factory=partial(EndpointTeacher,match_release=True))
    audit=score(raw/ep,FROZEN/f"{side}_{goal}_train",side)
    with (out/(ep+"_frozen_judge.json")).open("x") as f:
        f.write(json.dumps(audit,indent=2,allow_nan=False)+"\n")
    index_teacher_clock(trial,raw,out)
    md=raw/ep/"metadata.json"
    obj=json.loads(md.read_text())
    obj["augmented_teacher_generator_seed"]=json.loads(design.read_text())["seed"]
    md.write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
    print(ep,audit["frozen_judge_pass"],audit["frozen_judge_first_failure"],flush=True)


if __name__=="__main__":
    main()
