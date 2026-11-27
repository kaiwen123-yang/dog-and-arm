from pathlib import Path
import fcntl,json,os,time,statistics
from scripts.multimodal.mm03_launch import read,write,now,alive
from scripts.multimodal.mm03_b_parallel import native_slot_path
from scripts.multimodal.mm03_elastic_trial import active,telemetry,process_cpu
from scripts.multimodal.mm03_elastic import busy
p=Path(__file__).resolve().parent;root=p.parents[1];round_no=22
phase=root/'B/rounds/r22/H9-WM';seeds=(1701,1702,1703)
def sums():
 out={}
 for sid in seeds:
  journal=phase/f'seed{sid}/paired/applied.jsonl'
  if not journal.is_file():out[str(sid)]=(0,0);continue
  rows=[json.loads(l) for l in journal.open() if l.endswith('\n')]
  assert all(i==row['update'] for i,row in enumerate(rows,1))
  out[str(sid)]=(len(rows),sum(x['native_substeps'] for x in rows))
 return out
def owns(p):
 if not p.exists():return False
 with p.open('a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return False
  except BlockingIOError:return True
def population(n):
 sizes=active(root,round_no)
 return len(sizes)==n and all(5<=v<=8 for v in sizes.values()) and not busy(root)
def wait_warm(n,expected):
 warm=None;last_sizes=None
 while True:
  if max(v[0] for v in sums().values())>440 or any(phase.glob('seed*/paired/receipt.json')):raise RuntimeError('A registered seed is approaching its endpoint')
  if not alive(read(root/'status/B.json')):raise RuntimeError('Coordinator restarting')
  sizes=sorted(active(root,round_no).values())
  ready=sum(owns(phase/f'seed{s}/paired/native_stage_owner.lock') for s in seeds)
  if ready>=expected and len(sizes)==n and population(n):
   if warm is None or last_sizes!=sizes:warm=time.monotonic()
   if time.monotonic()-warm>10:return
  else:warm=None
  last_sizes=sizes;time.sleep(1.)
def sample(n):
 before=sums();t0=time.monotonic();epoch=time.time();other=process_cpu();info=[];bad=''
 while True:
  rec=telemetry();rec['widths']=sorted(active(root,round_no).values());info.append(rec)
  if len(rec['widths'])!=n or busy(root):bad='native population or ordinary queue changed';break
  if rec['oom_kill']!=info[0]['oom_kill'] or rec['oom']!=info[0]['oom'] or rec['host_free_GiB']<8 or rec['gpu_free_GiB']<12:bad='memory reserve or OOM counter changed';break
  remaining=90-(time.monotonic()-t0)
  if remaining<=0:break
  time.sleep(min(1.5,remaining))
 after=sums();dt=time.monotonic()-t0;other2=process_cpu()
 counts={k:after[k][0]-before[k][0] for k in before};native=sum(after[k][1]-before[k][1] for k in before)
 result=dict(at=now(),round=round_no,active_seeds=n,valid=not bad and sum(v>0 for v in counts.values())==n,reason=bad,
  start_epoch=epoch,seconds=dt,before=before,after=after,paid_by_seed=counts,updates=sum(counts.values()),
  updates_min=sum(counts.values())*60/dt,substeps=native,substeps_s=native/dt,
  mean_gpu=statistics.mean(r['gpu_util'] for r in info),
  mean_cpu=(info[-1]['cpu_usec']-info[0]['cpu_usec'])/1e6/(info[-1]['t']-info[0]['t']),
  min_host_free_GiB=min(r['host_free_GiB'] for r in info),min_gpu_free_GiB=min(r['gpu_free_GiB'] for r in info),
  other_cpu_seconds={k:round(other2[k]['seconds']-v['seconds'],2) for k,v in other.items() if k in other2 and other2[k]['seconds']-v['seconds']>1},
  first_widths=info[0]['widths'],last_widths=info[-1]['widths'],samples=len(info),extra_training_updates=0,extra_native_substeps=0)
 write(p/f'window_{n}.json',result);print('window',n,result['valid'],result['updates_min'],flush=True);return result
def main():
 if (p/'decision.json').exists():return
 locks={};windows=[];reason=''
 try:
  while True:
   allocs=sorted((root/'B/optimizer_allocations').glob('*_r22.json'),reverse=True)
   if allocs and read(allocs[0]).get('image_storage')=='shared_original_npy':break
   if (root/'B/completion.json').exists() or (root/'B/rounds/r22/block.json').exists():raise RuntimeError('Mapped cohort not available')
   time.sleep(2)
  alloc=read(allocs[0]);slots=alloc['slots'];write(p/'production_allocation.json',alloc)
  for i in range(1,slots):
   handle=native_slot_path(root/'B/locks',i).open('a');fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);locks[i]=handle
  print('admitted',slots,now(),flush=True)
  for n in range(1,slots+1):
   if n>1:locks.pop(n-1).close()
   wait_warm(n,slots)
   result=sample(n);windows.append(result)
   if not result['valid']:raise RuntimeError(result['reason'] or 'incomplete paid window')
 except Exception as ex:reason=str(ex)
 finally:
  for f in locks.values():f.close()
  valid=[x for x in windows if x['valid']];chosen=1
  if valid:
   best=valid[0]
   for x in valid[1:]:
    if x['updates_min']>best['updates_min'] and x['substeps_s']>best['substeps_s']:best=x
   chosen=best['active_seeds']
  policy_file=root/'resources/mapped_image_policy.json';policy=read(policy_file)
  complete=bool(windows) and len(valid)==read(p/'production_allocation.json').get('slots',0)
  if complete:
   policy.update(max_slots=chosen,decision=str(p/'decision.json'));write(policy_file,policy)
  write(p/'decision.json',dict(at=now(),complete=complete,reason=reason,winner=chosen if complete else None,
       rates={x['active_seeds']:x['updates_min'] for x in valid},max_future_slots=policy.get('max_slots'),extra_training_updates=0,extra_native_substeps=0))
if __name__=='__main__':
 with (p/'controller.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
