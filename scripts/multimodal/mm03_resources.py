"""Reassign measured native capacity between complete batches without interrupting solvers."""
import argparse
import fcntl
import json
from pathlib import Path
import time

from scripts.multimodal.mm03_launch import DEFAULT, now, read, write


def update(root, b=None, c=None, reason=None, b_gpu=None, b_cf=None, cf_slots=None, elastic=None):
    from scripts.multimodal.mm03_elastic import configure_locked,reconcile_locked
    directory=root/"resources"
    directory.mkdir(exist_ok=True)
    with (directory/"allocation.lock").open("a") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        path=directory/"worker_targets.json"
        old=read(path)
        if (b is None and c is None and b_gpu is None and b_cf is None and cf_slots is None
                and old.get("reason")=="R28 ordinary collection width trial"):
            from scripts.multimodal.mm03_elastic import pid_stamp
            lease=read(directory/"ordinary_width_trial.json")
            valid=(lease.get("active") and lease.get("pid_stamp")
                   and lease["pid_stamp"]==pid_stamp(lease.get("pid")))
            if not valid or (root/"B/rounds/r28/collection_complete.json").exists():
                b,b_cf,cf_slots=4,6,3
                reason="Restore CF32 seed slots after the ordinary collection trial"
        if (b is None and c is None and b_gpu is None and b_cf is None and cf_slots is None
                and old.get("reason")=="Scoped R8 seed1702 single-tail test with two completed sibling receipts"):
            from scripts.multimodal.mm03_elastic import pid_stamp
            lease=read(directory/"CF_single_tail.json")
            stage=root/"B/rounds/r08/H9-WM/seed1702/paired"
            valid=(lease.get("phase")=="trial" and lease.get("pid_stamp")
                   and lease["pid_stamp"]==pid_stamp(lease.get("pid")) and lease.get("stage")==str(stage))
            if not valid or (stage/"receipt.json").is_file():
                b,b_cf,cf_slots=4,6,3
                reason="Return the completed or abandoned single-seed loan to the measured three-seed layout"
        if elastic is not None:
            configure_locked(root,elastic,reason)
        cfg=read(root/"launch_config.json")["workers"]
        prior={k:old.get(k,cfg[k]) for k in ("B","C")}
        prior["B_CF"]=old.get("B_CF",0)
        prior["B_GPU"]=old.get("B_GPU",2)
        prior["B_CF_slots"]=old.get("B_CF_slots",1)
        target=prior.copy()
        a_done=(root/"A/completion.json").is_file()
        c_done=(root/"C/selection.json").is_file()
        frozen=(root/"B/candidate_freeze.json").is_file()
        if b is None and c is None and b_gpu is None and b_cf is None and cf_slots is None:
            if old and old.get("A_finished")==a_done and old.get("C_finished")==c_done and old.get("candidates_frozen",False)==frozen:
                return reconcile_locked(root,old)
            if c_done and a_done:
                winner=read(root/"C/selection.json").get("selected_model_variant")
                reserve_cf=winner=="CF32" and not frozen
                target.update(B=6 if reserve_cf else 15,B_CF=8 if reserve_cf else 0,
                              B_CF_slots=2 if reserve_cf else 1,B_GPU=3)
                reason=f"A and C returned their slots; task collection and {winner} paired optimization share the native budget"
                result=read(root/"performance/cf32-three-seeds-20261126/decision.json") if reserve_cf else {}
                if result.get("winner") in ("two","three"):
                    measured=result["retained_target"]
                    target.update({key:measured[key] for key in ("B","B_CF","B_CF_slots","B_GPU")})
                    reason="Restore the faster measured H9-WM seed configuration for this run"
            elif a_done:
                target.update(B=9,C=8)
                reason="A finished its last registered native batch; hand its slots to task collection and CF32"
            else:
                return reconcile_locked(root,old)
        else:
            if not reason:
                raise ValueError("A manual allocation needs a measured reason")
            if b is not None:target["B"]=b
            if c is not None:target["C"]=c
            if cf_slots is not None:
                if not c_done or read(root/"C/selection.json").get("selected_model_variant")!="CF32" or not 1<=cf_slots<=3:
                    raise ValueError("Native pairing concurrency requires the selected CF32 method")
                target["B_CF_slots"]=cf_slots
            if b_cf is not None:
                if not c_done or read(root/"C/selection.json").get("selected_model_variant")!="CF32" or b_cf<1:
                    raise ValueError("A positive B_CF share requires the frozen CF32 selection")
                target["B_CF"]=b_cf
            if b_gpu is not None:
                if not 1<=b_gpu<=3:
                    raise ValueError("There are three independent B seeds")
                target["B_GPU"]=b_gpu
        active_a=0 if a_done else cfg["A"]
        active_c=0 if c_done else target["C"]
        if min(target["B"],target["C"])<1 or active_a+target["B"]+active_c+target["B_CF"]*target["B_CF_slots"]>22:
            raise ValueError("Native workers leave fewer than three of the 25 cores for shared work")
        if target==prior:
            return reconcile_locked(root,old)
        generation=dict(**target,changed_beijing=now(),reason=reason,
            A_finished=a_done,C_finished=c_done,candidates_frozen=frozen,previous=prior,
            B_throughput_before=read(root/"B/physical_progress.json"),
            A_last_batch=read(root/"A/progress.json"),central_inference=read(root/"service/inference_stats.json"))
        write(path,generation)
        with (directory/"allocation_changes.jsonl").open("a") as f:
            f.write(json.dumps(generation,separators=(",",":"))+"\n")
        return reconcile_locked(root,generation)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,default=DEFAULT)
    p.add_argument("--b-workers",type=int)
    p.add_argument("--c-workers",type=int)
    p.add_argument("--b-gpu-slots",type=int,choices=(1,2,3))
    p.add_argument("--b-cf-workers",type=int)
    p.add_argument("--b-cf-slots",type=int,choices=(1,2,3))
    p.add_argument("--elastic",choices=("on","off"),help="Use verified ordinary-idle CF pool widths and reclaim on demand")
    p.add_argument("--reason")
    args=p.parse_args()
    print(json.dumps(update(args.root,args.b_workers,args.c_workers,args.reason,args.b_gpu_slots,args.b_cf_workers,args.b_cf_slots,
                            None if args.elastic is None else args.elastic=="on"),ensure_ascii=False))

