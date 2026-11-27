from pathlib import Path
import os,time,json,fcntl,statistics
from collections import defaultdict
from scripts.multimodal.mm03_launch import now,read,write
from scripts.multimodal.mm03_elastic import pid_stamp,native_pools
from scripts.multimodal.mm03_elastic_trial import telemetry,process_cpu
from scripts.multimodal.mm03_resources import update
p=Path(__file__).resolve().parent;r=p.parents[1];part='rounds/r28/collect';stage=r/'B'/part
def batches():
 result=[]
 for f in sorted((r/'B/native_batch_timings').glob('*.json')):
  d=read(f)
  if d['partition']==part and d['cases']==24 and d['workers'] in (12,18):
   case=read(stage/d['dispatch_order'][0]/'result.json')
   result.append(dict(method=case['method'],seed=case['seed'],workers=d['workers'],steps=d['physical_substeps'],elapsed=d['elapsed_s'],steps_s=d['substeps_per_s'],start_epoch=d['start_epoch'],evidence=f.name))
 return result
def run():
 assert all((r/f'B/rounds/r27/H9-WM/seed{s}/paired/receipt.json').is_file() for s in (1701,1702,1703)) and not native_pools(r)
 cfg=read(r/'resources/worker_targets.json');assert (cfg['B'],cfg['B_CF'],cfg['B_CF_slots'])==(4,6,3)
 current=len(list(stage.glob('*/result.json')))
 assert current<216 and not (stage.parent/'members.json').exists()
 d=telemetry();assert d['host_free_GiB']>36 and d['gpu_free_GiB']>18
 start=time.time();write(p/'registration.json',dict(at=now(),initial_cases=current,incumbent=12,challenger=18,source='original round-28 paid 24-case cohorts; same method across different fine-tuning seeds; no reruns. Compare native substeps per wall second and elapsed time. Use the wider pool in eligible later phases only if overlapping methods agree and the pooled physical throughput is faster, with memory reserves and shared CPU headroom.',extra_episodes=0))
 write(r/'resources/ordinary_width_trial.json',dict(at=now(),active=True,pid=os.getpid(),pid_stamp=pid_stamp(os.getpid())))
 try:
  update(r,b=18,b_cf=4,cf_slots=1,reason="R28 ordinary collection width trial")
  samples=[];other=process_cpu()
  while len(list(stage.glob('*/result.json')))<216 and not (stage.parent/'members.json').exists():
   x=telemetry();samples.append(x)
   if x['gpu_free_GiB']<12 or x['host_free_GiB']<8 or x['oom_kill']!=d['oom_kill'] or x['oom']!=d['oom']:break
   time.sleep(2)
 finally:
  write(r/'resources/ordinary_width_trial.json',dict(at=now(),active=False))
  c=read(r/'resources/worker_targets.json')
  if c['reason']=="R28 ordinary collection width trial":update(r,b=4,b_cf=6,cf_slots=3,reason="Restore the measured three-seed allocation after the round 28 collection trial")
 end=time.time();other2=process_cpu()
 # Last case receipt precedes the pool-join timing receipt; wait for that native batch only.
 if len(list(stage.glob('*/result.json')))==216:
  while not any(t['start_epoch']+t['elapsed']>=end-5 for t in batches()) and not (stage.parent/'members.json').exists():time.sleep(1)
 rs=batches();by=defaultdict(dict)
 for width in (12,18):
  for method in ('D23','H9','H9-WM'):
   grp=[v for v in rs if (v['workers'],v['method'])==(width,method)]
   if grp:by[method][str(width)]=sum(x['steps'] for x in grp)/sum(x['elapsed'] for x in grp)
 common={m:a for m,a in by.items() if set(a)=={'12','18'}}
 ratios=[a['18']/a['12'] for a in common.values()]
 cpu=(samples[-1]['cpu_usec']-samples[0]['cpu_usec'])/1e6/(samples[-1]['t']-samples[0]['t']) if len(samples)>1 else 100
 good=bool(ratios) and min(ratios)>1 and cpu<=22 and min(x['host_free_GiB'] for x in samples)>=8 and min(x['gpu_free_GiB'] for x in samples)>=12 and samples[-1]['oom_kill']==d['oom_kill']
 write(p/'width.json',dict(at=now(),common_methods=common,matched_throughput_ratios=ratios,batches=rs,winner=18 if good else 12,mean_cpu=cpu,mean_gpu=statistics.mean(x['gpu_util'] for x in samples),min_host_free_GiB=min(x['host_free_GiB'] for x in samples),min_gpu_free_GiB=min(x['gpu_free_GiB'] for x in samples),external_cpu_seconds={k:round(other2[k]['seconds']-v['seconds'],2) for k,v in other.items() if k in other2 and other2[k]['seconds']-v['seconds']>3},note='Adjacent original cases of the same registered method use different independently trained seeds and may have different loss/termination times.',extra_cases=0,extra_substeps=0))
 print(now(),by,'winner',18 if good else 12,flush=True)
if __name__=='__main__':
 with (p/'trial.lock').open('a') as lk:
  fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB);run()
