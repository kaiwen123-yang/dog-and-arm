"""Bound concurrent task optimizers by seed, RAM and the shared GPU allocation."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
from pathlib import Path
from queue import SimpleQueue
from threading import Event
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


def mapped_image_policy(root, membership):
    if root is None or membership is None:
        return {}
    round_name = Path(membership).parent.name
    policy = Path(root)/"resources/mapped_image_policy.json"
    if not (round_name.startswith("r") and round_name[1:].isdigit() and policy.is_file()):
        return {}
    settings = read(policy)
    if settings.get("enabled") and int(round_name[1:]) >= settings["from_round"]:
        return settings
    return {}


def phase_capacity(max_slots, host_free, gpu_free, host_per_fit, wm_gpu, other_gpu):
    """Fit simultaneous phases, reserving memory for the GPU and the host as usual."""
    for slots in range(max_slots,0,-1):
        if slots*host_per_fit+HOST_HEADROOM>host_free:
            continue
        for heavy in range(slots,0,-1):
            budget=heavy*max(wm_gpu,other_gpu)+(slots-heavy)*other_gpu
            if budget+GPU_HEADROOM<=gpu_free:
                return slots,heavy
    return 1,1


def round_storage_policy(root, membership, filename):
    if root is None or membership is None:
        return False
    path = Path(root)/"resources"/filename
    name = Path(membership).parent.name
    if not name.startswith("r") or not name[1:].isdigit() or not path.is_file():
        return False
    policy = read(path)
    round_id = int(name[1:])
    return (policy.get("enabled") is True and round_id >= policy["from_round"]
            and round_id <= policy.get("through_round", round_id))


def compact_row_policy(root, membership):
    return round_storage_policy(root, membership, "compact_state_rows.json")


def stream_row_policy(root, membership):
    if membership is not None:
        capacity = Path(membership).parent/"phase_capacity.json"
        if capacity.is_file():
            cap = read(capacity)
            return cap.get("membership")==str(membership) and cap.get("streamed_storage") is True
    return round_storage_policy(root, membership, "streamed_replay_rows.json")


def wm_replay_budget(root, membership, record):
    if record.get("streamed_storage"):
        # Nonvisual states, indices and legal starts fit in 1 KiB per decision.
        # One 180-scalar visual feature per exposure fits in 1.5 KiB even in FP64.
        columns = 1024*record["wm_rows"] + 1536*(1+record["wm_exposures"])
        return columns+GPU_WORK_PER_OPTIMIZER,True
    marker=Path(root)/"resources/direct_wm_storage.json"
    policy=read(marker) if marker.is_file() else {}
    name=Path(membership).parent.name
    if policy.get("enabled") and name.startswith("r") and name[1:].isdigit() and int(name[1:])>=policy["from_round"]:
        private_rows=estimated_row_bytes(0,record["source_decision_rows"])
        # Direct fill keeps one durable copy of each field. Allow 2,000 B/WM row
        # plus a separate model/workspace reserve; native contexts have their own bound.
        return max(2*private_rows,2000*record["wm_rows"])+GPU_WORK_PER_OPTIMIZER,True
    return record["gpu_estimate_per_fit"],False


def indexed_wm_lanes(spec, cap, conservative_bytes, current_lanes):
    """Budget the indexed replay using its decision, exposure and episode columns."""
    if (current_lanes!=1 or not cap.get("streamed_storage") or cap["slots"]<2
            or not round_storage_policy(spec["root"],spec["members"],"paired_indexed_wm.json")):
        return current_lanes, conservative_bytes
    # 109 float32 state/action/contact values, one mask, four int64 indices
    # and H7 start/contact temporaries fit in 768 bytes per decision. Two
    # copies of the nine-step (52+23)-float prefixes fit in 8 KiB per episode.
    episodes = len(set(read(spec["members"])["wm"]))
    wm_bytes = (768*cap["wm_rows"] + 1536*(1+cap["wm_exposures"])
                + 8192*episodes + GPU_WORK_PER_OPTIMIZER)
    slots, lanes = phase_capacity(cap["slots"],cap["host_available_bytes"],cap["gpu_free_bytes"],
                                  cap["private_host_estimate_per_fit"],wm_bytes,cap["gpu_estimate_other_fit"])
    if slots==cap["slots"] and lanes>=2 and wm_bytes<=conservative_bytes:
        return 2, wm_bytes
    return current_lanes, conservative_bytes


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
    policy = mapped_image_policy(root, membership)
    if policy:
        # The camera pixels live in the original files and share physical pages.
        # Budget private states, model/Adam temporaries and each native pool;
        # the WM builder also holds both the episode blocks and their concatenation.
        private_rows = estimated_row_bytes(0, rows)
        wm_rows = sum(read(Path(p)/"metadata.json")["transitions"]+1 for p in set(mp["wm"]))
        native_width = int(targets.get("B_CF") or 1)
        compact = compact_row_policy(root, membership)
        streamed = (compact and scope==Path(membership).parent.name
                    and round_storage_policy(root,membership,"phase_capacity_policy.json")
                    and round_storage_policy(root,membership,"streamed_replay_rows.json")
                    and round_storage_policy(root,membership,"direct_wm_storage.json"))
        # The compact loader holds one table of input chunks, a bounded transfer,
        # and at most one final host table even on the CUDA-to-host fallback.
        host_per_fit = (2 if compact else 3)*private_rows + 4*GIB + native_width*(5*GIB//2)
        if streamed:
            # Even on CPU fallback the streamed loader owns one row table plus a
            # bounded input block. Reserve the full elastic native pool and its EGL contexts.
            host_per_fit = private_rows + 4*GIB + max(8,native_width)*(5*GIB//2)
        gpu_per_fit = max(2*private_rows, 3000*wm_rows) + GPU_WORK_PER_OPTIMIZER
        slots = max(1,min(requested,policy["max_slots"],
                          (available-HOST_HEADROOM)//host_per_fit,(free-GPU_HEADROOM)//gpu_per_fit))
        record=dict(requested=requested,slots=slots,scope=scope,membership=str(membership),
             image_storage="shared_original_npy",source_image_file_bytes=images,
             source_decision_rows=rows,wm_rows=wm_rows,native_workers_per_seed=native_width,
             private_host_estimate_per_fit=host_per_fit,gpu_estimate_per_fit=gpu_per_fit,
             compact_state_rows=compact,streamed_storage=streamed,
             host_available_bytes=available,gpu_free_bytes=free,planned_gpu_row_tables=0,
             measured_epoch_s=stamp/1e9)
        if streamed:
            import numpy as np
            record["wm_exposures"] = sum(len(np.load(Path(p)/"image_t.npy",mmap_mode="r",allow_pickle=False))
                                         for p in set(mp["wm"]))
        phase_policy=root/"resources/phase_capacity_policy.json"
        folder=Path(membership).parent
        if scope==folder.name and phase_policy.is_file():
            phase=read(phase_policy)
            if phase.get("enabled") and int(scope[1:])>=phase["from_round"]:
                # Reserve CUDA/EGL space for the largest admitted idle native pool.
                other_gpu=max(2*private_rows+GPU_WORK_PER_OPTIMIZER,
                              private_rows+3*GIB+max(8,native_width)*(3*GIB//2))
                wm_gpu,direct=wm_replay_budget(root,membership,record)
                slots,wm_slots=phase_capacity(min(requested,policy["max_slots"],phase["max_slots"]),
                                               available,free,host_per_fit,wm_gpu,other_gpu)
                record.update(previous_uniform_slots=record["slots"],slots=slots,wm_slots=wm_slots,
                              gpu_estimate_other_fit=other_gpu,wm_admission_gpu_bytes=wm_gpu,
                              planned_direct_wm_storage=direct)
                emit(folder/"phase_capacity.json",record)
        emit(evidence,record)
        return slots
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

    @contextmanager
    def completed_fits(self, schedules, fit):
        """Advance each seed as its fit ends, even while the caller scores another policy."""
        ready=SimpleQueue()
        stopping=Event()

        def dispatch():
            futures={}
            def next_for(seed):
                method=next(schedules[seed],None)
                if method is not None and not stopping.is_set():
                    futures[self.submit(seed,fit,method,seed)]=(method,seed)
            try:
                for seed in schedules:
                    next_for(seed)
                while futures and not stopping.is_set():
                    completed,_=wait(futures,return_when=FIRST_COMPLETED)
                    for job in completed:
                        method,seed=futures.pop(job)
                        if getattr(job.exception(),"returncode",None)==75:
                            stopping.set()
                        else:
                            next_for(seed)
                        ready.put((method,seed,job))
            finally:
                ready.put(None)

        with ThreadPoolExecutor(max_workers=1) as dispatcher:
            task=dispatcher.submit(dispatch)
            try:
                yield iter(ready.get,None)
            finally:
                stopping.set()
                task.result()

    def __exit__(self, typ, value, trace):
        # Already running jobs finish their atomic stage. Untouched submissions
        # need not start if the coordinator is explicitly reloaded.
        self.pool.shutdown(wait=True,cancel_futures=typ is not None and getattr(value,"returncode",None)==75)


def native_slot_path(folder, index):
    return folder/("native_cf32.lock" if index==0 else f"native_cf32_{index}.lock")


@contextmanager
def ordinary_capacity(root, base, cases, cf_free_phase, *, partition=""):
    """Borrow idle CF slots during the collecting barrier or after all paired receipts."""
    if not cf_free_phase or base!=4 or cases<=base:
        yield min(base,cases)
        return
    import fcntl
    share=root/"resources/worker_targets.json"
    cfg=read(share) if share.is_file() else {}
    if (cfg.get("B_CF_slots"),cfg.get("B_CF"))!=(3,6):
        yield base
        return
    folder=root/"B/locks"
    folder.mkdir(parents=True,exist_ok=True)
    width=base
    with ExitStack() as reservations:
        try:
            # A live or waiting CF pool keeps full priority outside these two barriers.
            for index in range(3):
                handle=reservations.enter_context(native_slot_path(folder,index).open("a"))
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            _,headroom=host_memory()
            quota,period=Path("/sys/fs/cgroup/cpu.max").read_text().split()
            cores=len(os.sched_getaffinity(0)) if quota=="max" else int(quota)//int(period)
            gpu_free=int(subprocess.check_output(["nvidia-smi","-i","0","--query-gpu=memory.free",
                "--format=csv,noheader,nounits"],text=True).strip())*2**20
            if gpu_free>=GPU_HEADROOM:
                ceiling=min(12,cores//2)
                if partition.endswith("/collect") and cases>=24 and cores>=25 and gpu_free>=18*GIB:
                    trial=root/"performance/20261127-ordinary-queue/width.json"
                    if trial.is_file() and read(trial).get("winner")==18:
                        ceiling=min(18,cores-7)
                width=max(base,min(ceiling,cases,(headroom-HOST_HEADROOM)//(3*GIB//2)))
        except (OSError,ValueError,subprocess.CalledProcessError):
            pass
        if width==base:
            reservations.close()
        yield width


@contextmanager
def wm_phase_slot(spec):
    """Limit simultaneous high-memory WM builders separately from the native seed pools."""
    if spec.get("stage")!="wm":
        yield False
        return
    membership=Path(spec["members"])
    path=membership.parent/"phase_capacity.json"
    if not path.is_file():
        yield False
        return
    import fcntl
    cap=read(path)
    lanes=cap["wm_slots"]
    if cap["membership"]!=str(membership) or not 1<=lanes<=cap["slots"]<=len(SEEDS):
        raise ValueError(f"Invalid WM phase allocation: {path}")
    wm_gpu,direct=wm_replay_budget(spec["root"],membership,cap)
    expanded = False
    if direct:
        # An existing coordinator may have captured its cohort with the old, larger
        # WM peak estimate. Keep its seed limit and re-evaluate only the WM gate.
        slots,lanes=phase_capacity(cap["slots"],cap["host_available_bytes"],cap["gpu_free_bytes"],
                                  cap["private_host_estimate_per_fit"],wm_gpu,cap["gpu_estimate_other_fit"])
        if slots!=cap["slots"]:
            raise ValueError(f"Direct fill cannot satisfy the existing seed allocation: {path}")
        original_lanes = lanes
        lanes,wm_gpu = indexed_wm_lanes(spec,cap,wm_gpu,original_lanes)
        expanded = lanes>original_lanes
        emit(Path(spec["output"])/"wm_storage_admission.json",dict(membership=str(membership),
             direct_storage=True,seed_slots=slots,wm_slots=lanes,wm_gpu_estimate=wm_gpu,
             original_wm_slots=original_lanes,indexed_wm_expansion=expanded,
             host_available_bytes=cap["host_available_bytes"],gpu_free_bytes=cap["gpu_free_bytes"]))
    folder=Path(spec["root"])/"B/locks"
    folder.mkdir(parents=True,exist_ok=True)
    while True:
        for i in range(lanes):
            with (folder/f"wm_phase_{i}.lock").open("a") as handle:
                try:
                    fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                free=int(subprocess.check_output(["nvidia-smi","-i","0","--query-gpu=memory.free",
                        "--format=csv,noheader,nounits"],text=True).strip())*2**20
                if cap["slots"]>1 and free<GPU_HEADROOM+wm_gpu:
                    break
                if expanded and i and (free<GPU_HEADROOM+2*wm_gpu or host_memory()[1]<HOST_HEADROOM+16*GIB):
                    break
                yield direct
                return
        time.sleep(1)


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
                file=native_slot_path(folder,index)
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

