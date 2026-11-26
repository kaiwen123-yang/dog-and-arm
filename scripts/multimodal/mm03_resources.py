"""Reassign measured native capacity between complete batches without interrupting solvers."""
import argparse
import fcntl
import json
from pathlib import Path
import time

from scripts.multimodal.mm03_launch import DEFAULT, now, read, write


def update(root, b=None, c=None, reason=None):
    directory=root/"resources"
    directory.mkdir(exist_ok=True)
    with (directory/"allocation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        path=directory/"worker_targets.json"
        old=read(path)
        cfg=read(root/"launch_config.json")["workers"]
        target={k:old.get(k,cfg[k]) for k in ("B","C")}
        a_done=(root/"A/completion.json").is_file()
        c_done=(root/"C/selection.json").is_file()
        if b is None and c is None:
            if c_done and a_done:
                target.update(B=15)
                reason="A and the C native fork matrix have returned their physics slots"
            elif a_done:
                target.update(B=9,C=8)
                reason="A finished its last registered native batch; hand its slots to task collection and CF32"
            else:
                return old
        else:
            if not reason:
                raise ValueError("A manual allocation needs a measured reason")
            if b is not None:target["B"]=b
            if c is not None:target["C"]=c
        active_a=0 if a_done else cfg["A"]
        active_c=0 if c_done else target["C"]
        if min(target.values())<1 or active_a+target["B"]+active_c>22:
            raise ValueError("Native workers leave fewer than three of the 25 cores for shared work")
        if target=={k:old.get(k,cfg[k]) for k in ("B","C")}:
            return old
        generation=dict(**target,changed_beijing=now(),reason=reason,
            A_finished=a_done,C_finished=c_done,previous={k:old.get(k,cfg[k]) for k in ("B","C")},
            B_throughput_before=read(root/"B/physical_progress.json"),
            A_last_batch=read(root/"A/progress.json"),central_inference=read(root/"service/inference_stats.json"))
        write(path,generation)
        with (directory/"allocation_changes.jsonl").open("a") as f:
            f.write(json.dumps(generation,separators=(",",":"))+"\n")
        return generation


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=DEFAULT)
    p.add_argument("--b-workers",type=int)
    p.add_argument("--c-workers",type=int)
    p.add_argument("--reason")
    args=p.parse_args()
    print(json.dumps(update(args.root,args.b_workers,args.c_workers,args.reason),ensure_ascii=False))

