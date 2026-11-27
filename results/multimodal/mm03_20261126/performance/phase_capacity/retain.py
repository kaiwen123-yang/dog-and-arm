from pathlib import Path
import time,json,subprocess
from scripts.multimodal.mm03_launch import read,write,now
from scripts.multimodal.mm03_b import refresh_coordinator
p=Path(__file__).resolve().parent;r=p.parents[1]
while not (p/'decision.json').is_file():
 if (p/'trial_error.json').is_file():raise RuntimeError(read(p/'trial_error.json'))
 time.sleep(2)
a,b=(read(p/f'window_{n}.json') for n in (2,3));result=read(p/'decision.json')
if not result.get('valid'):raise ValueError(result)
valid_host=b['min_host_free_GiB']>=8 and b['min_gpu_free_GiB']>=12 and b['oom_kill_change']==0
chosen=3 if result['three_faster'] and valid_host and b['cpu_cores']<=22 else 2
policy=dict(enabled=chosen==3,from_round=28,max_slots=chosen,at=now(),source=str(p/'decision.json'),note='Cap concurrent WM builders by the original WM peak estimate while other trained seeds use the lighter budget. Keep 12 GiB free VRAM, 8 GiB host reserve and the native solver slots. Each round recomputes feasibility.')
write(r/'resources/phase_capacity_policy.json',policy);write(p/'retained_policy.json',policy)
if chosen==3:
 state=read(r/'status/B.json')
 if state['state']=='running' and not (r/'B/coordinator_refresh.json').exists():
  refresh_coordinator(r)
print('policy',chosen,flush=True)
