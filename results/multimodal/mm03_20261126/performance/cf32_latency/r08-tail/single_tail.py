"""Native capacity in the registered tail of R8 H9-WM after the two sibling seeds have finished."""
from pathlib import Path
import fcntl,json,os,time
from statistics import mean
from scripts.multimodal.mm03_elastic_trial import active,telemetry,paid,process_cpu
from scripts.multimodal.mm03_elastic import busy,pid_stamp
from scripts.multimodal.mm03_resources import update
from scripts.multimodal.mm03_launch import read,write,now
root=Path('/root/autodl-tmp/mm03-20261126'); output=Path(__file__).resolve().parent
stage=root/'B/rounds/r08/H9-WM/seed1702/paired'
siblings=[stage.parents[1]/f'seed{s}/paired/receipt.json' for s in (1701,1703)]
reason='Scoped R8 seed1702 single-tail test with two completed sibling receipts'
control=root/'resources/CF_single_tail.json'
def startable(width):
 actual=active(root,8)
 return len(actual)==1 and list(actual.values())==[width] and not busy(root)
def warmed(width):
 began=None
 while not (stage/'receipt.json').exists():
  n=len((stage/'applied.jsonl').read_text().splitlines())
  if 512-n<105:raise RuntimeError('Insufficient registered updates for two complete windows')
  if startable(width):
   if began is None:began=time.monotonic()
   if time.monotonic()-began>=12:return
  else:began=None
  time.sleep(1.)
 raise RuntimeError('Stage completed')
def sample(width):
 t0=time.time(); t1=t0+90; others=process_cpu(); rows=[]; err=''
 while True:
  d=telemetry();d['ordinary_busy']=busy(root);d['populations']=active(root,8);rows.append(d)
  if d['ordinary_busy'] or list(d['populations'].values())!=[width]:
   err='ordinary work or pool changed';break
  if d['host_free_GiB']<10 or d['gpu_free_GiB']<12 or d['oom_kill']!=rows[0]['oom_kill']:
   err='resource reserve changed';break
  if d['t']>=t1:break
  time.sleep(min(1.5,t1-d['t']))
 after=process_cpu();end=min(t1,rows[-1]['t'])
 result=paid(root,t0,end,8)
 result.update(width=width,valid=not err,reason=err,mean_gpu=mean(d['gpu_util'] for d in rows),min_gpu_free_GiB=min(d['gpu_free_GiB'] for d in rows),min_host_free_GiB=min(d['host_free_GiB'] for d in rows),mean_cpu=(rows[-1]['cpu_usec']-rows[0]['cpu_usec'])/1e6/max(.001,rows[-1]['t']-rows[0]['t']),external_cpu={k:round(after[k]['seconds']-v['seconds'],3) for k,v in others.items() if k in after},samples=len(rows),raw_telemetry=rows)
 return result
def main():
 if (output/'decision.json').exists():return
 assert all(p.exists() for p in siblings)
 reg=dict(at=now(),round=8,seed=1702,baseline=6,challenger=12,registered_updates=512,
     windows_s=[90,90],warm_s=12,criterion='same isolated seed, same ordinary-idle population, better paid updates and physical substeps per minute, same external hot jobs >=90% aggregate/85% per process, CPU <=22 and memory reserves, restore three slots immediately on completion',extra_registered_updates=0)
 write(output/'registration.json',reg)
 previous=read(root/'resources/worker_targets.json')
 assert (previous['B'],previous['B_CF'],previous['B_CF_slots'])==(4,6,3)
 config=dict(phase='trial',pid=os.getpid(),pid_stamp=pid_stamp(os.getpid()),stage=str(stage),original={'B':4,'B_CF':6,'B_CF_slots':3},revert_on_completion=True)
 changed=False
 result=dict(at=now(),winner=6,valid=False,extra_updates=0,extra_training_physics=0)
 try:
  # If another regular batch interrupts the baseline, wait for the next complete quiet window.
  while True:
   warmed(6)
   old=sample(6);write(output/'baseline.json',old)
   if old['valid']:break
  if old['min_host_free_GiB']<19 or old['min_gpu_free_GiB']<15 or old['mean_cpu']>20:raise RuntimeError('Insufficient headroom')
  write(control,config)
  update(root,b=4,b_cf=12,cf_slots=1,reason=reason)
  changed=True
  warmed(12)
  new=sample(12);write(output/'challenger.json',new)
  hot=lambda a:{k:v for k,v in a.items() if v>=5}
  a,b=hot(old['external_cpu']),hot(new['external_cpu'])
  common=set(a)&set(b)
  checks=dict(complete=new['valid'],paid_faster=new['updates_min']>old['updates_min'],physics_faster=new['substeps_s']>old['substeps_s'],cpu_headroom=new['mean_cpu']<=22,external_cohort=set(a)==set(b),external_throughput=all(b[k]>=.85*a[k] for k in common) and sum(b[k] for k in common)>=.9*sum(a[k] for k in common))
  winner=12 if all(checks.values()) else 6
  result.update(at=now(),winner=winner,valid=new['valid'],checks=checks,baseline_updates_min=old['updates_min'],challenger_updates_min=new['updates_min'],baseline_substeps_s=old['substeps_s'],challenger_substeps_s=new['substeps_s'],ratio=new['updates_min']/old['updates_min'])
  write(output/'decision.json',result);print(result,flush=True)
  if winner==12:
   while not (stage/'receipt.json').exists() and len((stage/'applied.jsonl').read_text().splitlines())<512:
    if not active(root,8):break
    time.sleep(1.)
 except Exception as error:
  result.update(at=now(),reason=str(error))
 finally:
  if changed:
   cfg=read(root/'resources/worker_targets.json')
   if cfg.get('reason')==reason:update(root,b=4,b_cf=6,cf_slots=3,reason='Restore the measured three-seed layout after the scoped single-seed tail')
  write(control,dict(**{k:v for k,v in config.items() if k!='phase'},phase='released',at=now()))
  write(output/'decision.json',result)
  print('released',result,flush=True)
if __name__=='__main__':
 with (output/'controller.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);main()
