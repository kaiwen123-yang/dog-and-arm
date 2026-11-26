"""Read paid CF32 receipts and compare two guarded, ordinary-idle production windows."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

from scripts.multimodal.mm03_elastic import busy, memory_available, native_pools, pid_stamp
from scripts.multimodal.mm03_launch import now, read, write

GIB=2**30
DURATION=90.
WARM=20.
TRIAL_PARENT="performance/20261126-cf-latency"


def folder(root,round_id):
    return root/TRIAL_PARENT/f"r{round_id:02d}-eight"


def process_cpu():
    entries={}
    for path in Path("/proc").iterdir():
        if not path.name.isnumeric():
            continue
        try:
            name=(path/"comm").read_text().strip()
            if not name.startswith("python"):
                continue
            cwd=os.readlink(path/"cwd")
            if not cwd.startswith("/root/autodl-tmp/") or "dog-and-arm-mm03" in cwd or "mm03-20261126" in cwd:
                continue
            stat=(path/"stat").read_text().rsplit(")",1)[1].split()
            entries[f"{path.name}/{stat[19]}"]=dict(name=name,project=cwd.split("/")[3],
                                      seconds=(int(stat[11])+int(stat[12]))/os.sysconf("SC_CLK_TCK"))
        except (FileNotFoundError,ProcessLookupError,PermissionError,IndexError):
            continue
    return entries


def telemetry():
    cg=Path("/sys/fs/cgroup")
    cpu=dict(l.split() for l in (cg/"cpu.stat").read_text().splitlines())
    mem=dict(l.split() for l in (cg/"memory.events").read_text().splitlines())
    gpu=subprocess.check_output(["nvidia-smi","-i","0","--query-gpu=utilization.gpu,memory.free",
                                "--format=csv,noheader,nounits"],text=True).strip().split(",")
    return dict(t=time.time(),cpu_usec=int(cpu["usage_usec"]),throttle_usec=int(cpu["throttled_usec"]),
        host_free_GiB=memory_available()/GIB,gpu_free_GiB=int(gpu[1])/1024,gpu_util=int(gpu[0]),
        oom=int(mem["oom"]),oom_kill=int(mem["oom_kill"]))


def paid(root,start,end,round_id):
    totals={}
    for seed in (1701,1702,1703):
        p=root/f"B/rounds/r{round_id:02d}/H9-WM/seed{seed}/paired/applied.jsonl"
        rows=[]
        for line in p.read_text().splitlines():
            if not line or not line.endswith("}"):
                continue
            x=json.loads(line)
            f=Path(x["shared_native_replay"])
            when=f.stat().st_mtime
            if start<=when<end:
                rows.append((x["update"],int(x["native_substeps"]),when))
        totals[str(seed)]=dict(updates=len(rows),substeps=sum(x[1] for x in rows),first=rows[0] if rows else None,
                               last=rows[-1] if rows else None,ledger=str(p))
    updates=sum(x["updates"] for x in totals.values())
    steps=sum(x["substeps"] for x in totals.values())
    return dict(start=start,end=end,seconds=end-start,by_seed=totals,updates=updates,substeps=steps,
                updates_min=60*updates/(end-start),substeps_s=steps/(end-start))


def active(root,round_id):
    actual=native_pools(root)
    result={}
    for p in (root/f"B/rounds/r{round_id:02d}/H9-WM").glob("seed*/paired/native_pool_processes.jsonl"):
        for line in p.read_text().splitlines():
            owner=json.loads(line)["optimizer_pid"]
            if owner in actual:
                result[str(owner)]=len(actual[owner])
    return result


def sample(root,round_id,width):
    start=time.time()
    end=start+DURATION
    external=process_cpu()
    observations=[]
    flag=None
    while True:
        x=telemetry()
        populations=active(root,round_id)
        ordinary=busy(root)
        x.update(pool_widths=populations,ordinary_active=ordinary)
        observations.append(x)
        if len(populations)!=3 or any(n!=width for n in populations.values()) or ordinary:
            flag="ordinary batch or three-pool population changed"
            break
        if x["oom"]!=observations[0]["oom"] or x["oom_kill"]!=observations[0]["oom_kill"] or x["host_free_GiB"]<8 or x["gpu_free_GiB"]<12:
            flag="host/GPU headroom or OOM counters changed"
            break
        if x["t"]>=end:
            break
        time.sleep(min(1.5,max(0.,end-time.time())))
    external_end=process_cpu()
    endpoints={}
    for key in external.keys()&external_end.keys():
        endpoints[key]=dict(project=external[key]["project"],cpu_seconds=external_end[key]["seconds"]-external[key]["seconds"])
    covered=min(observations[-1]["t"],end)
    if covered<=start:
        raise RuntimeError("No measurable production interval")
    result=paid(root,start,covered,round_id)
    result.update(width=width,valid=flag is None and covered>=end,stop_reason=flag,
        external=endpoints,external_exited=sorted(external.keys()-external_end.keys()),
        external_started=sorted(external_end.keys()-external.keys()),samples=observations,
        mean_cpu=(observations[-1]["cpu_usec"]-observations[0]["cpu_usec"])/1e6/max(.001,observations[-1]["t"]-observations[0]["t"]),
        min_host_GiB=min(x["host_free_GiB"] for x in observations),min_gpu_GiB=min(x["gpu_free_GiB"] for x in observations))
    return result


def challenger(root,round_id):
    import fcntl
    from scripts.multimodal.mm03_resources import update
    from scripts.multimodal.mm03_elastic import max_private_bytes,eight_compute_headroom
    directory=folder(root,round_id)
    with (directory/"controller.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (directory/"decision.json").exists():
            print(read(directory/"decision.json"));return
        while not (directory/"baseline.json").exists():
            if busy(root) or set(active(root,round_id).values())!={7}:
                raise RuntimeError("Baseline lost its ordinary-idle triplet")
            time.sleep(1)
        base=read(directory/"baseline.json")
        verdict=dict(valid=False,winner="seven",at=now(),round=round_id,baseline_updates=base["updates"],
                     comparison="equal 90s production windows",extra_updates=0,extra_physics_substeps=0)
        if not base["valid"]:
            write(directory/"decision.json",dict(**verdict,reason=base["stop_reason"]));return
        try:
            owners=active(root,round_id)
            pools={k:v for k,v in native_pools(root).items() if str(k) in owners}
            cpu,gpu,budget=eight_compute_headroom(root)
            if (busy(root) or len(pools)!=3 or any(len(v)!=7 for v in pools.values()) or cpu is None or
                    cpu>22 or budget<25 or gpu<15 or memory_available()<8*GIB+3*max_private_bytes(pools)):
                raise RuntimeError(f"Insufficient idle trial headroom or population, CPU {cpu}, GPU free {gpu}")
            pid=os.getpid();expiry=time.time()+DURATION+WARM+55
            write(root/"resources"/"ordinary_eight_trial.json",dict(round=round_id,active=True,pid=pid,
                  pid_stamp=pid_stamp(pid),expires_epoch=expiry,at=now(),ordinary_workers_on_demand=4,desired_idle_cf=8))
            first=None
            while first is None or time.monotonic()-first<WARM:
                update(root)
                widths=active(root,round_id)
                if busy(root) or len(widths)!=3 or time.time()>=expiry-DURATION:
                    raise RuntimeError("No intact ordinary-idle eight-worker warm interval")
                if all(n==8 for n in widths.values()):
                    if first is None:
                        first=time.monotonic()
                        write(directory/"eight_ack.json",dict(at=now(),workers=widths))
                else:
                    first=None
                time.sleep(.3)
            test=sample(root,round_id,8);write(directory/"challenger.json",test)
            peers={k for k,v in base["external"].items() if v["cpu_seconds"]>=5 and k in test["external"]}
            base_hot={k for k,v in base["external"].items() if v["cpu_seconds"]>=5}
            test_hot={k for k,v in test["external"].items() if v["cpu_seconds"]>=5}
            ratios={k:test["external"][k]["cpu_seconds"]/base["external"][k]["cpu_seconds"] for k in peers}
            other_base=sum(base["external"][k]["cpu_seconds"] for k in peers)
            other_new=sum(test["external"][k]["cpu_seconds"] for k in peers)
            checks=dict(complete=test["valid"],updates_grew=test["updates_min"]>base["updates_min"],
                physical_steps_grew=test["substeps_s"]>base["substeps_s"],
                host_gpu_reserves=test["min_host_GiB"]>=8 and test["min_gpu_GiB"]>=12,
                total_cpu_headroom=test["mean_cpu"]<=22,external_hot_cohort_unchanged=base_hot==test_hot,
                other_jobs_progress=(not peers or (other_new>=.90*other_base and min(ratios.values())>=.85)))
            win=all(checks.values())
            verdict.update(valid=test["valid"],winner="eight" if win else "seven",at=now(),checks=checks,
                baseline_updates_min=base["updates_min"],challenger_updates_min=test["updates_min"],
                baseline_substeps_s=base["substeps_s"],challenger_substeps_s=test["substeps_s"],
                updates_throughput_ratio=test["updates_min"]/base["updates_min"],challenger_updates=test["updates"],
                external_common_cpu_seconds=[other_base,other_new],external_ratios=ratios,
                other_hot_jobs_left=sorted(base_hot-test_hot),other_hot_jobs_joined=sorted(test_hot-base_hot),
                baseline_cpu=base["mean_cpu"],challenger_cpu=test["mean_cpu"],
                min_host_GiB=test["min_host_GiB"],min_gpu_GiB=test["min_gpu_GiB"])
        except Exception as error:
            verdict.update(reason=str(error))
        finally:
            write(directory/"decision.json",verdict)
            write(root/"resources"/"ordinary_eight_trial.json",dict(round=round_id,active=False,at=now()))
            update(root)
            print(json.dumps(verdict,allow_nan=False),flush=True)


def monitor(root,round_id):
    directory=folder(root,round_id)
    directory.mkdir(parents=True,exist_ok=True)
    import fcntl
    with (directory/"monitor.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (directory/"decision.json").exists():
            print(read(directory/"decision.json"));return
        reg=directory/"registration.json"
        if not reg.is_file():
            write(reg,dict(at=now(),round=round_id,windows_s=[DURATION,DURATION],all_pool_warm_s=WARM,
                baseline="first qualifying future ordinary-idle production interval with three observed seven-worker pools",
                challenger="same round/seeds, next eligible interval at eight per pool",
                min_remaining_per_seed_at_baseline=104,min_common_external_cpu_ratio=.90,min_individual_external_cpu_ratio=.85,
                require_same_external_hot_cohort=True,external_hot_cpu_seconds=5,
                max_mean_cpu=22,min_host_GiB=8,min_gpu_GiB=12,
                win_rule="both paid updates/minute and native substeps/s increase, ordinary queue idle throughout, host/GPU/CPU reserves hold, no OOM increment and common other jobs preserve CPU progress",
                extra_updates=0,extra_substeps=0))
        if not (directory/"baseline.json").exists():
            warm=None
            while True:
                phase=root/f"B/rounds/r{round_id:02d}/H9-WM"
                paths=list(phase.glob("seed*/paired/progress.json"))
                counts={p.parents[1].name:read(p).get("step",0) for p in paths}
                if max(counts.values(),default=0)>512-104 or any(phase.glob("seed*/paired/receipt.json")) or (root/"B/completion.json").exists():
                    write(directory/"decision.json",dict(at=now(),valid=False,winner="seven",round=round_id,
                        reason="No same-round triplet with sufficient remaining registered work; training continued",paid_progress=counts))
                    return
                widths=active(root,round_id)
                if len(widths)==3 and all(n==7 for n in widths.values()) and not busy(root):
                    if warm is None:warm=time.monotonic()
                    if time.monotonic()-warm>=WARM:
                        counts={p.parents[1].name:len(p.read_text().splitlines()) for p in phase.glob("seed*/paired/applied.jsonl")}
                        if len(counts)==3 and max(counts.values())<=512-104:
                            break
                        write(directory/"decision.json",dict(at=now(),valid=False,winner="seven",round=round_id,
                              reason="Insufficient remaining paid work at admission",paid_progress=counts))
                        return
                else:
                    warm=None
                time.sleep(1.5)
            print(now(),"baseline_start",round_id,counts,flush=True)
            base=sample(root,round_id,7);write(directory/"baseline.json",base)
            print(now(),"baseline_receipt",base["valid"],base["updates_min"],flush=True)
        challenger(root,round_id)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--round",required=True,type=int)
    args=p.parse_args()
    monitor(args.root.resolve(),args.round)


if __name__=="__main__":
    main()
