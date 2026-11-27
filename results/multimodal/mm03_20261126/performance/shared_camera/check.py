from pathlib import Path
import json,os,time,tempfile,resource,hashlib
import numpy as np,torch
from learning.multimodal.mm03_task import load_task_actor
from learning.multimodal.mm03_task_data import SharedRows
from scripts.multimodal.mm03_b import emit,read
from scripts.multimodal.mm03_b_parallel import allocation
from scripts.multimodal.mm03_launch import now
r=Path('/root/autodl-tmp/mm03-20261126');p=Path(__file__).resolve().parent
mp=read(r/'B/rounds/r21/members.json');torch.set_num_threads(1);torch.set_float32_matmul_precision('high')
actors=[load_task_actor(r/f'B/rounds/r20/{m}/seed1701/paired/full.pt','cuda:0') for m in ('H9','D23')]
sub={k:seq[::max(1,len(seq)//17)][:20] for k in ('teachers','corrections') for seq in (mp[k],)}
with tempfile.TemporaryDirectory(dir=p) as tmp:
 root=Path(tmp);path=root/'r21/members.json';emit(path,sub)
 pilot=SharedRows(sub,actors[0][1],'cuda:0')
 emit(root/'resources/mapped_image_policy.json',dict(enabled=True,from_round=21,max_slots=3))
 fd0=len(list(Path('/proc/self/fd').iterdir()))
 mapped=SharedRows(sub,actors[0][1],'cuda:0',run_root=root,member_file=path)
 fd1=len(list(Path('/proc/self/fd').iterdir()))
 a,aa=pilot.schedule(root/'old/order.npy',updates=12,seed=183);b,bb=mapped.schedule(root/'new/order.npy',updates=12,seed=183)
 assert np.array_equal(a,b) and aa['batch_rows_sha256']==bb['batch_rows_sha256']
 assert mapped.paths==pilot.paths and np.array_equal(pilot.data.starts,mapped.data.starts)
 last=len(pilot.data.images['rgb'])-1
 for k,old in pilot.data.images.items():
  ids=np.array([0,1,last,last,0],dtype=np.int64)
  assert torch.equal(old[torch.from_numpy(ids).cuda()].cpu(),mapped.data.mapped_images[k].gather(ids))
 grad={}; cuda_noise={}; cpuactors={actor.mode:load_task_actor(r/f'B/rounds/r20/{actor.mode}/seed1701/paired/full.pt','cpu')[0] for actor,_,_ in actors}
 for step in (0,4,11):
  u=pilot.batch(a[step]);v=mapped.batch(b[step])
  assert u.keys()==v.keys() and all(u[k].dtype==v[k].dtype and torch.equal(u[k],v[k]) for k in u)
  for actor,_,_ in actors:
   loss=actor.bc_loss(u);loss2=actor.bc_loss(v)
   params=[v for v in actor.parameters() if v.requires_grad]
   g=torch.autograd.grad(loss,params,allow_unused=True);gg=torch.autograd.grad(loss2,params,allow_unused=True)
   repeat=torch.autograd.grad(actor.bc_loss(u),params,allow_unused=True)
   assert torch.equal(loss,loss2)
   def error(g1,g2):
    return max((float(torch.linalg.vector_norm(x-y)/torch.linalg.vector_norm(x).clamp_min(1e-10)) for x,y in zip(g1,g2) if x is not None and y is not None),default=0.)
   observed,reference=error(g,gg),error(g,repeat)
   assert observed<=max(2e-6,reference*4), (observed,reference)
   cuda_noise[f'{actor.mode}_{step}']=[observed,reference]
   cpu=cpuactors[actor.mode];cl=[cpu.bc_loss({k:v.cpu() for k,v in batch.items()}) for batch in (u,v)]
   params_cpu=[v for v in cpu.parameters() if v.requires_grad];g1,g2=[torch.autograd.grad(v,params_cpu,allow_unused=True) for v in cl]
   assert torch.equal(cl[0],cl[1]) and all((x is None and y is None) or (x is not None and y is not None and torch.equal(x,y)) for x,y in zip(g1,g2))
   grad[actor.mode]=sum(x is not None for x in g)
 assert fd1-fd0<12
 emit(p/'gradient_repeat.json',dict(checked=now(),relative_l2_mapped_vs_eager_and_eager_repeat=cuda_noise,CPU_all_gradients_byte_equal=True,CUDA_forward_loss_equal=True))
 emit(p/'parity.json',dict(at=now(),episodes=len(mapped.paths),all_batch_fields=list(u),all_three_batches_bitwise=True,gradient_tensors=grad,bc_sha256=aa['batch_rows_sha256'],boundary_missing_repeated_ids_match=True,extra_held_fds=fd1-fd0,physical_substeps=0,optimizer_applications=0))
 del pilot,mapped,actors,u,v,loss,loss2,g,gg,params
 torch.cuda.empty_cache()
 # Replay the actual full production membership without constructing a second image copy.
 vocab=load_task_actor(r/'B/rounds/r20/H9/seed1701/paired/full.pt','cuda:0')[1]
 emit(path,mp);fd0=len(list(Path('/proc/self/fd').iterdir()));before=torch.cuda.memory_allocated()
 torch.cuda.reset_peak_memory_stats()
 start=time.monotonic();table=SharedRows(mp,vocab,'cuda:0',run_root=root,member_file=path);setup=time.monotonic()-start
 order=np.load(r/'B/rounds/r21/schedules/seed1703.npy',mmap_mode='r')
 start=time.monotonic();torch.cuda.synchronize()
 for row in order[500:564]:
  batch=table.batch(row)
 torch.cuda.synchronize();elapsed=time.monotonic()-start
 emit(p/'full_membership.json',dict(at=now(),**table.residency,episodes=len(table.paths),setup_seconds=setup,measured_batches=64,mean_batch_gather_ms=elapsed*1000/64,extra_held_fds=len(list(Path('/proc/self/fd').iterdir()))-fd0,process_peak_RSS_GiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**20,peak_cuda_GiB=torch.cuda.max_memory_allocated()/2**30,physical_substeps=0,optimizer_applications=0))
 print('PASS',read(p/'full_membership.json'),flush=True)
