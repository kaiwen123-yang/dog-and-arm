from pathlib import Path
import time,contextlib,io,statistics
from scripts.multimodal import mm03_launch as L
p=Path(__file__).resolve().parent;r=p.parents[1]
while not (p/'retained_policy.json').exists():
 if (p/'trial_error.json').exists():raise RuntimeError(L.read(p/'trial_error.json'))
 time.sleep(1)
two=L.read(p/'window_2.json')['updates_min'];three=L.read(p/'window_3.json')['updates_min']
f=r/'performance/20261126-cf-latency/latency_forecast.py';rates=[]
for i in (25,26):
 o=r/f'B/rounds/r{i}/H9-WM/seed1703/paired/applied.jsonl'
 import json
 rows=[json.loads(l) for l in o.open() if l.endswith('\n')][-257:]
 rates.append((len(rows)-1)*60/(Path(rows[-1]['shared_native_replay']).stat().st_mtime-Path(rows[0]['shared_native_replay']).stat().st_mtime))
single=statistics.mean(rates)
def predict(slots,rate):
 text=f.read_text().replace("observed=evidence['forecast_reference_updates_min']",f"observed={rate}")
 for name in ('gpu_serial','extra'):
  text=text.replace(name+'/2.5',name+'/'+str(min(2.5,slots))).replace(name+'/1.6',name+'/'+str(min(1.6,slots)))
 text=text.replace('max(outstanding)/single_speed','max(outstanding)/'+str(single))
 ns={'__name__':'__main__','__file__':str(f)};old=L.write;L.write=lambda *a,**kw:None
 try:
  with contextlib.redirect_stdout(io.StringIO()):exec(compile(text,str(f),'exec'),ns)
 finally:L.write=old
 terminal=ns['result']['conditional_terminal_round'];nextblock=max(ns['result']['completed_blocks'])+4
 return dict(rate=rate,slots=slots,next_block=ns['forecast'](nextblock,False),terminal=ns['forecast'](terminal,True),extension=ns['forecast'](terminal+4,True))
prior=predict(2,1536/(1024/two+512/single));selected=predict(3,three) if L.read(p/'retained_policy.json')['enabled'] else prior
L.write(p/'forecast.json',dict(at=L.now(),prior=prior,selected=selected,standalone_seed_rate=single,assumptions='From live receipts with the same remaining work. Later cohorts recheck available GPU and host memory; terminal includes 324 formal, 60 cost and 16 isolated teacher cases. Further physical progress extends by four rounds.'))
print(selected['terminal']['range_beijing'])
