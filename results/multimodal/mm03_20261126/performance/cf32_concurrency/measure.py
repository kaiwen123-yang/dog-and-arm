import argparse,datetime,json,os,statistics,subprocess,time
from pathlib import Path
p=Path(__file__).resolve().parent;r=p.parent.parent
def rd(f):return json.loads(f.read_text()) if f.is_file() else {}
def put(f,d):
 tmp=f.with_name(f'.{f.name}.{os.getpid()}.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,f)
def stamp():return datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')
def system():
 cg=Path('/sys/fs/cgroup')
 cpu=dict(x.split() for x in (cg/'cpu.stat').read_text().splitlines())
 mem=dict(x.split() for x in (cg/'memory.stat').read_text().splitlines())
 ev=dict(x.split() for x in (cg/'memory.events').read_text().splitlines())
 vals=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,power.draw','--format=csv,noheader,nounits'],text=True).split(',')
 return dict(when=stamp(),epoch=time.time(),cpu_us=int(cpu['usage_usec']),anon_GiB=int(mem['anon'])/2**30,memory_current_GiB=int((cg/'memory.current').read_text())/2**30,oom_kill=int(ev['oom_kill']),gpu_percent=float(vals[0]),gpu_MiB=float(vals[1]),watts=float(vals[2]))
def counts(phase):
 result={}
 for seed in (1701,1702,1703):
  d=r/f'B/rounds/r02/H9-WM/seed{seed}/paired'
  f=d/'applied.jsonl'
  rows=[]
  if f.is_file():
   with f.open() as h:
    rows=[json.loads(l) for l in h if l.endswith('\n')]
  indices=[x['update'] for x in rows]
  if indices!=list(range(1,len(rows)+1)):raise ValueError(f'Repeated/skipped application in {f}')
  result[str(seed)]=dict(count=len(rows),substeps=sum(x['native_substeps'] for x in rows),queries=sum(x['model_queries'] for x in rows),valid=sum(x['legal'] for x in rows))
 return result
def capture():return dict(when=stamp(),monotonic=time.monotonic(),epoch=time.time(),seeds=counts('paired'))
def delta(after,before):
 return {s:{k:v-before[s][k] for k,v in data.items()} for s,data in after.items()}
def measure(tag):
 target=rd(p/'registration.json')['baseline' if tag.startswith('two') else 'challenger']
 resources=rd(r/'resources/worker_targets.json')
 assert all(resources[k]==v for k,v in target.items()),(target,resources)
 file=p/f'{tag}.json'
 if file.is_file():print(f'Already measured {file}',flush=True);return
 start=capture();prev=start;wins=[];samples=[system()];expected=target['B_CF_slots'];print(stamp(),tag,start['seeds'],flush=True)
 for i in range(3):
  end=start['monotonic']+(i+1)*60
  while (remain:=end-time.monotonic())>0:
   time.sleep(min(1.5,remain))
   if end-time.monotonic()>.4:samples.append(system())
  cur=capture();d=delta(cur['seeds'],prev['seeds']);elapsed=cur['monotonic']-prev['monotonic']
  ups=sum(v['count'] for v in d.values());steps=sum(v['substeps'] for v in d.values())
  window=dict(number=i+1,until=cur['when'],elapsed_s=elapsed,per_seed=d,updates=ups,updates_min=ups*60/elapsed,native_steps=steps,native_steps_s=steps/elapsed)
  if sum(v['count']>0 for v in d.values())!=expected:raise RuntimeError(f'Not all {expected} independent optimizers contributed {window}')
  if any(rd(r/'resources/worker_targets.json')[k]!=v for k,v in target.items()):raise RuntimeError('Worker target changed during measurement')
  wins.append(window);put(p/f'{tag}_progress.json',dict(start=start,windows=wins,latest=cur));print(stamp(),tag,i+1,ups,flush=True);prev=cur
 samples.append(system());d=delta(prev['seeds'],start['seeds']);t=prev['monotonic']-start['monotonic'];n=sum(x['count'] for x in d.values());steps=sum(x['substeps'] for x in d.values())
 result=dict(tag=tag,config=target,start=start,end=prev,elapsed_s=t,per_seed=d,aggregate_updates=n,updates_min=n*60/t,native_substeps=steps,native_substeps_s=steps/t,steps_per_update=steps/n,windows=wins,telemetry=dict(gpu_mean_percent=statistics.mean(x['gpu_percent'] for x in samples),gpu_median_percent=statistics.median(x['gpu_percent'] for x in samples),gpu_peak_MiB=max(x['gpu_MiB'] for x in samples),cpu_mean_cores=(samples[-1]['cpu_us']-samples[0]['cpu_us'])/1e6/(samples[-1]['epoch']-samples[0]['epoch']),peak_anon_GiB=max(x['anon_GiB'] for x in samples),oom_kills=samples[-1]['oom_kill']-samples[0]['oom_kill']),samples=samples)
 put(file,result);print(stamp(),tag,result['updates_min'],result['native_substeps_s'],flush=True)
if __name__=='__main__':
 import sys
 measure(sys.argv[1])
