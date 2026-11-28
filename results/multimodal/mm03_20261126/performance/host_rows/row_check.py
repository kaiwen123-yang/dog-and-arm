from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import hashlib, json, os, resource, sys, time
import numpy as np
import torch
from learning.multimodal.mm03_task import load_task_actor
from learning.multimodal.mm03_task_data import SharedRows
from scripts.multimodal.mm03_b_parallel import GIB, host_memory
from scripts.multimodal.mm03_launch import now, read, write

root = Path('/root/autodl-tmp/mm03-20261126')
out = Path(__file__).resolve().parent
round_dir = root / 'B/rounds/r44'
mode = sys.argv[1]
assert mode in ('original','compact')
torch.set_num_threads(1)
torch.use_deterministic_algorithms(True)
torch.set_float32_matmul_precision('high')
torch.manual_seed(1701)
device = torch.device('cuda:0')
while host_memory()[1] < 49*GIB or torch.cuda.mem_get_info(device)[0] < 37*GIB:
    time.sleep(3)
begin = time.monotonic()
stop = Event()
peak = [0]
minhost = [host_memory()[1]]
def sample():
    while not stop.is_set():
        lines = Path('/proc/self/status').read_text().splitlines()
        peak[0] = max(peak[0], next(int(x.split()[1])*1024 for x in lines if x.startswith('RssAnon:')))
        minhost[0] = min(minhost[0], host_memory()[1])
        stop.wait(.10)
observer=Thread(target=sample,daemon=True)
observer.start()
def digest(a):
    if isinstance(a,torch.Tensor):
        a=a.detach()
        dtype=str(a.dtype)
    else:
        a=np.asarray(a)
        dtype=str(a.dtype)
    h=hashlib.sha256()
    h.update(str((tuple(a.shape),dtype)).encode())
    flat=a.reshape(-1)
    for start in range(0,len(flat),1<<20):
        chunk=flat[start:start+(1<<20)]
        if isinstance(chunk,torch.Tensor):
            chunk=chunk.cpu().numpy()
        h.update(np.ascontiguousarray(chunk).view(np.uint8))
    return h.hexdigest()
with TemporaryDirectory(dir=out) as temp:
    probe=Path(temp)
    path=probe/'r44/members.json'
    membership=read(round_dir/'members.json')
    write(path,membership)
    write(probe/'resources/mapped_image_policy.json',dict(enabled=True,from_round=44,max_slots=3))
    if mode=='compact':
        write(probe/'resources/compact_state_rows.json',dict(enabled=True,from_round=44))
    actors=[load_task_actor(root/f'B/rounds/r43/{name}/seed1701/paired/full.pt',device) for name in ('H9','D23')]
    torch.cuda.reset_peak_memory_stats(device)
    start=time.monotonic()
    table=SharedRows(membership,actors[0][1],device,run_root=probe,member_file=path)
    torch.cuda.synchronize()
    setup=time.monotonic()-start
    build_peak=peak[0]
    build_gpu=torch.cuda.max_memory_reserved(device)
    assert table.residency['compact_state_rows']==(mode=='compact')
    checks={k:digest(v) for k,v in table.data.states.items()}
    for k in ('valid_rows','expert_rows','contact_rows','starts','history_starts','lengths'):
        checks[k]=digest(getattr(table.data,k))
    checks['command']=digest(table.commands)
    checks['command_valid']=digest(table.command_valid)
    cpu_actors=[load_task_actor(root/f'B/rounds/r43/{name}/seed1701/paired/full.pt','cpu')[0] for name in ('H9','D23')]
    schedules={}
    gradients={}
    batches={}
    for seed in (1701,1702,1703):
        source=round_dir/f'schedules/seed{seed}.json'
        registered=read(source)
        order, info = table.schedule(probe/f'schedules/seed{seed}.npy',registered['steps'],registered['seed'])
        assert info['batch_rows_sha256']==registered['batch_rows_sha256']
        assert np.array_equal(order,np.load(source.with_suffix('.npy'),mmap_mode='r'))
        schedules[seed]=info['batch_rows_sha256']
        ix={1701:0,1702:2047,1703:2559}[seed]
        batch=table.batch(order[ix])
        batches[seed]={k:digest(v) for k,v in batch.items()}
        with torch.no_grad():
            for actor,_,_ in actors:
                checks[f'cuda-loss-{actor.mode}-{seed}']=digest(actor.bc_loss(batch))
        cpu_batch={key:value.cpu() for key,value in batch.items()}
        for actor in cpu_actors:
            torch.manual_seed(1701)
            params=[v for v in actor.parameters() if v.requires_grad]
            loss=actor.bc_loss(cpu_batch)
            gs=torch.autograd.grad(loss,params,allow_unused=True)
            gradients[f'{actor.mode}-{seed}']=[digest(loss),[digest(g) if g is not None else None for g in gs]]
    stop.set()
    observer.join()
    write(out/f'{mode}.json', dict(at=now(),mode=mode,episodes=len(table.paths),rows=len(table.data.states['episode']),
          membership_sha256=hashlib.sha256((round_dir/'members.json').read_bytes()).hexdigest(),residency=table.residency,
          setup_s=setup,build_peak_anon_bytes=build_peak,build_peak_cuda_reserved_bytes=build_gpu,
          process_peak_anon_bytes=peak[0],cgroup_min_available_bytes=minhost[0],elapsed_s=time.monotonic()-begin,
          process_cpu_s=time.process_time(),max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
          state_checks=checks,schedules=schedules,batches=batches,gradients=gradients,
          optimizer_updates=0,physics_substeps=0))
    print(now(),mode,setup,build_peak/GIB,build_gpu/GIB,flush=True)
