"""Index the actual contact training cost and recovery files, counting each process once."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def interval_union(intervals):
    elapsed = 0.
    end = 0.
    for start, stop in sorted(intervals):
        elapsed += max(0., stop-max(start,end))
        end = max(end,stop)
    return elapsed


def index(names):
    root = Path('results/b0')
    processes = {}
    endpoints = {}
    intervals = []
    for name in names:
        run = root/name
        actual = read(run/'actual_config.json')
        outcome = read(run/'outcome.json')
        cfg = actual['cfg']
        log = rows(run/'updates.jsonl')
        counts = [r['update'] for r in log]
        last = outcome['actor_updates']
        if counts != list(range(counts[0],last+1)) or name != actual['run'] or name in processes:
            raise ValueError(f'Invalid run or update series at {run}')
        parent = actual['initialization']['resume']
        prefix = endpoints[Path(parent).parent.name] if parent else dict(actor_updates=0,valid=0,attempted=0)
        valid = sum(r['valid_transitions'] for r in log)
        attempted = sum(r['simulated_lane_intervals'] for r in log)
        if (prefix['actor_updates'] + len(log), prefix['valid'] + valid, prefix['attempted'] + attempted) != (
                last, outcome['valid_online_transitions'], outcome['simulated_lane_intervals']):
            raise ValueError(f'Continuation mismatch at {run}')
        collections = rows(run/'cohorts.jsonl') if (run/'cohorts.jsonl').is_file() else log
        effort = dict(actor_h32=len(log), wm_minibatches=len(log)*cfg['wm_batches'],
                      critic_minibatches=len(log)*20, valid=valid, attempted=attempted,
                      reset_prefix_lane_substeps=sum(r['prefix_steps_per_lane']*sum(r['starts_per_motion'])
                                                   for r in collections),
                      cohorts=len(collections))
        for field in ('wm_online_stored_positions','wm_offline_stored_positions','wm_online_successor_targets',
                      'wm_offline_successor_targets','imagined_policy_steps'):
            effort[field] = sum(r[field] for r in log)
        endpoint = dict(actor_updates=last,valid=prefix['valid']+valid,attempted=prefix['attempted']+attempted)
        checkpoint = run/f'checkpoint_{last:06d}.pt'
        with checkpoint.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        processes[name] = dict(seed=actual['seed'],actor=actual['actor_class'],reward_units=cfg['action_rate_coordinates'],
                               source_revision=actual['git_revision'],initialization=actual['initialization'],
                               updates=[counts[0],last],new_cost=effort,cumulative=endpoint,
                               process_seconds=outcome['elapsed_process_s'],device=actual['device'],
                               checkpoint=str(checkpoint),checkpoint_sha256=sha,
                               recovery=str(run/'cohort_state.pt'),recovery_bytes=(run/'cohort_state.pt').stat().st_size)
        endpoints[name] = endpoint
        intervals.append((outcome['started_unix'],outcome['finished_unix']))
    totals = {k:sum(p['new_cost'][k] for p in processes.values()) for k in effort}
    return dict(worktree=str(Path.cwd()),processes=processes,distinct_process_totals=totals,
                training_process_hours=sum(p['process_seconds'] for p in processes.values())/3600.,
                union_training_wall_hours=interval_union(intervals)/3600.,attributable_gpu_hours=None,
                timing_scope='Contact training processes including initialization/checkpoint I/O, overlapping on one shared GPU. Inherited free-policy and door-WM training time excluded.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs',nargs='+',help='Order parents before their continuations')
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    report = index(args.runs)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    temp=args.output.with_suffix('.tmp')
    temp.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    temp.replace(args.output)
