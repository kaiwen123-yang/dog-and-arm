"""Bound concurrent task optimizers by seed, RAM and the shared GPU allocation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import os
import subprocess
import time

from scripts.multimodal.mm03_b import SEEDS, emit, read

GIB = 2**30


GPU_HEADROOM = 12*GIB
GPU_WORK_PER_OPTIMIZER = 6*GIB
HOST_HEADROOM = 8*GIB


def host_memory():
    cgroup = Path("/sys/fs/cgroup")
    memory = {k:int(v) for k,v in (line.split() for line in (cgroup/"memory.stat").read_text().splitlines())}
    limit = (cgroup/"memory.max").read_text().strip()
    used = sum(memory.get(k,0) for k in ("anon","shmem","pagetables","kernel_stack","slab_unreclaimable"))
    free = int(limit)-used if limit!="max" else os.sysconf("SC_AVPHYS_PAGES")*os.sysconf("SC_PAGE_SIZE")
    return memory.get("anon",0),free


def estimated_row_bytes(image_files,rows):
    # 52 measured scalars, 23 previous controls, three clocks, 23 expert actions
    # (including original float64 records), two indices and the SI command/mask.
    return image_files+rows*521+2**20


def allocation(root, membership, scope):
    """Choose the concurrent population before any optimizer starts loading the shared rows."""
    mp = read(membership)
    episodes = set(mp["teachers"]+mp["corrections"])
    images = sum((Path(p)/(key+".npy")).stat().st_size for p in episodes
                 for key in ("rgb","depth","depth_valid"))
    rows = sum(read(Path(p)/"metadata.json")["transitions"]+1 for p in episodes)
    estimated = estimated_row_bytes(images,rows)
    stamp = time.time_ns()
    evidence = root/"B"/"optimizer_allocations"/f"{stamp}_{scope}.json"
    try:
        anon,available = host_memory()
        free = int(subprocess.check_output(["nvidia-smi","-i","0","--query-gpu=memory.free",
              "--format=csv,noheader,nounits"],text=True).strip())*2**20
    except (OSError,ValueError,subprocess.CalledProcessError) as err:
        emit(evidence,dict(slots=1,scope=scope,membership=str(membership),
             reason="Memory telemetry unavailable; retain single optimizer",detail=str(err)))
        return 1
    targets_file = root/"resources"/"worker_targets.json"
    targets = read(targets_file) if targets_file.exists() else {}
    requested = targets.get("B_GPU",targets.get("workers",{}).get("B_GPU",2))
    if type(requested) is not int or not 1<=requested<=len(SEEDS):
        raise ValueError(f"Invalid B_GPU optimizer concurrency: {requested}")
    for slots in range(requested,0,-1):
        gpu_rows = min(slots,max(0,(free-GPU_HEADROOM-slots*GPU_WORK_PER_OPTIMIZER)//estimated))
        # Loading a GPU table still concatenates the original host arrays once.
        # CPU residence retains a second host tensor allocation after concatenation.
        host = int(slots*(1.7*images+3*GIB)+(slots-gpu_rows)*.7*images)
        if slots==1 or (available-HOST_HEADROOM>=host and free-GPU_HEADROOM>=slots*GPU_WORK_PER_OPTIMIZER):
            break
    emit(evidence,dict(requested=requested,slots=slots,scope=scope,membership=str(membership),
         measured_epoch_s=stamp/1e9,source_image_file_bytes=images,estimated_row_tensor_bytes=estimated,
         planned_gpu_row_tables=gpu_rows,shared_image_GiB=images/GIB,cgroup_anon_GiB=anon/GIB,
         host_available_reclaiming_file_cache_GiB=available/GIB,gpu_free_GiB=free/GIB,
         estimated_host_GiB_for_cohort=host/GIB,per_optimizer_gpu_workspace_GiB=GPU_WORK_PER_OPTIMIZER/GIB,
         shared_gpu_headroom_GiB=GPU_HEADROOM/GIB))
    return slots


def process_stamp(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()
        return None if stat[0]=="Z" else stat[19]
    except (OSError,IndexError):
        return None


def choose_row_device(root,member_file,scope,images,rows,gpu_free):
    """Reserve space under a process lock. Completed old optimizer records are ignored."""
    import fcntl
    root = Path(root)
    cache_dir=root/"B"/"row_cache"
    cache_dir.mkdir(parents=True,exist_ok=True)
    allocation_dir=root/"B"/"optimizer_allocations"
    cohorts=sorted((p for p in allocation_dir.glob("*.json") if
                    any(p.name.endswith("_"+name+".json") for name in scope)),reverse=True)
    cohort={}
    for path in cohorts:
        record=read(path)
        if record.get("membership",str(member_file))==str(member_file):
            cohort=record
            break
    slots=cohort.get("slots",1)
    needed=estimated_row_bytes(images,rows)
    pid=os.getpid()
    record_file=cache_dir/f"{pid}.json"
    with (cache_dir/"reservation.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        # Measure after taking the lock so simultaneous starters cannot both claim
        # the same free bytes while one is still constructing its tensor tables.
        free=int(gpu_free())
        try:
            anon,host=host_memory()
        except (OSError,ValueError):
            anon,host=None,None
        other=[]
        for p in cache_dir.glob("*.json"):
            x=read(p)
            if x["pid"]!=pid and x["device"]=="cuda" and process_stamp(x["pid"])==x["process_stamp"]:
                other.append(x)
        pending=sum(x["estimated_row_tensor_bytes"] for x in other if x["status"]=="loading")
        resident=sum(x.get("actual_row_tensor_bytes",0) for x in other if x["status"]=="ready")
        initial_free=int(cohort.get("gpu_free_GiB",(free+resident)/GIB)*GIB)
        planned=min(slots,max(0,(initial_free-GPU_HEADROOM-slots*GPU_WORK_PER_OPTIMIZER)//needed))
        capacity=free-pending-GPU_HEADROOM-slots*GPU_WORK_PER_OPTIMIZER
        use_cuda=len(other)<planned and capacity>=needed
        state=dict(pid=pid,process_stamp=process_stamp(pid),device="cuda" if use_cuda else "cpu",
            status="loading",membership=str(member_file),cohort_scope=cohort.get("scope"),optimizer_slots=slots,
            source_image_file_bytes=images,estimated_row_tensor_bytes=needed,cohort_gpu_table_capacity=planned,
            live_gpu_free_bytes=free,other_gpu_tables=len(other),other_loading_reserved_bytes=pending,
            other_measured_resident_bytes=resident,shared_gpu_headroom_bytes=GPU_HEADROOM,
            cohort_workspace_bytes=slots*GPU_WORK_PER_OPTIMIZER,cgroup_anon_bytes=anon,
            host_headroom_reclaiming_cache_bytes=host,created_epoch_s=time.time())
        emit(record_file,state)
    return record_file,state


class SeedOptimizers:
    """Use at most one active fit per seed and deliver ready results to one native scheduler."""
    def __init__(self, slots):
        self.pool = ThreadPoolExecutor(max_workers=slots)
        self.previous = {}

    def submit(self, seed, function, *args):
        prior = self.previous.get(seed)
        def run():
            if prior is not None:
                # Preserve submission order within each seed. A distinct method
                # may still proceed from its own valid parent after another fails.
                prior.exception()
            return function(*args)
        future = self.pool.submit(run)
        self.previous[seed] = future
        return future

    def __enter__(self):
        return self

    def __exit__(self, typ, value, trace):
        # Already running jobs finish their atomic stage. Untouched submissions
        # need not start if the coordinator is explicitly reloaded.
        self.pool.shutdown(wait=True,cancel_futures=typ is not None and getattr(value,"returncode",None)==75)


@contextmanager
def native_pair_slot(spec):
    """Use one writer per frozen fork and a bounded number of independent native pools."""
    if spec.get("variant")!="CF32":
        yield
        return
    import fcntl
    folder = Path(spec["root"])/"B"/"locks"
    folder.mkdir(parents=True,exist_ok=True)
    out = Path(spec["output"])
    out.mkdir(parents=True,exist_ok=True)
    with (out/"native_stage_owner.lock").open("a") as owner:
        fcntl.flock(owner,fcntl.LOCK_EX)
        if (out/"receipt.json").is_file():
            yield
            return
        share=Path(spec["root"])/"resources/worker_targets.json"
        handle=None
        while handle is None:
            cfg=read(share) if share.is_file() else {}
            slots=int(cfg.get("B_CF_slots",1))
            if not 1<=slots<=3:
                raise ValueError(f"Invalid number of CF32 optimizer slots: {slots}")
            workers=int(cfg.get("B_CF") or spec.get("native_workers",3))
            for index in range(slots):
                file=folder/("native_cf32.lock" if index==0 else f"native_cf32_{index}.lock")
                candidate=file.open("a")
                try:
                    fcntl.flock(candidate,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    candidate.close()
                    continue
                anon,available=host_memory()
                free=int(subprocess.check_output(["nvidia-smi","-i","0","--query-gpu=memory.free",
                         "--format=csv,noheader,nounits"],text=True).strip())*2**20
                if index and (available < (8+4*workers)*GIB or free < (12+workers)*GIB):
                    candidate.close()
                    continue
                handle=candidate
                emit(out/f"native_slot_{os.getpid()}.json",dict(index=index,slots=slots,initial_workers=workers,
                    pid=os.getpid(),acquired_epoch=time.time(),free_gpu_bytes=free,
                    available_host_bytes=available,anon_bytes=anon,owner=str(owner.name)))
                break
            if handle is None:
                time.sleep(1)
        try:
            yield
        finally:
            handle.close()

