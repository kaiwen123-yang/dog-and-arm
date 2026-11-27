from pathlib import Path
from contextlib import closing
import importlib.util,tempfile,json,statistics,time
import numpy as np,torch
from scripts.multimodal.mm03_launch import now,read,write
r=Path('/root/autodl-tmp/mm03-20261126');p=Path(__file__).resolve().parent;mp=read(r/'B/rounds/r22/members.json')
def load(name):
 spec=importlib.util.spec_from_file_location(name,p/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.SharedForwardReplay
ref,new=load('h7_reference'),load('h7_candidate')
torch.set_num_threads(1)
times=[];instances=[]
for cls,opt in [(ref,{}),(new,{'cache_index':True}),(new,{'cache_index':True})]:
 t=time.monotonic();obj=cls(r,'cuda:0',extra_ledgers=mp['previous_cf_ledgers'],**opt);times.append(time.monotonic()-t);instances.append(obj)
old,fresh=instances[0],instances[-1]
assert old.files==fresh.files and old.weights==fresh.weights and old.count==fresh.count and np.array_equal(old.probabilities,fresh.probabilities)
results={}
for seed in (1701,1702,1703):
 a,b=np.random.default_rng(seed),np.random.default_rng(seed);same=0
 with closing(fresh.prefetched(32,b,24)) as it:
  for i in range(11):
   x=old.sample(32,a);y=next(it);assert x.keys()==y.keys() and all(torch.equal(x[k],y[k]) for k in x)
   assert a.bit_generator.state==b.bit_generator.state;same+=1
 state=b.bit_generator.state
 c=np.random.default_rng(99);c.bit_generator.state=state
 with closing(fresh.prefetched(32,c,13)) as it:
  for y in it:
   x=old.sample(32,a);assert all(torch.equal(x[k],y[k]) for k in x) and a.bit_generator.state==c.bit_generator.state;same+=1
 results[seed]=same
with tempfile.TemporaryDirectory(dir=p) as tm:
 temp=Path(tm);f=temp/'data.npz';ledger=temp/'file.jsonl';ledger.write_text('{}\n')
 for mask,expected in ((np.ones((2,9),bool),6),(np.zeros((2,9),bool),0)):
  np.savez(f,valid=mask)
  assert new.window_counts(ledger,ledger.read_bytes(),[f],temp/'counts')==[expected]
 np.savez(f,valid=np.array([[1,0,1,0,0,0,0,0,0]],bool))
 try:new.window_counts(ledger,ledger.read_bytes(),[f],temp/'counts')
 except ValueError:pass
 else:raise AssertionError('stale index crossed episode termination')
dur={'serial':[],'prefetch':[]};N=96
for mode in ('serial','prefetch','prefetch','serial'):
 rng=np.random.default_rng(18042);torch.cuda.synchronize();t=time.monotonic()
 if mode=='serial':
  for _ in range(N):old.sample(32,rng)
 else:
  with closing(fresh.prefetched(32,rng,N)) as it:
   for _ in it:pass
 torch.cuda.synchronize();dur[mode].append(time.monotonic()-t)
receipt=dict(at=now(),files=len(old.files),windows=old.count,index_seconds=times,identical_batches_per_seed=results,checkpointed_rng_equal=True,restart_after_11=True,stale_mask_rejected=True,ordered_files_and_weights_identical=True,seconds_per_96_batches=dur,loader_throughput_ratio=statistics.mean(dur['serial'])/statistics.mean(dur['prefetch']),optimizer_updates=0,additional_native_substeps=0)
write(p/'h7_comparison.json',receipt);print(receipt)
