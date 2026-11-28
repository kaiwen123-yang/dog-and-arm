"""Compare the three already registered R49 WM refreshes without issuing training steps."""
from datetime import datetime
from pathlib import Path
from statistics import mean
import fcntl
import hashlib
import json
import subprocess
import time
from scripts.multimodal.mm03_b_parallel import GIB, GPU_HEADROOM, HOST_HEADROOM, host_memory
from scripts.multimodal.mm03_elastic_trial import process_cpu, telemetry
from scripts.multimodal.mm03_launch import now, read, write
out=Path(__file__).resolve().parent
root=out.parents[1]
round_dir=root/'B/rounds/r49'
seeds=(1701,1702,1703)
marker=root/'resources/paired_wm_loaders.json'
registration=out/'registration.json'
policy=dict(enabled=True,from_round=49,through_round=49,trial=str(registration))

def set_policy(previous,new):
    with (root/'resources/allocation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if read(marker)!=previous:raise RuntimeError('The WM policy has changed externally')
        write(marker,new)

def read_records(folder):
    file=folder/'executions.jsonl'
    if not file.is_file():return []
    with file.open() as f:return [json.loads(line) for line in f if line.endswith('\n')]

def stages():
    current={}
    for seed in seeds:
        folder=round_dir/f'wm/seed{seed}'
        rec=read_records(folder)
        starts=[x for x in rec if x['event']=='started']
        ends=[x for x in rec if x['event']=='ended' and x.get('completed')]
        if starts:
            current[str(seed)]=dict(start=starts[0]['time'],attempts=len(starts),admission=read(folder/'wm_storage_admission.json'))
            if ends:
                receipt=read(folder/'receipt.json')
                if receipt:
                    last=ends[-1];current[str(seed)].update(end=last['time'],retained=receipt['retained'],
                        paid=receipt['paid'],rollback=receipt['rollback'],h7_before=receipt['validation_h7_before'],
                        h7_after=receipt['validation_h7_after'],cuda_peak_reserved_MiB=last['cuda_peak_reserved_MiB'],
                        peak_rss_GiB=last['rss_peak_kib']/2**20,members=receipt['members_file'])
    return current

def summary(samples,start,end):
    xs=[p for p in samples if start<=p['t']<=end]
    if len(xs)<2:return {}
    coverage=xs[-1]['t']-xs[0]['t']
    return dict(samples=len(xs),sampled_seconds=coverage,gpu_mean_pct=mean(x['gpu_util'] for x in xs),
                min_gpu_free_GiB=min(x['gpu_free_GiB'] for x in xs),
                min_host_free_GiB=min(x['host_free_GiB'] for x in xs),
                cpu_cores=(xs[-1]['cpu_usec']-xs[0]['cpu_usec'])/(1e6*coverage),
                oom_delta=xs[-1]['oom']-xs[0]['oom'],oom_kill_delta=xs[-1]['oom_kill']-xs[0]['oom_kill'])

def run():
    if (out/'decision.json').is_file():return
    expected='/root/autodl-tmp/mm03-20261126'
    assert str(root)==expected and 'measured_wm_lanes' in Path('scripts/multimodal/mm03_b_parallel.py').read_text()
    samples=[]; peers={}; baseline=None
    first_lock=root/'B/locks/wm_phase_1.lock'
    # A lost controller releases only this empty extra lane; registered WM trainers continue.
    with first_lock.open('a') as extra:
        fcntl.flock(extra,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (round_dir/'phase_capacity.json').is_file():raise RuntimeError('R49 already started before registration')
        if marker.exists():raise RuntimeError('Active WM policy already exists')
        checks=read(out/'admission_checks.json')
        assert len(checks['records'])==3 and all(x['allowed_lanes_candidate']==2 for x in checks['records'])
        write(registration,dict(at=now(),round=49,seeds=seeds,one_then_two=True,
            planned_updates_per_seed=1000,control='Hold only the added lane until the first registered WM receipt. Release the second lane for the remaining two.',
            effective_throughput='Paid 1000 or 2000 updates divided by physical table construction and training elapsed time.',
            select='At least 5% more paid updates per minute, at least half of the shorter job overlapping, identical members, 3 unbroken 1000/1000 receipts, no new OOM and min 12 GiB GPU and 8 GiB host available.',
            extrapolation='30% above the three preceding measured GPU peaks scaled to this membership, plus 3 GiB per CUDA process; recomputed per round capped at two. Revert to the preceding estimate on a >15% single-round row jump.',
            extras=dict(optimizer_updates=0,native_substeps=0),code=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
        set_policy({},policy)
        while not (round_dir/'phase_capacity.json').is_file():
            if (root/'B/completion.json').is_file():raise RuntimeError('Registered training closed before R49')
            time.sleep(3)
        peers=process_cpu();cap=read(round_dir/'phase_capacity.json')
        while True:
            current=stages();samples.append(telemetry())
            done=[s for s,v in current.items() if 'end' in v]
            if done:
                assert len(done)==1
                baseline=done[0];break
            time.sleep(2)
        released=now()
    print(released,'second lane available',baseline,flush=True)
    while True:
        current=stages();samples.append(telemetry())
        if len(current)==3 and all('end' in s for s in current.values()):break
        time.sleep(2)
    single=current[baseline];others={s:st for s,st in current.items() if s!=baseline}
    pair_start=min(s['start'] for s in others.values());pair_end=max(s['end'] for s in others.values())
    overlap=min(s['end'] for s in others.values())-max(s['start'] for s in others.values())
    single_s=single['end']-single['start'];pair_s=pair_end-pair_start
    single_perf=summary(samples,single['start'],single['end'])
    pair_perf=summary(samples,pair_start,pair_end)
    pair_ratio=(2000/pair_s)/(1000/single_s)
    last_peers=process_cpu()
    other_cpu={}
    for pid,row in last_peers.items():
        if pid in peers:
            label=row['project'];other_cpu[label]=other_cpu.get(label,0.)+row['seconds']-peers[pid]['seconds']
    checks=dict(paid=all(x['retained']==x['paid']==1000 and not x['rollback'] and x['attempts']==1 for x in current.values()),
           same_members=len({x['members'] for x in current.values()})==1,
           baseline_exclusive=pair_start>=single['end']-.5,
           pair_overlap=overlap>=.5*min(s['end']-s['start'] for s in others.values()),
           pair_admitted=all(x['admission'].get('wm_slots')==2 for x in others.values()),
           gpu_sample_coverage=all(v and v['sampled_seconds']>=.9*t for v,t in ((single_perf,single_s),(pair_perf,pair_s))),
           gpu_headroom=bool(pair_perf) and pair_perf['min_gpu_free_GiB']>=GPU_HEADROOM/GIB,
           host_headroom=bool(pair_perf) and pair_perf['min_host_free_GiB']>=HOST_HEADROOM/GIB,
           oom=samples[-1]['oom']==samples[0]['oom'] and samples[-1]['oom_kill']==samples[0]['oom_kill'])
    valid=all(checks.values());winner=2 if valid and pair_ratio>=1.05 else 1
    comparison=dict(at=now(),valid=valid,checks=checks,round=49,selected_lanes=winner,
        single_seed=baseline,pair_seeds=list(others),single_seconds=single_s,pair_seconds=pair_s,overlap_seconds=overlap,
        single_updates_min=60000/single_s,pair_updates_min=120000/pair_s,ratio=pair_ratio,
        single_telemetry=single_perf,pair_telemetry=pair_perf,stages=current,other_project_cpu_seconds=other_cpu,
        cohort_slots=cap['slots'],extra_optimizer_updates=0,extra_native_substeps=0,
        scope='Same frozen physical membership and 1000 H7 updates per seed, different model seeds. The pair also overlaps the earlier seed’s downstream training and simultaneous production disk transfers.')
    next_policy=dict(enabled=winner==2,from_round=50,selected=winner,decision=str(out/'decision.json'))
    set_policy(policy,next_policy)
    write(out/'decision.json',comparison)
    print(now(),'ratio',pair_ratio,'choose',winner,checks,flush=True)

if __name__=='__main__':
    with (out/'controller.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:run()
        except Exception as exc:
            write(out/'issue.json',dict(at=now(),error=str(exc),extra_budget=0))
            if read(marker)==policy:
                set_policy(policy,dict(enabled=False,from_round=50,reason='Unfinished R49 comparison'))
            raise
