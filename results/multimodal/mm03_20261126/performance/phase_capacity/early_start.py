from pathlib import Path
import fcntl,json,time
from scripts.multimodal.mm03_b import SEEDS
from scripts.multimodal.mm03_b_rounds import fit_round
from scripts.multimodal.mm03_b_parallel import GIB,GPU_HEADROOM,HOST_HEADROOM,estimated_row_bytes,phase_capacity
from scripts.multimodal.mm03_elastic_trial import active,telemetry
from scripts.multimodal.mm03_launch import now,read,write
r=Path('/root/autodl-tmp/mm03-20261126');p=Path(__file__).resolve().parent;rr=r/'B/rounds/r27'
with (p/'promotion.lock').open('a') as guard:
 fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert read(p/'window_2.json')['seeds']==2
 assert read(r/'C/selection.json')['selected_model_variant']=='CF32' and not (r/'B/candidate_freeze.json').exists()
 assert (rr/'members.json').is_file()
 assert all((rr/'wm'/f'seed{s}'/'receipt.json').is_file() for s in (1701,1702))
 assert not (rr/'H9-WM/seed1703/paired/receipt.json').exists()
 # Do not join a group that was already started with a pre-lock version of the trainer.
 for f in Path('/proc').glob('[0-9]*/cmdline'):
  try:cmd=f.read_bytes().split(b'\0')
  except OSError:continue
  if b'scripts.multimodal.mm03_b_train' in cmd and any(b'/r27/' in x and b'/seed1703/' in x for x in cmd):raise RuntimeError('seed 1703 already owned')
 cfg=read(sorted((r/'B/optimizer_allocations').glob('*_r27.json'))[-1]);assert cfg['slots']==2
 priv=estimated_row_bytes(0,cfg['source_decision_rows']);light=max(2*priv+6*GIB,priv+3*GIB+8*3*GIB//2)
 heavy=cfg['gpu_estimate_per_fit'];host=cfg['private_host_estimate_per_fit']
 n,q=phase_capacity(3,cfg['host_available_bytes'],cfg['gpu_free_bytes'],host,heavy,light)
 assert (n,q)==(3,2),(n,q)
 snap=telemetry();pools=active(r,27); assert len(pools)==2 and all(v==6 for v in pools.values()),pools
 expansion=(3*8-3*6)*(5*GIB//2)
 assert snap['gpu_free_GiB']*GIB>heavy+GPU_HEADROOM and snap['host_free_GiB']*GIB>host+HOST_HEADROOM+expansion,snap
 assert read(p/'window_2.json')['cpu_cores']<22
 stage=dict(cfg,previous_uniform_slots=2,slots=3,wm_slots=2,gpu_estimate_other_fit=light)
 write(rr/'phase_capacity.json',stage)
 write(p/'promotion.json',dict(at=now(),round=27,seed=1703,scope='only the existing registered H9-WM fit; normal coordinator owns scoring and other methods',captured=cfg,admitted=stage,live=snap,initial_pools=pools,extra_updates=0,extra_physics=0,all_seed26_parents=[str(r/f'B/rounds/r26/H9-WM/seed{s}/paired/full.pt') for s in SEEDS]))
 out=fit_round(r,27,'H9-WM',1703,4,'CF32')
 print('completed',out,now(),flush=True)
