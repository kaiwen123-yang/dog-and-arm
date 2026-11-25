"""Issue the registered paired task matrix and sample distinct real recovery anchors."""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from itertools import product
import json
from pathlib import Path
import pickle

import numpy as np

from learning.multimodal.sensors import RobotSensors
from scripts.multimodal.mm02_physics import (PolicyPipe, TORCH, digest, emit, execute, init_resources, scenes)

TRAIN = ("tr_nominal","tr_offset","tr_load")
DEV = ("tr_nominal","va_pose")
FORMAL = (*DEV,"te_combination","te_mm02_combo_a","te_mm02_combo_b")
BRANCHES = ("supervised_aggregate","model_trajectory")


@lru_cache(maxsize=2)
def policy(checkpoint):
    return PolicyPipe(TORCH,checkpoint)


def run_case(task):
    run, job = task
    result = execute(run,job,client=policy(job["checkpoint"]))
    print(job["id"], result["success"],result["ordered_event_count"], result["physics_steps"],flush=True)
    return result


def jobs(run,partition,branches,scene_ids,round_no,modes=("pure",),snapshots=False):
    output = []
    for (branch,checkpoint),scene,side,goal,mode in product(branches.items(),scene_ids,("pull","push"),(15,25),modes):
        source = Path(checkpoint).resolve()
        seed = np.random.SeedSequence([22020+round_no,list(scenes()).index(scene),int(side=="push"),
                                       int(goal)]).generate_state(1)[0]
        keep = snapshots and (partition.endswith("collection") or scene=="va_pose")
        name = "_".join((partition.replace("/","_"),branch,scene,side,str(goal),mode))
        output.append(dict(id=name,partition=partition,branch=branch,scene=scene,side=side,
                           goal=goal,mode=mode,round=round_no,checkpoint=str(source),
                           sha=digest(source.read_bytes()),seed=int(seed),
                           probability=[0,.75,.50,.25,.10,.10,.10][round_no] if mode=="mixed" else 0.,
                           snapshot_count=12 if keep else 0))
    return output


def run_suite(run, cases, workers):
    if any(j["scene"].startswith("te_mm02") for j in cases):
        if not (Path(run)/"terminal_freeze.json").is_file():
            raise ValueError("The terminal freeze and extension decision must precede student blind evaluation")
    with ProcessPoolExecutor(workers) as pool:
        rows = list(pool.map(run_case,((run,job) for job in cases)))
    by = defaultdict(set)
    for row in rows:
        by[(row["branch"],row["scene"],row["side"],row["mode"])].add(row["initial_state_sha256"])
    if any(len(v)!=1 for v in by.values()):
        raise ValueError("Goal-paired resets differ")
    return rows


def choose(cases, max_count, seed):
    groups = defaultdict(list)
    for c in cases:
        p = Path(c["raw_episode"]).parent/"candidates.json"
        if p.exists():
            for a in json.loads(p.read_text()):
                groups[(a["scene"],a["side"],a["goal"],a["phase"],a["branch"],a["mode"])].append(a)
    rng = np.random.default_rng(seed)
    for group in groups.values():
        rng.shuffle(group)
    keys = list(groups)
    rng.shuffle(keys)
    result, used = [],set()
    while any(groups.values()) and len(result)<max_count:
        for key in keys:
            if len(result)==max_count:
                break
            while groups[key]:
                a=groups[key].pop()
                if a["key"] not in used:
                    result.append(a)
                    used.add(a["key"])
                    break
    return result


def recover_group(args):
    run, partition, round_no, picks = args
    first_parent = None
    sensors = None
    rows = []
    try:
        for choice in picks:
            with open(choice["path"],"rb") as f:
                anchor = pickle.load(f)
            parent = anchor["parent"]
            if first_parent is None:
                resources = init_resources(parent)
                scene,cfg,model,_,_,_ = resources
                sensors = RobotSensors(model,cfg["handle_site"],scene.get("panel_rgb"))
                first_parent = parent["id"]
            if parent["id"]!=first_parent:
                raise ValueError("A restored group must have one model/task identity")
            job = dict(parent,partition=partition,round=round_no,mode="recovery",snapshot_count=0,
                       id=f'r{round_no}_{parent["id"]}_a{anchor["tick"]}')
            rows.append(execute(run,job,anchor=anchor,sensors=sensors,
                                client=policy(job["checkpoint"]),resources=resources))
    finally:
        if sensors:
            sensors.close()
    return rows


def recover(run,partition,round_no,cases,limit,workers):
    is_val = partition.endswith("validation")
    if any(c["scene"] not in (("va_pose",) if is_val else TRAIN) for c in cases):
        raise ValueError("Recovery source partition differs from the registered split")
    picks = choose(cases,limit,22020+round_no+int(is_val))
    emit(Path(run)/partition/"selection.json",picks)
    groups = defaultdict(list)
    for p in picks:
        groups[p["parent"]].append(p)
    with ProcessPoolExecutor(workers) as pool:
        rows = [row for group in pool.map(recover_group,
                ((run,partition,round_no,g) for g in groups.values())) for row in group]
    emit(Path(run)/partition/"cases.json",rows)
    return rows


if __name__=="__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run",type=Path)
    parser.add_argument("partition")
    parser.add_argument("checkpoint")
    parser.add_argument("--branch",default="common_12000")
    parser.add_argument("--workers",type=int,default=8)
    parser.add_argument("--scene",choices=tuple(scenes()))
    parser.add_argument("--side",choices=("pull","push"))
    parser.add_argument("--goal",type=int,choices=(15,25))
    parser.add_argument("--round",type=int,default=0,choices=range(7))
    args=parser.parse_args()
    case_scenes=(args.scene,) if args.scene else TRAIN
    requests=jobs(args.run,args.partition,{args.branch:args.checkpoint},case_scenes,args.round)
    requests=[job for job in requests if (not args.side or job["side"]==args.side)
              and (not args.goal or job["goal"]==args.goal)]
    rows=run_suite(args.run,requests,min(args.workers,len(requests)))
    emit(args.run/args.partition/"cases.json",rows)
