from pathlib import Path
import contextlib,io,time,json
from scripts.multimodal import mm03_launch as L
p=Path(__file__).resolve().parent;r=p.parents[1]
while not (p/'decision.json').exists():time.sleep(1.)
pick=L.read(p/'decision.json');widths=L.read(r/'performance/20261126-cf-latency/r22-eight/decision.json')
observed=(pick['candidate_updates_min'] if pick.get('packed_selected') else pick['reference_updates_min']) if pick.get('valid') else widths['challenger_updates_min']
source=r/'performance/20261126-cf-latency/latency_forecast.py'
ns={'__name__':'__main__','__file__':str(source)}
allocs=sorted((r/'B/optimizer_allocations').glob('*_r23.json'));slots=L.read(allocs[-1])['slots'] if allocs else 3
code=source.read_text().replace("observed=evidence['forecast_reference_updates_min']",f"observed={observed}").replace('gpu_serial/2.5',f'gpu_serial/{min(slots,2.5)}').replace('gpu_serial/1.6',f'gpu_serial/{min(slots,1.6)}').replace('extra/2.5',f'extra/{min(slots,2.5)}').replace('extra/1.5',f'extra/{min(slots,1.5)}')
write=L.write
try:
 L.write=lambda *a,**kw:None
 with contextlib.redirect_stdout(io.StringIO()):exec(compile(code,str(source),'exec'),ns)
finally:L.write=write
earliest=ns['result']['conditional_terminal_round'];next_block=4+max(ns['result']['completed_blocks'])
result=dict(at=L.now(),next_block=ns['forecast'](next_block,False),terminal=ns['forecast'](earliest,True),
 another_block=ns['forecast'](earliest+4,True),real_updates_min=observed,slots=slots,
 assumptions='Current paid CF rate and last three ordinary stage receipts. Completion includes terminal cost matching and frozen formal scoring. Further registered progress or resource allocation changes the horizon.')
L.write(p/'forecast.json',result);print(result['terminal']['range_beijing'])
