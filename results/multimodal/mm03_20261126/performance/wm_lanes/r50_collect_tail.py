from pathlib import Path
import fcntl
import time
from idle_release import root,out,replace,snap
from scripts.multimodal.mm03_launch import alive,read,write,now
def main():
 result=out/'r50_admission.json'
 if result.exists():return
 rd=root/'B/rounds/r50';old=root/'B/rounds/r49';action=None
 while not (rd/'phase_capacity.json').exists():
  if (root/'B/completion.json').exists():return
  if not alive(read(root/'status/B.json')):time.sleep(3);continue
  if action is None and (rd/'collect').exists():
   # The last of nine frozen policies is being prefetched. Drain existing subscriptions;
   # a fresh service handles any new connections on the same socket.
   episodes=len(list((rd/'collect').glob('*/result.json')))
   if episodes>=196 and len(list((old/'development').glob('*/result.json')))==72:
    state=snap()
    if state['gpu_MiB'] > 0:
     action=replace('r50_collection_tail','Reclaim completed policy caches before R50 seed admission',False)
    else:action=dict(skip='Current service has no allocated CUDA memory',at=now(),snapshot=state)
  time.sleep(2)
 c=read(rd/'phase_capacity.json');g=2**30
 record=dict(at=now(),round=50,allocation=c,drained_release=action,
  used_original_admission=True,host_available_GiB=c['host_available_bytes']/g,gpu_free_GiB=c['gpu_free_bytes']/g,
  required_for_three_host_GiB=3*c['private_host_estimate_per_fit']/g+8,
  required_for_three_gpu_GiB=(c['wm_admission_gpu_bytes']+2*c['gpu_estimate_other_fit'])/g+12,
  seed_slots=c['slots'],wm_slots_before_optional_tuning=c['wm_slots'],
  optional_wm_policy=read(root/'resources/paired_wm_loaders.json'),extra_native_steps=0,extra_optimizer_updates=0)
 write(result,record)
 print(now(),'original admission',c['slots'],record['host_available_GiB'],record['gpu_free_GiB'],flush=True)
if __name__=='__main__':
 with (out/'r50_tail.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
