"""Independent native 3.3.0 frame-zero evaluation of frozen C optimization forks."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path

from scripts.multimodal.mm02_physics import execute, emit
from scripts.multimodal.mm02_suite import DEV, jobs
from scripts.multimodal.mm03_inference import PolicyClient


def case(item):
    root,job = item
    client = PolicyClient(job["checkpoint"],kind="mm02")
    try:
        return execute(root,job,client=client)
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
    with ProcessPoolExecutor(args.workers) as executor:
        rows = list(executor.map(case,((args.root,job) for job in matrix)))
    for row in rows:
        if row["teacher_steps"] or row["mode"] != "pure" or row["parent_tick"] != 0:
            raise ValueError("Not a frame0 pure-student development episode")
    emit(args.root/group/"cases.json",rows)
    for row in rows:
        if row["success"]:
            path = args.root/"videos/first_success.json"
            if path.is_file() and Path(json.loads(path.read_text())["episode"])==Path(row["raw_episode"]):
                base = dict(next(j for j in matrix if j["id"]==row["id"]))
                replicates=[]
                for copy in (1, 2):
                    job=dict(base,partition=group+"/independent_reload",id=base["id"]+f"_reload{copy}")
                    # Fresh service key uses an independently loaded copy of the frozen package.
                    reload_path=args.root/group/f"reload{copy}.pt"
                    if not reload_path.exists():
                        reload_path.hardlink_to(args.checkpoint)
                    job["checkpoint"]=str(reload_path)
                    replicates.append(case((args.root,job)))
                emit(args.root/group/"first_success_reloads.json",replicates)


if __name__=="__main__":
    main()
