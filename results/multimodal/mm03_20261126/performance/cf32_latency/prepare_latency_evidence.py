from pathlib import Path
from statistics import mean
from datetime import datetime,timezone,timedelta
import json,os
p=Path(__file__).resolve().parent
r=p.parents[1]
def read(f):
 return json.loads(f.read_text()) if f.is_file() else {}
def save(name,value):
 f=p/name; tmp=f.with_name("."+f.name+f".{os.getpid()}.part");tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n");os.replace(tmp,f)
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
def write_md(f,content):
 tmp=f.with_name("."+f.name+f".{os.getpid()}.part");tmp.write_text(content.rstrip()+"\n");os.replace(tmp,f)
# Record the registered ordinary cohorts that bracketed the return of all three CF slots.
batches=[]
for f in sorted((r/'B/native_batch_timings').glob('*.json')):
 d=read(f)
 if d.get('partition')=='rounds/r08/collect' and any('_H9_'+str(s)+'_' in d['dispatch_order'][0] for s in (1701,1702)) and d['cases']==24:
  batches.append({'source':str(f.relative_to(r)),**{k:d[k] for k in ('workers','cases','elapsed_s','physical_substeps','substeps_per_s','start_epoch','dispatch_order')}})
ordinary={str(x['workers']):x for x in batches}
if '4' in ordinary and '12' in ordinary:
 save('ordinary_capacity.json',dict(before=ordinary['4'],after=ordinary['12'],scope='Registered round 8 H9 24-case collection, different seeds 1701 and 1702 and their original trajectories. Native substeps per wall second. Neither cohort was rerun.',throughput_ratio=ordinary['12']['substeps_per_s']/ordinary['4']['substeps_per_s'],extra_cases=0,extra_updates=0))
# Record interrupted-step recovery outside the registered training and microbenchmark ledgers.
repair_folder=r/'B/rounds/r08/H9-WM/seed1702/paired/recovery_after_sigkill'
rebuild=read(repair_folder/'reconstruction.json')
if rebuild.get('reconstructed_step')==2 and rebuild.get('unchanged_original_ledger'):
 save('r08_recovery.json',dict(as_of_beijing=rebuild['at'],round=8,seed=1702,recomputed_native_substeps=rebuild['native_restore_substeps'],recomputed_optimizer_applications=rebuild['restore_forward_backward_adam'],registered_extra_updates=rebuild['additional_distinct_updates'],registered_extra_rows=rebuild['additional_training_rows'],source_exit_signal=9,kernel_oom_kill_delta=0,exit_signal_origin='undetermined',reconstruction=rebuild,raw_physical=read(repair_folder/'physical_recovery.json'),gradient_comparison=read(repair_folder/'gradient_comparison.json')))
# Persist a process-level check that the compiled reader is actually mapped by paid CF workers.
loaded={}
for pid in Path('/proc').glob('[0-9]*'):
 try:
  args=(pid/'cmdline').read_bytes().split(b'\0')
  if b'scripts.multimodal.mm03_c_native' in args and b'--worker' in args:
   lines=[line.split()[-1] for line in (pid/'maps').read_text().splitlines() if 'wheel_normals_' in line]
   if lines: loaded[pid.name]=lines[0]
 except (OSError,UnicodeDecodeError):pass
if loaded:save('native_loading.json',dict(as_of_beijing=now(),mapped_probe='Live native CF32 worker /proc/<pid>/maps',workers=loaded))
wheel=read(p/'native_wheel_results.json'); latency=read(p/'live_native_overlap.json');elastic=read(p/'elastic_trial.json')
parity=[read(p/(n+'_parity.json')) for n in ('full_h9','partial_direct23')]
loan=read(p/'b_ordinary_production_lease.json')['observed_loans']
seven=max(x['production_rate_window']['updates_per_minute'] for x in loan if x.get('all_three_confirmed') and x.get('production_rate_window'))
tests=sorted(p.glob('r[0-9][0-9]-eight'))
measured=[t for t in tests if read(t/'decision.json').get('valid')]
current_test=measured[-1] if measured else (tests[-1] if tests else p/'r08-eight')
decision=read(current_test/'decision.json')
rate=seven
source='r07 three live seven-worker optimizers, 90s'
if decision.get('valid'):
 which='challenger' if decision['winner']=='eight' else 'baseline'
 item=read(current_test/(which+'.json'))
 if item.get('valid'):
  rate=item['updates_min'];source=current_test.name+'/'+which+'.json'
prev=read(p.parent/'cf32-three-seeds-20261126'/'three.json')
extra=sum(x['captured_native_substeps'] for x in parity)+latency['actual_diagnostic_substeps']+read(p/'cf_profile.json')['native_substeps']+wheel['diagnostic_native_substeps']
oc=read(p/'ordinary_capacity.json')
brief=(f"第六轮三个种子每个从 6 增至 7 个物理进程，实付更新由 {elastic['baseline']['updates_min']:.1f} 增至 {elastic['challenger']['updates_min']:.1f} 次/分。"
       f"同锚点 H32 真前向及完整反传从 {mean(latency['wall_s']['reference']):.2f} 秒缩至 {mean(latency['wall_s']['candidate']):.2f} 秒，"
       f"单个原生进程的轮地接触读取对照达到原吞吐的 {wheel['cf']['speedup']:.2f} 倍。")
if oc:brief+=f"第八轮 H9 采集的两个 24 案批次，以 4 和 12 个进程分别完成 {oc['before']['substeps_per_s']:,.0f} 和 {oc['after']['substeps_per_s']:,.0f} 个物理子步/秒。"
summary=dict(as_of_beijing=now(),pool_trial_r06=elastic['throughput_ratio'],pool_trial_r07_updates_min=seven,wall_overlap_speedup=latency['speedup'],wheel_only_worker_speedup=wheel['cf']['speedup'],ordinary_native_comparison=oc.get('throughput_ratio'),native_loading_receipt='native_loading.json',new_benchmark_native_substeps=extra,extra_training_optimizer_updates_for_benchmarks=0,current_trial_directory=current_test.name,registered_production_progress_used_for_throughput=True,eight_worker_trial=decision or {'status':'awaiting comparable production window'},forecast_reference_updates_min=rate,forecast_reference=source,summary_zh=brief)
if decision.get('valid'):
 summary['summary_zh']+=f"第{decision['round']}轮 7/8 进程登记对照选择了每种子 {8 if decision['winner']=='eight' else 7} 个，普通采集有需求时归还额度。"
if rebuild and rebuild.get('reconstructed_step')==2:
 summary['separate_recovery_native_substeps']=rebuild['native_restore_substeps']
 summary['separate_recovery_adam_applications']=rebuild['restore_forward_backward_adam']
# First quiet 90 s after the last ordinary cohort in the common R8 two-pool interval.
pair_by_seed={}
for sid in (1701,1702,1703):
 journal=r/f'B/rounds/r08/H9-WM/seed{sid}/paired/applied.jsonl'
 rows=[]
 if journal.is_file():
  for line in journal.open():
   if line.endswith('\n'):
    row=json.loads(line)
    replay=Path(row['shared_native_replay'])
    rows.append((replay.stat().st_mtime,row['native_substeps']))
 pair_by_seed[sid]=rows
if pair_by_seed[1701] and pair_by_seed[1703]:
 a=max(pair_by_seed[s][0][0] for s in (1701,1703))
 b=min(pair_by_seed[s][-1][0] for s in (1701,1703))
 windows=[]
 for f in (r/'B/native_batch_timings').glob('*.json'):
  d=read(f); t=d['start_epoch'];u=t+d['elapsed_s']
  if t<b and u>a:windows.append((max(a,t),min(b,u)))
 left=a
 for start,end in sorted(windows)+[(b,b)]:
  if start-left>=120:
   t0=left+30;t1=t0+90
   picked={str(k):[n for t,n in rows if t0<t<=t1] for k,rows in pair_by_seed.items()}
   if not picked['1702'] and all(picked[str(k)] for k in (1701,1703)):
    samples=[json.loads(l) for l in (r/'resources.jsonl').open() if l.endswith('\n')]
    gpu=[int(v['gpu_name_usedMiB_totalMiB_utilPC'].split(',')[-1]) for v in samples if t0<v['time']<=t1]
    summary['r08_two_seed_observation']=dict(first_eligible_ordinary_idle_90s_after_30s_warm=True,start_epoch=t0,end_epoch=t1,paid_by_seed={k:len(ns) for k,ns in picked.items()},updates_min=sum(map(len,picked.values()))/1.5,native_substeps=sum(map(sum,picked.values())),sampled_whole_GPU_mean_pct=mean(gpu) if gpu else None,whole_gpu_samples=len(gpu),extra_updates=0)
    break
  left=max(left,end)
tail=read(p/'r08-tail/decision.json')
if tail:
 summary['r08_single_seed_tail']=tail
 if tail.get('valid'):
  summary['summary_zh']+=f"仅余种子 1702 时，6/12 进程同种子生产对照分别实付 {tail['baseline_updates_min']:.1f}/{tail['challenger_updates_min']:.1f} 次/分，剩余更新采用 {tail['winner']} 进程。"
save('summary.json',summary)
forecast=read(p/'forecast.json')
eta=""
if forecast:
 first=forecast['first_eight']
 when="第八轮记录完成于 "+first['observed_block_beijing'] if first.get('observed_block_beijing') else "第八轮记录预计在 "+' 至 '.join(first['range_beijing'])+" 完成"
 terminal=forecast.get('earliest_conditional_finish',forecast['possible_final_at_twelve'])
 eta=f"\n\n以 {forecast['as_of_beijing']} 的在途回执估计，{when}。若后续工作块达到连续两块的平台期条件，最早可在第 {terminal['rounds']} 轮结案，含正式评测的北京时间区间为 {' 至 '.join(terminal['range_beijing'])}。"
md=f"""# CF32 与采集的实测吞吐

{summary['as_of_beijing']} 北京时间。{brief}

| 工作量 | 对照与结果 |
|---|---|
| 三个种子，两个 90 秒生产窗口 | 每种子 6 个物理进程共 {elastic['baseline']['total_updates']} 个注册更新，7 个共 {elastic['challenger']['total_updates']} 个。第七轮 7 进程再测为每分钟 {seven:.1f} 个。见 [R6](elastic_trial.json) 和 [R7](b_ordinary_production_lease.json)。 |
| 同一批 32 个冻结锚点，H32，两个真实物理进程 | 旧、新、新、旧，计入前向、重放整理和完整反传，Adam 单独执行。见 [逐次计时](live_native_overlap.json)。 |
| 完整和提前终止的真实输入 | 实际动作、回放数组、损失与全部梯度逐位一致。分别涉及 {parity[0]['gradient_tensors']} 和 {parity[1]['gradient_tensors']} 个梯度张量，第二个批次有 {parity[1]['terminal_lanes']} 条中途终止。见 [H9](full_h9_parity.json) 和 [D23](partial_direct23_parity.json)。 |
| 原生轮地接触读取 | 普通和优化实现逐个 2 毫秒子步核对。拉 15 度和推 25 度教师均完成 12 个事件，两条学生失败轨迹保持原判。涉及其他接触或需要滑移时使用原观察器。见 [逐案物理对照](native_wheel_results.json) 和 [运行进程](native_loading.json)。 |
| 空闲进程配额用于普通采集 | 普通进程池与 CF32 共用排程，三个 CF32 全部退出及采集屏障允许扩大普通物理池。两个实际 H9 采集批次使用不同微调种子，各 24 案、相同任务组合。见 [两个批次](ordinary_capacity.json) 和 [锁及归还记录](ordinary_tail_trial.json)。 |

以上性能测量额外消费 {extra:,} 个真实仿真子步。所有微基准合计进行 0 次训练优化器更新。登记内的生产吞吐测量使用既有种子、原锚点与原预算。整块 GPU 的利用率包含同机作业。对照耗时来自重叠的不同代码段，各加速比无法直接相乘。随训练长度变化，最终时间由四轮工作块和物理判据决定。

[完成时间估算](forecast.json) · [每种子八进程的登记]({current_test.name}/registration.json)"""
reconstruction=read(p/'r08_recovery.json')
if reconstruction:
 md+="\n\n第八轮种子 1702 从已保存的第 1 步完整包和第 2 步原始重放恢复。灾后重新计算的物理积分和优化器代价单列。参见 [相同动作、状态与 Adam 比对](r08_recovery.json)。"
if tail.get('valid'):
 md+=f"\n\n第八轮只余 1702 时，6 和 12 个物理进程的各 90 秒实付吞吐为 {tail['baseline_updates_min']:.1f} 与 {tail['challenger_updates_min']:.1f} 次/分。已采用 {tail['winner']} 进程完成该种子余量，完成后归还三种子配额。见 [对照判定](r08-tail/decision.json)、[六进程计时](r08-tail/baseline.json) 和 [十二进程计时](r08-tail/challenger.json)。"
elif tail:
 md+=f"\n\n第八轮 1702 空闲配额对照保留原配置，登记与限制见 [运行判定](r08-tail/decision.json)。"
if decision:md+=f" · [第 {decision['round']} 轮八进程判定]({current_test.name}/decision.json)"
write_md(p/'README.md',md.replace("空闲进程配额用于普通采集","空闲进程配额用于普通采集")+eta)
print('evidence',now(),extra,len(loaded),rate)
