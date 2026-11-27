from pathlib import Path
import tempfile,os,time,json,fcntl,multiprocessing as mp
from unittest.mock import patch
from scripts.multimodal.mm03_b_parallel import GIB,phase_capacity,wm_phase_slot
from scripts.multimodal.mm03_launch import read,write,now
p=Path(__file__).resolve().parent;rec=read(p/'promotion.json');a=rec['admitted'];host=a['private_host_estimate_per_fit'];heavy=a['gpu_estimate_per_fit'];light=a['gpu_estimate_other_fit']
assert phase_capacity(3,a['host_available_bytes'],a['gpu_free_bytes'],host,heavy,light)==(3,2)
assert phase_capacity(3,8*GIB+2*host,2**40,host,heavy,light)[0]==2
assert phase_capacity(3,2**40,12*GIB+heavy+2*light-1,host,heavy,light)[0]<3
assert phase_capacity(3,2**40,12*GIB+heavy+2*light,host,heavy,light)==(3,1)
def child(spec,held,release):
 with patch('scripts.multimodal.mm03_b_parallel.subprocess.check_output',return_value='96000'):
  with wm_phase_slot(spec):
   held.set();release.wait()
with tempfile.TemporaryDirectory(dir=p) as tmp:
 root=Path(tmp);folder=root/'B/rounds/r27';folder.mkdir(parents=True)
 spec=dict(stage='wm',root=tmp,members=str(folder/'members.json'))
 write(folder/'phase_capacity.json',dict(a,membership=spec['members']));ctx=mp.get_context('fork')
 held=[ctx.Event() for _ in range(3)];release=[ctx.Event() for _ in range(3)]
 procs=[ctx.Process(target=child,args=(spec,held[i],release[i])) for i in range(3)]
 try:
  for i in (0,1):procs[i].start();assert held[i].wait(10)
  procs[2].start();assert not held[2].wait(.5)
  release[0].set();assert held[2].wait(5)
 finally:
  for ev in release:ev.set()
  for pr in procs:
   if pr.pid is not None:pr.join()
 assert all(x.exitcode==0 for x in procs)
write(p/'gate_check.json',dict(at=now(),original_R27_slots=2,phase_R27_slots=3,max_simultaneous_world_models=2,third_WM_waited_until_real_lock_released=True,
 tight_host_and_device_quotas_checked=True,extra_training_updates=0,extra_native_substeps=0))
