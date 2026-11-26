"""Lend idle B collection capacity to live CF32 pools at independent-window boundaries."""
from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import time

from scripts.multimodal.mm03_launch import now, pid_stamp, read, write

GIB = 2**30
PROTOCOL = "mm03-ordinary-native-lease-v1"


def event(root, kind, **fields):
    target=root/"resources"/"ordinary_elastic_events.jsonl"
    target.parent.mkdir(parents=True,exist_ok=True)
    line=json.dumps(dict(at=now(),epoch=time.time(),event=kind,**fields),separators=(",",":"),allow_nan=False)
    with target.open("a") as f:
        f.write(line+"\n")


def configure_locked(root, enabled, reason):
    """Enable only from the registered, completed comparison owned by this run."""
    directory=root/"resources"
    path=directory/"ordinary_elastic_policy.json"
    if not enabled:
        write(path,dict(enabled=False,protocol=PROTOCOL,changed_beijing=now(),reason=reason))
        return
    source=root/"performance/20261126-cf-latency/elastic_trial.json"
    registration=root/"performance/20261126-cf-latency/elastic_registration.json"
    trial,reg=read(source),read(registration)
    if (trial.get("throughput_ratio",0.)<=1 or set(trial.get("workers",{}).values())!={7} or
            len(trial["workers"])!=3 or not trial.get("min_host_headroom_GiB",0)>8 or
            trial.get("extra_updates")!=0 or trial.get("extra_physics_substeps")!=0):
        raise ValueError("The completed three-pool trial must support seven workers without added training")
    quiet=trial["challenger"]["start_epoch"]-datetime.fromisoformat(reg["at"]).timestamp()
    write(path,dict(enabled=True,protocol=PROTOCOL,source=str(source),changed_beijing=now(),reason=reason,
        ordinary_workers=4,base_per_cf=6,idle_per_cf=7,cf_slots=3,
        observed_throughput_ratio=trial["throughput_ratio"],idle_delay_s=max(0.,quiet),
        minimum_host_reserve_bytes=8*GIB))
    event(root,"policy_enabled",source=str(source),idle_delay_s=quiet)


def announce(root):
    """The publisher may lend only after the live coordinator runs this admission protocol."""
    path=Path(root)/"resources"/"ordinary_coordinator.json"
    pid=os.getpid()
    write(path,dict(protocol=PROTOCOL,pid=pid,pid_stamp=pid_stamp(pid),idle_since=time.time()))


def busy(root):
    file=root/"resources"/"ordinary_execution.lock"
    with file.open("a") as f:
        try:
            fcntl.flock(f,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False


def native_pools(root):
    """Resolve logged native pools to live processes; exited or reused PIDs are ignored."""
    journal=root/"B"/"native_pool_changes.jsonl"
    if not journal.is_file():
        return {}
    live={}
    with journal.open() as f:
        for line in f:
            if not line.endswith("\n"):
                break  # a concurrent append is incomplete
            item=json.loads(line)
            live[item["pid"]]=item["native_pids"]
    actual={}
    for parent, logged in live.items():
        if not logged:
            continue
        proc=Path("/proc")/str(parent)
        try:
            args=(proc/"cmdline").read_bytes().split(b"\0")
            if b"scripts.multimodal.mm03_b_train" not in args:
                continue
            children=(proc/"task"/str(parent)/"children").read_text().split()
        except FileNotFoundError:
            continue
        workers=[]
        for child in children:
            try:
                args=(Path("/proc")/child/"cmdline").read_bytes().split(b"\0")
                if b"scripts.multimodal.mm03_c_native" in args and b"--worker" in args:
                    workers.append(int(child))
            except FileNotFoundError:
                pass
        if workers:
            actual[parent]=workers
    return actual


def memory_available():
    base=Path("/sys/fs/cgroup")
    m={key:int(value) for key,value in (line.split() for line in (base/"memory.stat").read_text().splitlines())}
    limit=(base/"memory.max").read_text().strip()
    if limit=="max":
        return os.sysconf("SC_AVPHYS_PAGES")*os.sysconf("SC_PAGE_SIZE")
    return int(limit)-sum(m.get(k,0) for k in ("anon","shmem","pagetables","kernel_stack","slab_unreclaimable"))


def max_private_bytes(pools):
    maximum=0
    for group in pools.values():
        for pid in group:
            try:
                for line in (Path("/proc")/str(pid)/"status").read_text().splitlines():
                    if line.startswith("RssAnon:"):
                        maximum=max(maximum,1024*int(line.split()[1]))
                        break
            except FileNotFoundError:
                pass
    return maximum


def reconcile_locked(root, base, *, live=None, memory=None):
    """Called under the same allocation.lock used by the ordinary admission barrier."""
    policy=read(root/"resources"/"ordinary_elastic_policy.json")
    previous=base.get("elastic_cf",{})
    if not policy.get("enabled") and not previous:
        return base
    ce=read(root/"resources"/"ordinary_coordinator.json")
    runner=read(root/"status"/"B.json")
    capable=(ce.get("protocol")==PROTOCOL and runner.get("state")=="running" and ce.get("pid") and
             ce["pid"]==runner.get("pid") and ce.get("pid_stamp")==runner.get("pid_stamp")==pid_stamp(ce["pid"]))
    expected=(base.get("B"),base.get("B_CF"),base.get("B_CF_slots"),base.get("B_GPU"))
    applicable=(policy.get("enabled") and capable and expected==(4,6,3,3) and
                base.get("A_finished") and base.get("C_finished") and not base.get("candidates_frozen"))
    idle=False
    actual={}
    available=None
    growth=0
    if applicable and not busy(root):
        quiet=time.time()-ce["idle_since"]
        if quiet>=policy["idle_delay_s"]:
            actual=native_pools(root) if live is None else live
            if len(actual)==3 and all(len(v) in (6,7) for v in actual.values()):
                try:
                    available=memory_available() if memory is None else memory
                    largest=max_private_bytes(actual)
                    growth=sum(max(0,7-len(v)) for v in actual.values())*largest
                    idle=(available>=policy["minimum_host_reserve_bytes"]+growth and largest>0)
                except (OSError,ValueError):
                    pass  # retain the measured four-worker ordinary allocation when telemetry is unavailable
    # Top-level fields remain the admitted baseline for newly constructed pools.
    # Existing pools already read the nested workers values at the next independent reset.
    active=7 if idle else 6
    mode="idle_loan" if idle else "ordinary_reserved"
    if not applicable:
        mode="inactive"
    if mode=="inactive":
        if not previous:
            return base
        updated={k:v for k,v in base.items() if k not in ("workers","elastic_cf")}
    else:
        if previous.get("mode")==mode and base.get("workers",{}).get("B_CF")==active:
            return base
        updated=dict(base)
        updated["workers"]={k:base[k] for k in ("B","C","B_CF","B_GPU","B_CF_slots")}
        updated["workers"].update(B=1 if idle else 4,B_CF=active)
        updated["elastic_cf"]=dict(protocol=PROTOCOL,mode=mode,changed_beijing=now(),reserved_ordinary=4,
            effective_ordinary_capacity=1 if idle else 4,effective_workers_per_cf=active,
            borrowed_ordinary_cores=3 if idle else 0,host_available_bytes=available,
            estimated_incremental_host_bytes=growth,live_pool_sizes={str(p):len(v) for p,v in actual.items()})
    write(root/"resources"/"worker_targets.json",updated)
    event(root,"allocation",mode=mode,base={k:base.get(k) for k in ("B","B_CF","B_CF_slots","B_GPU")},
          actual_cf_sizes={str(p):len(v) for p,v in actual.items()},host_available_bytes=available,
          ordinary_execution_locked=busy(root))
    return updated


@contextmanager
def ordinary_admission(root, partition, planned, default_workers):
    """Start four ordinary workers only after the live pools relinquish borrowed workers."""
    root=Path(root)
    directory=root/"resources"
    directory.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    with (directory/"ordinary_execution.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        prior=read(directory/"worker_targets.json")
        policy=read(directory/"ordinary_elastic_policy.json")
        cfg=prior
        if (policy.get("enabled") or prior.get("elastic_cf")) and (root/"launch_config.json").is_file():
            from scripts.multimodal.mm03_resources import update
            cfg=update(root)
        workers=cfg.get("B",cfg.get("workers",{}).get("B",default_workers))
        if type(workers) is not int or not 1<=workers<=25:
            raise ValueError(f"Invalid native B worker target: {workers}")
        was_lent=prior.get("elastic_cf",{}).get("mode")=="idle_loan"
        # Explicit disable can remove the nested target before the already-running
        # CF optimizers reach their next reset. Still observe that last reclaim.
        recently_managed=(policy.get("protocol")==PROTOCOL and workers==4 and
                          cfg.get("B_CF")==6 and cfg.get("B_CF_slots")==3)
        if was_lent or recently_managed or cfg.get("elastic_cf",{}).get("mode")=="ordinary_reserved":
            # New pools start at top-level six. Existing ones inspect the nested target
            # and finish their ongoing 32-step window before draining their last worker.
            base=cfg["B_CF"]
            pools=native_pools(root)
            while any(len(group)>base for group in pools.values()):
                time.sleep(.12)
                pools=native_pools(root)
        else:
            pools={}
        wait_s=time.monotonic()-started
        event(root,"ordinary_admitted",partition=partition,cases=planned,ordinary_workers=min(workers,planned),
              wait_s=wait_s,was_lent=was_lent,confirmed_cf_sizes={str(p):len(v) for p,v in pools.items()})
        try:
            yield workers
        finally:
            # Record the instant the ordinary pool has actually joined. The lock stays
            # held until after publishing the new quiet interval.
            pid=os.getpid()
            write(directory/"ordinary_coordinator.json",dict(protocol=PROTOCOL,pid=pid,
                  pid_stamp=pid_stamp(pid),idle_since=time.time()))
            event(root,"ordinary_released",partition=partition,cases=planned)
