from contextlib import contextmanager
from pathlib import Path
from statistics import mean
import fcntl, json, time
from scripts.multimodal.mm03_launch import alive, now, read, write
from scripts.multimodal.mm03_b_parallel import native_slot_path
from scripts.multimodal.mm03_elastic import busy
from scripts.multimodal.mm03_elastic_trial import active, process_cpu, telemetry

out=Path(__file__).resolve().parent
root=out.parents[1]
number=45
directory=root/f'B/rounds/r{number:02d}'
seeds=(1701,1702,1703)
duration=90
def totals():
    answer={}
    for seed in seeds:
        path=directory/f'H9-WM/seed{seed}/paired/applied.jsonl'
        rows=[json.loads(line) for line in path.open() if line.endswith('\n')] if path.exists() else []
        if any(i!=row['update'] for i,row in enumerate(rows,1)):
            raise RuntimeError('Non-contiguous optimization ledger '+str(path))
        answer[str(seed)]=[len(rows),sum(r['native_substeps'] for r in rows)]
    return answer

def stage_ready():
    count=0
    for seed in seeds:
        path=directory/f'H9-WM/seed{seed}/paired/native_stage_owner.lock'
        if not path.exists():continue
        with path.open('a') as f:
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:count+=1
    return count==3

def ensure_open():
    if (root/'B/candidate_freeze.json').exists() or (directory/'block.json').exists():
        raise RuntimeError('Round closed before the measurement')
    if any(x[0]>=428 for x in totals().values()):
        raise RuntimeError('Near the end of the registered work; release any measurement reservation')
    if not alive(read(root/'status/B.json')):
        raise RuntimeError('B supervisor is recovering; release all measurement reservations')

def sample(n):
    stable_since=None
    last=None
    while True:
        ensure_open()
        sizes=sorted(active(root,number).values())
        t=time.monotonic()
        if len(sizes)==n and len(set(sizes))==1 and not busy(root) and stage_ready():
            if sizes!=last or stable_since is None:stable_since=t
            if t-stable_since>=12:break
        else:stable_since=None
        last=sizes
        time.sleep(1)
    before=totals()
    peers=process_cpu()
    t0=time.monotonic()
    wall=time.time()
    points=[]
    while True:
        x=telemetry()
        x['widths']=sorted(active(root,number).values())
        points.append(x)
        if len(x['widths'])!=n or busy(root):
            raise RuntimeError('Seed population or ordinary work changed during the timed window')
        if min(x['widths'])<6 or max(x['widths'])>8 or x['oom']!=points[0]['oom'] or x['oom_kill']!=points[0]['oom_kill'] or x['host_free_GiB']<8 or x['gpu_free_GiB']<12:
            raise RuntimeError('Resource admission condition changed')
        remaining=duration-(time.monotonic()-t0)
        if remaining<=0:break
        time.sleep(min(2,remaining))
    after=totals()
    elapsed=time.monotonic()-t0
    other=process_cpu()
    counts={s:v[0]-before[s][0] for s,v in after.items()}
    assert sum(k>0 for k in counts.values())==n
    native=sum(v[1]-before[s][1] for s,v in after.items())
    result=dict(at=now(),round=number,active_seeds=n,seconds=elapsed,start_epoch=wall,before=before,after=after,
          paid_by_seed=counts,updates_min=sum(counts.values())*60/elapsed,native_substeps=native,substeps_s=native/elapsed,
          gpu_mean=mean(x['gpu_util'] for x in points),cpu_cores=(points[-1]['cpu_usec']-points[0]['cpu_usec'])/1e6/(points[-1]['t']-points[0]['t']),
          min_host_free_GiB=min(x['host_free_GiB'] for x in points),min_gpu_free_GiB=min(x['gpu_free_GiB'] for x in points),
          observed_native_widths=sorted(set(tuple(x['widths']) for x in points)),oom_delta=points[-1]['oom']-points[0]['oom'],
          oom_kill_delta=points[-1]['oom_kill']-points[0]['oom_kill'],other_cpu_seconds={k:v['seconds']-peers[k]['seconds'] for k,v in other.items() if k in peers and v['seconds']-peers[k]['seconds']>2},
          extra_updates=0,extra_physics_substeps=0)
    write(out/f'r45_window_{n}.json',result)
    print(now(),n,result['updates_min'],result['substeps_s'],flush=True)
    return result

def run():
    capfile=directory/'phase_capacity.json'
    while not capfile.exists():
        if (root/'B/candidate_freeze.json').exists():raise RuntimeError('Candidates already frozen')
        time.sleep(3)
    cap=read(capfile)
    write(out/'r45_allocation.json',cap)
    if cap.get('slots')!=3 or not cap.get('compact_state_rows'):raise RuntimeError('Cohort did not admit three compact fits')
    cfg=root/'resources/phase_capacity_policy.json'
    original=read(cfg)
    slots_dir=root/'B/locks'
    warm=out/'r45_window_2.json'
    if not warm.exists():
        with native_slot_path(slots_dir,2).open('a') as reservation:
            fcntl.flock(reservation,fcntl.LOCK_EX|fcntl.LOCK_NB)
            two=sample(2)
    else:two=read(warm)
    three=sample(3)
    chosen=3 if three['updates_min']>two['updates_min'] and three['substeps_s']>two['substeps_s'] else 2
    with (root/'resources/allocation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if read(cfg)!=original:raise RuntimeError('Another operator changed the active phase policy')
        if chosen!=original['max_slots']:
            write(cfg,dict(original,max_slots=chosen,changed_beijing=now(),last_throughput_decision=str(out/'r45_decision.json')))
    write(out/'r45_decision.json',dict(at=now(),valid=True,round=number,winner=chosen,two_updates_min=two['updates_min'],three_updates_min=three['updates_min'],two_native_steps_s=two['substeps_s'],three_native_steps_s=three['substeps_s'],ratio=three['updates_min']/two['updates_min'],extra_training_updates=0,extra_physics_substeps=0))
if __name__=='__main__':
    with (out/'production_control.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not (out/'r45_decision.json').exists():
            try:run()
            except Exception as exc:
                write(out/'r45_measurement_issue.json',dict(at=now(),detail=str(exc),training_continues=True))
                raise
