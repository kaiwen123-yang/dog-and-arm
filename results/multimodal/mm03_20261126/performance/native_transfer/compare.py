from pathlib import Path
import fcntl,json,time,os,statistics
from scripts.multimodal.mm03_launch import now,read,write,pid_stamp
from scripts.multimodal.mm03_elastic_trial import active,telemetry,process_cpu
from scripts.multimodal.mm03_elastic import busy
p=Path(__file__).resolve().parent;root=p.parents[1];n=23
policy=root/'resources/native_transfer_policy.json'
def mode(on,final=False):
 write(policy,dict(from_round=n,packed=on,status='selected' if final else 'trial',pid=os.getpid(),pid_stamp=pid_stamp(os.getpid()),at=now()))
def rows():
 result=[]
 for seed in (1701,1702,1703):
  f=root/f'B/rounds/r{n:02d}/H9-WM/seed{seed}/paired/applied.jsonl'
  result.append([json.loads(l) for l in f.open() if l.endswith('\n')] if f.exists() else [])
 return result
def ready(expected,width):
 start=None
 while True:
  history=rows()
  if max(map(len,history))>=440 or (root/'B/completion.json').exists():raise RuntimeError('No further complete comparable interval in registered round')
  sizes=sorted(active(root,n).values())
  flags=all(len(a)>=2 and all(t.get('packed_native_transfer') is expected for t in a[-2:]) for a in history)
  if flags and len(sizes)==3 and len(set(sizes))==1 and (not width or sizes[0]==width) and not busy(root):
   if start is None:start=time.monotonic()
   if time.monotonic()-start>=5:return sizes[0]
  else:start=None
  time.sleep(1)
def sample(expected,width):
 before=rows();beg=time.monotonic();epoch=time.time();other=process_cpu();samples=[]
 while True:
  d=telemetry();samples.append(d)
  if sorted(active(root,n).values())!=[width]*3 or busy(root):raise RuntimeError('Concurrent load or worker widths changed')
  if d['oom']!=samples[0]['oom'] or d['oom_kill']!=samples[0]['oom_kill'] or d['host_free_GiB']<8 or d['gpu_free_GiB']<12:raise RuntimeError('Insufficient resource reserve')
  left=75-(time.monotonic()-beg)
  if left<=0:break
  time.sleep(min(1.5,left))
 after=rows();end=time.monotonic();extra=process_cpu()
 paid=[b[len(a):] for a,b in zip(before,after)]
 assert all(c and all(x['packed_native_transfer'] is expected for x in c) for c in paid)
 count=sum(map(len,paid));steps=sum(x['native_substeps'] for c in paid for x in c)
 return dict(packed=expected,start_epoch=epoch,seconds=end-beg,paid=count,paid_by_seed=[len(c) for c in paid],substeps=steps,updates_min=60*count/(end-beg),substeps_s=steps/(end-beg),native_per_seed=width,
 mean_gpu=statistics.mean(d['gpu_util'] for d in samples),mean_cpu=(samples[-1]['cpu_usec']-samples[0]['cpu_usec'])/1e6/(samples[-1]['t']-samples[0]['t']),min_gpu_GiB=min(d['gpu_free_GiB'] for d in samples),min_host_GiB=min(d['host_free_GiB'] for d in samples),
 other_jobs_cpu_s={k:round(extra[k]['seconds']-v['seconds'],2) for k,v in other.items() if k in extra and extra[k]['seconds']-v['seconds']>=3})
def main():
 if (p/'decision.json').exists():return
 write(p/'registration.json',dict(at=now(),round=n,order=['separate','packed','packed','separate'],seconds_per_window=75,require='all three seeds, stable native width, ordinary queue idle, every measured application acknowledges its configured transport',selection='enable packed only when both matched pairs gain in paid updates/minute and native substeps/s, resource reserves hold, and the aggregate update gain is at least 1 percent',extra_training_updates=0,extra_native_substeps=0))
 width=None;windows=[];winner=False;decision=dict(round=n,valid=False,extra_training_updates=0,extra_native_substeps=0)
 try:
  for i,on in enumerate((False,True,True,False)):
   mode(on);width=ready(on,width);w=sample(on,width);windows.append(w);write(p/'production.json',dict(windows=windows));print(now(),i,w['updates_min'],flush=True)
  def rate(data,key,factor):return sum(w[key] for w in data)*factor/sum(w['seconds'] for w in data)
  a=[windows[0],windows[3]];b=windows[1:3];old=rate(a,'paid',60);new=rate(b,'paid',60)
  checks=dict(both_update_pairs=all(y['updates_min']>x['updates_min'] for x,y in zip(a,b)),
              both_physics_pairs=all(y['substeps_s']>x['substeps_s'] for x,y in zip(a,b)),aggregate_gain=new/old>=1.01)
  winner=all(checks.values())
  decision.update(valid=True,checks=checks,reference_updates_min=old,candidate_updates_min=new,reference_substeps_s=rate(a,'substeps',1),candidate_substeps_s=rate(b,'substeps',1),throughput_ratio=new/old,external_observation='per-window other CPU time recorded; other jobs untouched')
 except Exception as exc:decision.update(reason=str(exc))
 finally:
  mode(winner,True);decision.update(at=now(),packed_selected=winner);write(p/'decision.json',decision);print(decision,flush=True)
if __name__=='__main__':
 with (p/'controller.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
