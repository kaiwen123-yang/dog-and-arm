from pathlib import Path
import contextlib,io,time,statistics
from scripts.multimodal import mm03_launch as L
p=Path(__file__).resolve().parent;r=p.parents[1]
while not (p/'decision.json').is_file():time.sleep(1)
decision=L.read(p/'decision.json')
if not decision.get('complete') or not decision.get('winner'):
 print(decision);raise SystemExit(0)
width=decision['winner']; rate=decision['rates'][str(width)];oldrate=decision['rates']['1']
cf=L.read(p/'production_allocation.json');source=r/'performance/20261126-cf-latency/latency_forecast.py'
def scenario(slots,observed):
 code=source.read_text().replace("observed=evidence['forecast_reference_updates_min']",f"observed={observed}").replace("gpu_serial/2.5",f"gpu_serial/{min(2.5,slots)}").replace("gpu_serial/1.6",f"gpu_serial/{min(1.6,slots)}").replace('extra/2.5',f'extra/{min(2.5,slots)}').replace('extra/1.5',f'extra/{min(1.5,slots)}').replace("tail_hours=max(0.,max(outstanding)/single_speed-sum(outstanding)/observed)/60","tail_hours=max(0.,max(outstanding)/"+str(oldrate)+"-sum(outstanding)/observed)/60")
 ns={'__file__':str(source),'__name__':'__main__'};w=L.write;L.write=lambda *a,**k:None
 try:
  with contextlib.redirect_stdout(io.StringIO()):exec(compile(code,str(source),'exec'),ns)
 finally:L.write=w
 last=ns['result']['conditional_terminal_round']
 return dict(earliest_round=last,next_block=ns['forecast'](24,False),earliest_terminal=ns['forecast'](last,True),another_block=ns['forecast'](last+4,True),updates_min=observed,optimizer_slots=slots,ordinary_workers_assumed=4)
result=dict(as_of_beijing=L.now(),selected=scenario(width,rate),prior_single_scenario=scenario(1,oldrate),assumptions='Uses actual remaining committed work, the measured round-22 CF throughput, native episode timings and stage receipts. Subsequent rounds can choose fewer optimizers when RAM or VRAM is busy; completed archive costs excluded. Final scoring requires two registered plateau blocks.')
L.write(p/'forecast.json',result);print(result['selected']['earliest_terminal']['range_beijing'])
