from pathlib import Path
import json,os,sys,fcntl,time
from scripts.multimodal.mm03_launch import DEFAULT as r,read,write,now,alive
from scripts.multimodal.mm03_resources import update
from measure import counts,measure
p=Path(__file__).resolve().parent
assert r==p.parent.parent
def stage(name,**extra):
 record=dict(at=now(),stage=name,**extra);write(p/'state.json',record)
 with (p/'events.jsonl').open('a',buffering=1) as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
 print(now(),name,flush=True)
def live():
 s=read(r/'status/B.json')
 if s.get('state')!='running' or not alive(s):raise RuntimeError(('B requires inspection',s))
def workers():
 result={}
 for seed in ('1701','1702','1703'):
  d=r/f'B/rounds/r02/H9-WM/seed{seed}/paired'
  fs=sorted(d.glob('native_slot_*.json'),key=lambda f:f.stat().st_mtime)
  if not fs or (d/'receipt.json').is_file():continue
  rec=read(fs[-1]);pid=rec['pid']; proc=Path('/proc')/str(pid)
  if not proc.exists():continue
  cs=set()
  for f in (proc/'task').glob('*/children'):
   try: cs.update(f.read_text().split())
   except OSError: pass
  running=[]
  for entry in cs:
   try:
    if b'scripts.multimodal.mm03_c_native' in Path('/proc',entry,'cmdline').read_bytes():running.append(int(entry))
   except OSError:pass
  result[seed]=dict(pid=pid,slot=rec['index'],workers=sorted(running))
 return result
def ready(expected,width):
 w=workers()
 return set(w)==set(expected) and len(set(q['slot'] for q in w.values()))==len(expected) and all(len(q['workers'])==width for q in w.values())
def target(b,cf,slots,why):
 return update(r,b=b,c=None,reason=why,b_gpu=3,b_cf=cf,cf_slots=slots)
def choose():
 a,b=(read(p/f'{tag}.json') for tag in ('two','three'))
 gain=b['updates_min']/a['updates_min']-1
 valid=b['telemetry']['oom_kills']==0 and a['telemetry']['oom_kills']==0
 winner='three' if valid and gain>0 else 'two'
 if valid and abs(gain)<.03:
  stage('near_tie_more_measurement_needed',observed_relative_gain=gain)
  return
 if winner=='two':
  target(4,6,2,'Close third CF admission after measured lower three-seed throughput; drain its outstanding lease at a normal boundary.')
  # On return to a two-slot target, a previously admitted third slot runs out its existing stage.
  # Acquire only its released lease, then restore the measured eight-worker baseline for the two remaining permits.
  with (r/'B/locks/native_cf32_2.lock').open('a') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   target(6,8,2,'The third CF lease drained. Retain the measured faster two-seed configuration.')
 else:
  target(4,6,3,'Three actual independent CF32 seeds have higher measured paid updates per minute.')
 stage('selected',winner=winner,relative_gain=gain)
 write(p/'decision.json',dict(at=now(),winner=winner,relative_updates_gain_three_vs_two=gain,classification='production CF32 paired updates',
   two_updates_min=a['updates_min'],three_updates_min=b['updates_min'],two_substeps_s=a['native_substeps_s'],three_substeps_s=b['native_substeps_s'],
   retained_target=read(r/'resources/worker_targets.json'),live_owners=workers(),training_budget_increment=0,additional_physics_outside_registered_updates=0))
if __name__=='__main__':
 with (p/'controller.lock').open('a') as f:
  fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if not (p/'decision.json').exists():
   if not (p/'three.json').exists():
    stage('baseline_in_progress')
    while not (p/'two.json').is_file():live();time.sleep(.25)
    base=read(p/'two.json');assert base['aggregate_updates']>0 and base['telemetry']['oom_kills']==0
    stage('shrinking_two_existing_pools',before=workers())
    target(4,6,2,'Registered comparison: resize the existing two native pools at independent CF batches before admitting the third.')
    while not ready(('1701','1703'),6):live();time.sleep(.25)
    checkpoint=counts('paired')
    stage('admitting_third_seed',before=workers(),paid_before=checkpoint)
    target(4,6,3,'Measure three independent H9-WM CF32 seeds on the same 25-core allocation: three native pools of six plus four ordinary workers.')
    while True:
     live(); cur=counts('paired')
     if ready(('1701','1702','1703'),6) and all(cur[s]['count']-checkpoint[s]['count']>=10 for s in cur):break
     if any(x['count']>=512 for x in cur.values()):
      raise RuntimeError('A seed completed before the common three-seed sampling window')
     time.sleep(1)
    stage('three_active_measurement',owners=workers(),paid=cur)
    measure('three')
   choose()
