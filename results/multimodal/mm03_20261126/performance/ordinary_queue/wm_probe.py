from pathlib import Path
import sys,os,time,json,importlib.util,hashlib,resource,subprocess
import numpy as np,torch
from scripts.multimodal.mm03_launch import read,write,now
from scripts.multimodal.train_wm import physical_loss
from learning.multimodal.world_model import PerceptualDynamics
p=Path(__file__).resolve().parent;r=p.parents[1];device=torch.device('cuda:0')
mode=sys.argv[1];direct=mode=='direct'
torch.set_num_threads(1);torch.set_float32_matmul_precision('high')
code='wm_direct.py' if direct else 'wm_original.py';name='learning.multimodal._mm03_replay_probe'
spec=importlib.util.spec_from_file_location(name,p/code);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
f=r/'B/rounds/r28/members.json';mp=read(f);members=list(dict.fromkeys(mp['wm']))
def free_gpu():return int(subprocess.check_output(['nvidia-smi','-i','0','--query-gpu=memory.free','--format=csv,noheader,nounits'],text=True).strip())
while free_gpu()<40*1024:time.sleep(3)
torch.cuda.reset_peak_memory_stats();t=time.monotonic()
kwargs={'direct_storage':True} if direct else {}
replay=module.PhysicalReplay(None,'train',device,episode_dirs=members,**kwargs)
torch.cuda.synchronize();build_s=time.monotonic()-t
pre_peak=torch.cuda.max_memory_reserved()/2**30
# Compare every stored replay byte, in bounded CPU chunks; no simulation or optimizer step.
def digest(t):
 h=hashlib.sha256()
 for i in range(0,t.shape[0],32768):h.update(t[i:i+32768].detach().cpu().contiguous().numpy().tobytes())
 return h.hexdigest()
all_arrays={k:digest(v) for k,v in replay.parts.items()}
for k in ('base','end','episode_index','prefix_p','prefix_prev'):all_arrays[k]=digest(getattr(replay,k))
all_arrays['starts'],all_arrays['contact_starts']=[digest(x) for x in replay.starts(7)]
ck=torch.load(r/'B/rounds/r27/wm/seed1701/wm.pt',map_location=device,weights_only=False)
model=PerceptualDynamics(ck['width']).to(device);model.load_state_dict(ck['model']);checks={}
for seed in (1701,1702,1703):
 rng=torch.Generator(device=device).manual_seed(seed)
 ix=replay.draw_starts(7,128,rng,True);win=replay.window(ix,7)
 loss=physical_loss(model,win);grad=torch.autograd.grad(loss,[x for x in model.parameters() if x.requires_grad],allow_unused=True)
 checks[str(seed)]=dict(draw=digest(ix),window={k:digest(v) for k,v in win.items()},loss=float(loss.detach()),grad=[digest(g.reshape(-1)) if g is not None else None for g in grad],rng=digest(rng.get_state()))
result=dict(at=now(),mode=mode,round=28,membership_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),episodes=len(replay.episodes),rows=replay.parts['p'].shape[0],logical_bytes=sum(v.numel()*v.element_size() for v in replay.parts.values()),build_s=build_s,build_peak_reserved_GiB=pre_peak,max_reserved_GiB=torch.cuda.max_memory_reserved()/2**30,rss_peak_GiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**20,arrays=all_arrays,batches=checks,gradient_evaluations=3,optimizer_updates=0,native_substeps=0)
write(p/f'wm_{mode}.json',result);print(mode,result['rows'],build_s,pre_peak,result['max_reserved_GiB'],flush=True)
if direct:
 old=read(p/'wm_reference.json')
 for k in ('arrays','batches','membership_sha256','episodes','rows','logical_bytes'):assert old[k]==result[k],k
 assert pre_peak<old['build_peak_reserved_GiB']
 write(p/'wm_comparison.json',dict(at=now(),round=28,episodes=result['episodes'],rows=result['rows'],old_build_s=old['build_s'],direct_build_s=build_s,old_peak_GiB=old['max_reserved_GiB'],new_peak_GiB=result['max_reserved_GiB'],old_build_peak_GiB=old['build_peak_reserved_GiB'],new_build_peak_GiB=pre_peak,all_full_table_hashes_equal=True,all_window_loss_gradient_rng_hashes_equal=True,seeds=[1701,1702,1703],extra_gradient_evaluations=6,extra_native_steps=0,extra_optimizer_updates=0))
