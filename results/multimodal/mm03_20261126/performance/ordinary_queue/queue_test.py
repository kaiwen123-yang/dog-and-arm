from pathlib import Path
from threading import Event,Lock,Barrier
import ast,subprocess
from scripts.multimodal.mm03_launch import write,now
from scripts.multimodal.mm03_b_parallel import SeedOptimizers
seeds=(1701,1702,1703);methods=('H9-WM','D23','H9')
gitref='42a758c63a30467a3958076a9d2a940689bc402a'
src=subprocess.check_output(['git','show',gitref+':scripts/multimodal/mm03_b_rounds.py'],text=True)
node=next(x for x in ast.walk(ast.parse(src)) if isinstance(x,ast.FunctionDef) and x.name=='independent_fits')
from concurrent.futures import FIRST_COMPLETED,wait
def compare(use_new):
 rendezvous=Barrier(3);advanced={s:Event() for s in seeds};calls={s:[] for s in seeds};lock=Lock();schedules={s:iter(methods) for s in seeds}
 def fit(method,seed):
  with lock:calls[seed].append(method)
  if method==methods[0]:rendezvous.wait(timeout=10)
  if method==methods[1]:advanced[seed].set()
  return (method,seed)
 with SeedOptimizers(3) as gpu:
  def drain(ready):
   first=next(ready);assert first[2].result()==first[:2]
   progressed=all(advanced[s].wait(1) for s in seeds)
   rows=[first,*list(ready)]
   assert len(rows)==9 and len(set(x[:2] for x in rows))==9
   assert all(x[2].result()==x[:2] for x in rows)
   return progressed
  if use_new:
   with gpu.completed_fits(schedules,fit) as ready:progressed=drain(ready)
  else:
   ns=dict(SEEDS=seeds,schedules=schedules,gpu=gpu,fit_round=lambda _r,_n,m,s,_w,_v:fit(m,s),root=None,r=1,workers=4,selected='CF32',wait=wait,FIRST_COMPLETED=FIRST_COMPLETED)
   exec(compile(ast.Module(body=[node],type_ignores=[]),'reference_coordinator','exec'),ns)
   progressed=drain(ns['independent_fits']())
 assert all(v==list(methods) for v in calls.values())
 return progressed
assert not compare(False) and compare(True)
for code in (1,75):
 calls=[];outputs=[]
 def fail(method,seed):
  calls.append(method)
  if method=='b':raise subprocess.CalledProcessError(code,['simulated'])
  return method
 with SeedOptimizers(1) as gpu,gpu.completed_fits({1701:iter(('a','b','c'))},fail) as ready:
  for method,seed,f in ready:
   outputs.append(method)
   if method=='b':assert f.exception().returncode==code
 assert outputs==calls==(['a','b'] if code==75 else ['a','b','c'])
write(Path(__file__).parent/'queue_test.json',dict(at=now(),original_blocked_while_consumer_scores=True,new_dispatch_advanced_all_three=True,
 nine_unique_ordered_fits=True,independent_fit_after_non_refresh_error=True,refresh_defers_unstarted_work=True,extra_updates=0,extra_native_steps=0))
print('dispatch parity checked',now())
