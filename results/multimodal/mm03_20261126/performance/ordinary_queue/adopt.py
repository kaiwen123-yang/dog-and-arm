from pathlib import Path
import json,tempfile,fcntl
from unittest.mock import patch
from scripts.multimodal.mm03_b_parallel import wm_phase_slot,ordinary_capacity,phase_capacity,GIB,wm_replay_budget
from scripts.multimodal.mm03_launch import now,read,write
p=Path(__file__).resolve().parent;r=p.parents[1];wc=read(p/'wm_comparison.json');width=read(p/'width.json')
assert wc['all_full_table_hashes_equal'] and wc['all_window_loss_gradient_rng_hashes_equal'] and wc['new_peak_GiB']<wc['old_peak_GiB']*.65
policy=dict(at=now(),enabled=True,from_round=29,source=str(p/'wm_comparison.json'),note='Preallocate by actual recorded valid_transition shapes; retain distinct states, all camera features, frozen row order and native data. Decide concurrency from currently available hardware.')
cap=read(r/'B/rounds/r28/phase_capacity.json')
with tempfile.TemporaryDirectory(dir=p) as t:
 root=Path(t);folder=root/'B/rounds/r29';folder.mkdir(parents=True)
 member=folder/'members.json';write(member,{})
 write(root/'resources/direct_wm_storage.json',policy)
 test=dict(cap,membership=str(member));write(folder/'phase_capacity.json',test)
 spec=dict(root=str(root),stage='wm',members=str(member),output=str(folder/'wm/seed1701'))
 with patch('scripts.multimodal.mm03_b_parallel.subprocess.check_output',return_value='96000'):
  with wm_phase_slot(spec) as used:assert used
 adm=read(folder/'wm/seed1701/wm_storage_admission.json')
 assert adm['wm_slots']==3 and adm['seed_slots']==3,adm
 write(root/'resources/worker_targets.json',dict(B=4,B_CF=6,B_CF_slots=3))
 write(root/'performance/20261127-ordinary-queue/width.json',width)
 with patch('scripts.multimodal.mm03_b_parallel.host_memory',return_value=(0,96*GIB)):
  with ordinary_capacity(root,4,24,True,partition='rounds/r29/collect') as n:assert n==width['winner'],n
 with patch('scripts.multimodal.mm03_b_parallel.host_memory',return_value=(0,23*GIB)):
  with ordinary_capacity(root,4,24,True,partition='rounds/r29/collect') as n:assert n==10,n
 with ordinary_capacity(root,4,24,False,partition='rounds/r29/collect') as n:assert n==4,n
 with (root/'B/locks/native_cf32.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  with ordinary_capacity(root,4,24,True,partition='rounds/r29/collect') as n:assert n==4,n
write(r/'resources/direct_wm_storage.json',policy)
write(p/'adoption.json',dict(at=now(),policy=policy,measured_peak_reserved_GiB=wc['new_peak_GiB'],reference_R28_world_model_slots=cap['wm_slots'],same_observed_budget_with_new_layout=adm['wm_slots'],same_budget_seed_slots=adm['seed_slots'],expected_peak_budget_GiB_per_WM=adm['wm_gpu_estimate']/GIB,ordinary_winner=width['winner'],training_active_guard_verified=True,busy_CF_slot_guard_verified=True,active_coordinator=read(r/'status/B.json'),extra_optimizer_updates=0,extra_physics_substeps=0))
print(now(),adm,flush=True)
