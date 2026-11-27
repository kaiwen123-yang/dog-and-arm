from pathlib import Path
import json,datetime,time,statistics
from scripts.multimodal.mm03_launch import now,read,write
p=Path(__file__).resolve().parent;r=p.parents[1]
out={}
for role,updates in [('wm',1000),('bc',2048),('bridge',600)]:
 runs=[]
 for rr in (21,22):
  intervals=[]
  for seed in (1701,1702,1703):
   stage=r/f'B/rounds/r{rr:02d}'/('wm' if role=='wm' else 'H9-WM')/f'seed{seed}'
   if role!='wm':stage=stage/role
   while not (stage/'receipt.json').is_file():time.sleep(2)
   while True:
    e=next((v for v in reversed([json.loads(l) for l in (stage/'executions.jsonl').open() if l.endswith('\n')]) if v.get('completed')),None)
    if e or (stage/'executions.jsonl').stat().st_mtime<time.time()-10:break
    time.sleep(.5)
   if not e:raise ValueError(stage)
   intervals.append(dict(seed=seed,start=e['started'],end=e['time'],rss_GiB=e['rss_peak_kib']/2**20,gpu_peak_GiB=e['cuda_peak_allocated_MiB']/1024))
  segs=sorted((i['start'],i['end']) for i in intervals);merged=[]
  for l,h in segs:
   if merged and l<=merged[-1][1]:merged[-1][1]=max(h,merged[-1][1])
   else:merged.append([l,h])
  union=sum(h-l for l,h in merged)
  sam=[json.loads(z) for z in (r/'resources.jsonl').open() if z.endswith('\n')];sam=[v for v in sam if any(l<=v['time']<=h for l,h in merged)]
  runs.append(dict(round=rr,intervals=intervals,paid_updates=3*updates,active_wall_s=union,updates_min=3*updates*60/union,whole_gpu_mean=statistics.mean(int(x['gpu_name_usedMiB_totalMiB_utilPC'].split(',')[-1]) for x in sam) if sam else None,samples=len(sam)))
 out[role]=runs
 write(p/'production_prepare_stages.json',dict(at=now(),stages=out,definition='Union of actual registered stage intervals across the three H9-WM seeds. Different matched round workloads; wall time includes data setup and normal verification. Concurrent card-wide GPU sample readings include other processes.',extra_training_updates=0))
