from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timedelta,timezone
from statistics import median,mean
import json,math
from scripts.multimodal.mm03_launch import DEFAULT as r,read,write,now
p=Path(__file__).resolve().parent
evidence=read(p/'summary.json')
observed=evidence['forecast_reference_updates_min']
workers=4
choice=dict(winner='three')
frozen=read(r/'B/rounds/r04/block.json')
current=datetime.now(timezone(timedelta(hours=8)))
cases=defaultdict(list)
for part in ('collect','development','regression'):
 for f in (r/'B/rounds').glob('r*/'+part+'/*/result.json'):
  d=read(f)
  if d.get('use') not in ('train','evaluation') or d.get('mode') not in ('pure','prefix'):continue
  tag=(part+'_'+d['mode']) if part=='collect' else part
  cases[tag].append((int(d['round']),float(d['wall_s'])))
teacher_secs=mean(read(f)['wall_s'] for f in (r/'B/teachers').glob('*/result.json'))
eff=defaultdict(list)
for f in (r/'B/native_batch_timings').glob('*.json'):
 d=read(f);i=d['partition'].split('/')[-1]
 if d['cases']>=4 and d['elapsed_s']>0 and i in ('collect','development','regression'):
  eff[i].append(min(1.,d['worker_case_wall_s']/d['workers']/d['elapsed_s']))
eff={k:median(v) for k,v in eff.items()}
durations={k:mean(x[1] for x in seq) for k,seq in cases.items()}
stages=defaultdict(list)
for d in (r/'B/rounds').glob('r*'):
 if not d.is_dir():continue
 rr=int(d.name[1:])
 for f in d.glob('wm/seed*/receipt.json'):stages['wm'].append((rr,f))
 for m in ('D23','H9','H9-WM'):
  for role in ('bc','bridge','paired'):
   if role=='paired' and m=='H9-WM':continue
   for f in d.glob(m+'/seed*/'+role+'/receipt.json'):stages[role].append((rr,f))
def stage_time(f):
 e=f.with_name('executions.jsonl')
 if e.exists():
  for q in reversed([json.loads(l) for l in e.open() if l.endswith('\n')]):
   if q.get('event')=='ended' and q.get('completed'):return q['time']-q['started']
 d=read(f);return d.get('wall_s',d.get('wall_s_last_run'))
costs={}
for k,seq in stages.items():
 recent=sorted({n for n,f in seq})[-3:]
 times=[stage_time(f) for n,f in seq if n in recent]
 if not times:times=[stage_time(f) for n,f in seq]
 costs[k]=median(x for x in times if x is not None)
cf={}
for f in (r/'B/rounds').glob('r*/H9-WM/seed*/paired/applied.jsonl'):
 rows=[json.loads(l)['update'] for l in f.open() if l.endswith('\n')];cf[str(f.relative_to(r))]=max(rows,default=0)
def rounded(t,up):
 stamp=(current+timedelta(hours=t)).timestamp()/900
 return datetime.fromtimestamp((math.ceil(stamp) if up else math.floor(stamp))*900,tz=current.tzinfo).isoformat(timespec='minutes')
def forecast(n,final=False):
 targets={'collect_pure':108*n,'collect_prefix':108*n,'development':72*n,'regression':180*(n//4)}
 pending={k:v-sum(rr<=n for rr,_ in cases[k]) for k,v in targets.items()}
 nt={k:pending[k]*durations[k]/workers/eff['collect' if k.startswith('collect') else k]/3600 for k in pending}
 stages_planned={'wm':3*n,'bc':9*n,'bridge':9*n,'paired':6*n}
 missing={k:stages_planned[k]-sum(rr<=n for rr,_ in seq) for k,seq in stages.items()}
 gpu_serial=sum(costs[k]*missing[k] for k in missing)/3600
 owed=1536*n-sum(v for key,v in cf.items() if int(key.split('/')[2][1:])<=n)
 pair=owed/(60*observed)
 # An almost finished round can have just one seed left. Its update rate sets
 # the latency before the next round can use all three independent seed queues.
 open_round=next((rr for rr in range(1,n+1) if not (r/f'B/rounds/r{rr:02d}/H9-WM/seed1701/paired/receipt.json').exists() or not all((r/f'B/rounds/r{rr:02d}/H9-WM/seed{sid}/paired/receipt.json').exists() for sid in (1701,1702,1703))),None)
 if open_round is not None:
  outstanding=[512-cf.get(f'B/rounds/r{open_round:02d}/H9-WM/seed{sid}/paired/applied.jsonl',0) for sid in (1701,1702,1703)]
  two=evidence.get('r08_two_seed_observation',{}).get('paid_by_seed',{})
  single_speed=min([v/1.5 for v in two.values() if v]+[observed/2])
  single=evidence.get('r08_single_seed_tail',{})
  if open_round==8 and single.get('valid') and sum(v>0 for v in outstanding)==1:
   single_speed=single['challenger_updates_min'] if single['winner']==12 else single['baseline_updates_min']
  tail_hours=max(0.,max(outstanding)/single_speed-sum(outstanding)/observed)/60
  pair+=tail_hours
 else:
  tail_hours=0.
 native=sum(nt.values())
 # The physics collection and optimizer queues overlap in the actual launcher.
 # Bounds vary native case duration, batch occupancy, and overlap; they are timing scenarios.
 a,b=pair/.95,native*.95
 low=max(a,b)+.30*min(a,b)+gpu_serial/2.5+.15
 a,b=pair/.78,native*1.25
 high=max(a,b)+.65*min(a,b)+gpu_serial/1.6+.55
 end_hours=[0.,0.]
 if final:
  # Cost matching precedes final freeze; formal/teacher evaluation receives the released pool.
  extra=60000*costs['bc']/2048/3600
  public60=60*durations['regression']/workers/eff['regression']/3600
  formal=(324*durations['development']+16*teacher_secs)/15/eff['development']/3600
  end_hours=[extra/2.5+public60+formal+.10,extra/1.5+1.6*(public60+formal)+.35]
  low+=end_hours[0];high+=end_hours[1]
 return dict(rounds=n,terminal_scoring_included=final,remaining_CF_updates=owed,CF_hours_at_steady_measured_rate=owed/(60*observed),CF_hours_including_single_seed_tail=pair,tail_hours=tail_hours,
    ordinary_pending_cases=pending,ordinary_native_reference_hours_by_kind=nt,ordinary_pending_stages=missing,
    ordinary_gpu_stage_hours_if_serial=gpu_serial,terminal_extra_hours=end_hours,hours_from_observation=[low,high],
    range_beijing=[rounded(low,False),rounded(high,True)])
r8,r12,r16=forecast(8),forecast(12,True),forecast(16,True)
result=dict(as_of_beijing=current.isoformat(timespec='seconds'),selected=choice['winner'],CF_updates_min=observed,
  trained_CF_by_package=cf,paid_CF_to_date=sum(cf.values()),ordinary_workers=workers,observed_mean_case_s=durations,
  cohort_utilization=eff,measured_ordinary_gpu_stage_s=costs,round4_progress=bool(frozen['progress']),
  fourth_round_improved=[x for x in frozen['matched'] if x['progress']],
  first_eight=r8,possible_final_at_twelve=r12,additional_four_h=[b-a for a,b in zip(r12['hours_from_observation'],r16['hours_from_observation'])],
  assumptions="Steady paired hours divide pending updates by the selected observed updates/min. The favorable/conservative scenarios use 95%/78% of the observed pairing rate, native case work x0.95/x1.25, overlap of 70%/35% of the shorter native/paired component, and 2.5/1.6 effective GPU fit slots. Cases may get longer as control improves. Round-12 close requires both rounds 8 and 12 to qualify for the registered plateau. Estimates are not job deadlines.",
  budget=dict(extra_training_updates=0,extra_native_steps_outside_registration=0,formal_cases=324,cost_sensitivity_cases=60,isolated_teacher_cases=16))
result['source_current_speed']=evidence['forecast_reference']
result['peak_ordinary_workers_measured']=12
result['ordinary_reference_note']='Concurrent cohorts use four ordinary workers. The conditional idle-only expansion to twelve is excluded from the projection until future occupancy is measured. Three different fine-tuning seeds preserve the registered number of updates.'
result['diagnostic_physics_separate_receipt']='summary.json'
done_blocks=sorted((int(x.parent.name[1:]),x) for x in (r/'B/rounds').glob('r*/block.json'))
progress_blocks=[k for k,path in done_blocks if read(path).get('progress') or read(path).get('validated_repair')]
earliest=max(8,max(progress_blocks,default=0)+8)
terminal=forecast(earliest,True);following=forecast(earliest+4,True)
result['conditional_terminal_round']=earliest
result['earliest_conditional_finish']=terminal
result['additional_four_h']=[b-a for a,b in zip(terminal['hours_from_observation'],following['hours_from_observation'])]
result['completed_blocks']=dict((k,read(path).get('progress')) for k,path in done_blocks)
if (r/'B/rounds/r08/block.json').is_file():
 result['first_eight']['observed_block_beijing']=datetime.fromtimestamp((r/'B/rounds/r08/block.json').stat().st_mtime,tz=current.tzinfo).isoformat(timespec='minutes')
result['timing_method']='Cumulative registered work, sampled productive triplet, last three available rounds of GPU-stage receipts, capacity four for ordinary workers, explicit per-seed tail estimated from a real two-pool production window.'
write(p/'forecast.json',result)
print(result['as_of_beijing'],result['paid_CF_to_date'],r8['remaining_CF_updates'],r8['range_beijing'],r12['range_beijing'],result['additional_four_h'])
