from pathlib import Path
from statistics import mean
import json,os,sys,time
from scripts.multimodal.mm03_launch import read,write,now
from scripts.multimodal.mm03_elastic_trial import telemetry,active,process_cpu
from scripts.multimodal.mm03_elastic import busy
p=Path(__file__).resolve().parent;r=p.parents[1];phase=r/'B/rounds/r27/H9-WM'
def rows():
 result={}
 for seed in (1701,1702,1703):
  f=phase/f'seed{seed}/paired/applied.jsonl'
  a=[json.loads(x) for x in f.open() if x.endswith('\n')] if f.is_file() else []
  if any(i!=v['update'] for i,v in enumerate(a,1)):raise ValueError(f)
  result[str(seed)]=[len(a),sum(v['native_substeps'] for v in a)]
 return result
def window(n):
 start=None;last=None
 while True:
  size=sorted(active(r,27).values())
  if max(x[0] for x in rows().values())>460:raise ValueError('Insufficient remaining registered work for stable measurement')
  if len(size)==n and len(set(size))==1 and not busy(r):
   if start is None or size!=last:start=time.monotonic()
   if time.monotonic()-start>8:break
  else:start=None
  last=size;time.sleep(1)
 a=rows();peers=process_cpu();ss=[];t0=time.monotonic();epoch=time.time();width=size[0]
 while True:
  x=telemetry();ss.append(x)
  if sorted(active(r,27).values())!=[width]*n or busy(r):raise ValueError('Native width or ordinary queue changed')
  if x['host_free_GiB']<8 or x['gpu_free_GiB']<12 or x['oom_kill']!=ss[0]['oom_kill'] or x['oom']!=ss[0]['oom']:raise ValueError('Resource reserve changed')
  left=90-(time.monotonic()-t0)
  if left<=0:break
  time.sleep(min(1.5,left))
 b=rows();dt=time.monotonic()-t0;endpeers=process_cpu()
 counts={k:b[k][0]-a[k][0] for k in a};substeps=sum(b[k][1]-a[k][1] for k in a)
 assert sum(v>0 for v in counts.values())==n
 d=dict(at=now(),start_epoch=epoch,seconds=dt,round=27,seeds=n,native_per_seed=width,before=a,after=b,paid=counts,updates_min=sum(counts.values())*60/dt,native_substeps=substeps,substeps_s=substeps/dt,gpu_mean=mean(x['gpu_util'] for x in ss),cpu_cores=(ss[-1]['cpu_usec']-ss[0]['cpu_usec'])/1e6/(ss[-1]['t']-ss[0]['t']),min_host_free_GiB=min(x['host_free_GiB'] for x in ss),min_gpu_free_GiB=min(x['gpu_free_GiB'] for x in ss),other_cpu_seconds={k:round(endpeers[k]['seconds']-v['seconds'],2) for k,v in peers.items() if k in endpeers and endpeers[k]['seconds']-v['seconds']>2},oom_kill_change=ss[-1]['oom_kill']-ss[0]['oom_kill'],extra_optimizer_updates=0,extra_native_substeps=0)
 write(p/f'window_{n}.json',d);print('window',n,d['updates_min'],flush=True)
if __name__=='__main__':
 reg=p/'registration.json'
 if not reg.exists():write(reg,dict(at=now(),round=27,windows_seconds=[90,90],criterion='Two live H9-WM seeds versus three using the same round, registered optimizer applications and native substeps; retain three if both aggregate rates rise under the host and device reserves. Preserve all other jobs and frozen budgets.',extra_physical_substeps=0,extra_updates=0))
 try:
  for n in (2,3):
   if not (p/f'window_{n}.json').exists():window(n)
  a,b=(read(p/f'window_{n}.json') for n in (2,3));three=b['updates_min']>a['updates_min'] and b['substeps_s']>a['substeps_s']
  write(p/'decision.json',dict(at=now(),valid=True,three_faster=three,ratio=b['updates_min']/a['updates_min'],two_updates_min=a['updates_min'],three_updates_min=b['updates_min']))
 except Exception as err:write(p/'trial_error.json',dict(at=now(),error=str(err)));raise
