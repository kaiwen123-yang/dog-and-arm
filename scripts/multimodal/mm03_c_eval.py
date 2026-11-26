"""Independent native 3.3.0 frame-zero evaluation of frozen C optimization forks."""
import argparse
from concurrent.futures import ProcessPoolExecutor

from pathlib import Path

from scripts.multimodal.mm02_physics import execute, emit
from scripts.multimodal.mm02_suite import DEV, jobs
from scripts.multimodal.mm03_inference import PolicyClient


def case(item):
    root,job = item
    client = PolicyClient(job["checkpoint"],kind="mm02")
    try:
        row = execute(root,job,client=client,deliver_success=False)
        if row["success"] and row["teacher_steps"] == 0 and row["parent_tick"] == 0 and "reload" not in job["id"]:
            directory = Path(row["raw_episode"])
            emit(root/"C"/"success"/(job["id"]+".json"),
                 dict(case=str(directory.parent/"result.json"), episode=str(directory),
                      checkpoint=job["checkpoint"], method=job["branch"],training_seed=job["training_seed"],
                      case_seed=job["seed"]))
        return row
    finally:
        client.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("variant")
    p.add_argument("seed",type=int)
    p.add_argument("checkpoint",type=Path)
    p.add_argument("--workers",type=int,required=True)
    args=p.parse_args()
    group = f"C/{args.variant}/seed{args.seed}/development"
    matrix = jobs(args.root,group,{args.variant:args.checkpoint},DEV,0)
    for job in matrix:
        job["training_seed"] = args.seed
    with ProcessPoolExecutor(args.workers) as executor:
        rows = list(executor.map(case,((args.root,job) for job in matrix)))
    for row in rows:
        if row["teacher_steps"] or row["mode"] != "pure" or row["parent_tick"] != 0:
            raise ValueError("Not a frame0 pure-student development episode")
    emit(args.root/group/"cases.json",rows)



if __name__=="__main__":
    main()
