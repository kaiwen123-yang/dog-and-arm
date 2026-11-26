"""Bound concurrent task optimizers by seed, RAM and the shared GPU allocation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import os
import subprocess
import time

from scripts.multimodal.mm03_b import SEEDS, emit, read

GIB = 2**30


def allocation(root, membership, scope):
    """The dataset may reside in host or GPU memory, depending on its actual size."""
    mp = read(membership)
    episodes = set(mp["teachers"]+mp["corrections"])
    images = sum((Path(p)/(key+".npy")).stat().st_size for p in episodes
                 for key in ("rgb","depth","depth_valid"))
    cgroup = Path("/sys/fs/cgroup")
    memory = {k:int(v) for k,v in (line.split() for line in (cgroup/"memory.stat").read_text().splitlines())}
    limit = (cgroup/"memory.max").read_text().strip()
    used = sum(memory.get(k,0) for k in ("anon","shmem","pagetables","kernel_stack","slab_unreclaimable"))
    available = int(limit)-used if limit!="max" else os.sysconf("SC_AVPHYS_PAGES")*os.sysconf("SC_PAGE_SIZE")
    gpu_free = int(subprocess.check_output(
        ["nvidia-smi","-i","0","--query-gpu=memory.free","--format=csv,noheader,nounits"],text=True).strip())*2**20
    # Include the concatenation of mapped image arrays and the additional CPU copy
    # used by large CPU-resident pools. CUDA overhead includes local models and H7/H32.
    host_per_slot = int((2.3 if images>10*GIB else 1.7)*images)+3*GIB
    gpu_per_slot = (images if images<=10*GIB else 0)+6*GIB
    targets_path = root/"resources"/"worker_targets.json"
    targets = read(targets_path) if targets_path.exists() else {}
    requested = targets.get("B_GPU",targets.get("workers",{}).get("B_GPU",2))
    if type(requested) is not int or not 1<=requested<=len(SEEDS):
        raise ValueError(f"Invalid B_GPU optimizer concurrency: {requested}")
    slots = max(1,min(requested,(available-8*GIB)//host_per_slot,(gpu_free-8*GIB)//gpu_per_slot))
    stamp = time.time_ns()
    emit(root/"B"/"optimizer_allocations"/f"{stamp}_{scope}.json",dict(
         requested=requested, slots=slots, scope=scope, measured_epoch_s=stamp/1e9,
         shared_image_GiB=images/GIB, cgroup_anon_GiB=memory.get("anon",0)/GIB,
         host_available_reclaiming_file_cache_GiB=available/GIB,gpu_free_GiB=gpu_free/GIB,
         estimated_host_GiB_per_slot=host_per_slot/GIB,estimated_gpu_GiB_per_slot=gpu_per_slot/GIB))
    return slots


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
    """B_CF is the total shared native population, even with multiple independent seeds."""
    if spec.get("variant")!="CF32":
        yield
        return
    import fcntl
    folder = Path(spec["root"])/"B"/"locks"
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/"native_cf32.lock").open("a") as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        yield

