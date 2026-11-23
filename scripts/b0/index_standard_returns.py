"""Combine the two registered contact protocols for complete, named standard checkpoints."""
import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def stats(rows):
    values = [r['normalized_fixed_effort'] for r in rows]
    complete = bool(rows) and all(v is not None for v in values)
    return dict(cases=len(rows), physical_passes=sum(r['passed'] for r in rows),
                finite_segment_returns=sum(v is not None for v in values),
                mean=statistics.mean(values) if complete else None,
                median=statistics.median(values) if complete else None,
                worst=min(values) if complete else None,
                total_scored_substeps=sum(r['measured_substeps'] for r in rows),
                first_2ms_failures=sum(not r['passed'] and r['measured_substeps']==1 for r in rows),
                failures=dict(Counter(r['failure'] for r in rows if r['failure'])))


def contact_training_budget(directory, update):
    """Sum observed rows across a resumed contact chain once, up to this checkpoint."""
    if update == 0:
        return [],0.
    cfg = read(directory/'actual_config.json')
    rows = []
    with (directory/'updates.jsonl').open() as file:
        for line in file:
            row = json.loads(line)
            if row['update'] > update:
                break
            rows.append(row)
            if row['update'] == update:
                break
    previous = cfg['initialization']['resume']
    history = []
    process_seconds = 0.
    if previous:
        first = rows[0]['update'] if rows else update+1
        history, process_seconds = contact_training_budget(Path(previous).parent,first-1)
    if rows:
        process_seconds += rows[-1]['process_elapsed_s']
    return history+rows, process_seconds


def main(args):
    base = Path('results/b0')
    formal = read(Path('config/b0/contact_dev_v1.json'))['cases']
    margin = read(Path('config/b0/contact_dev_hold_margin_v2.json'))['cases']
    by_checkpoint = defaultdict(list)
    for train in args.training_runs:
        if Path(train).name != train:
            raise ValueError('Supply a training run name')
        for p in sorted(base.glob(f'{train}_u*_*/returns.json')):
            if not p.with_name('evaluation.json').is_file():
                continue
            measured = read(p)
            evaluation = read(p.with_name('evaluation.json'))
            checkpoint = Path(measured['checkpoint'])
            if checkpoint.parent != base/train or evaluation['checkpoint'] != str(checkpoint):
                raise ValueError(f'Mismatched checkpoint at {p}')
            protocol = Path(measured['manifest']).stem
            for r in measured['rows']:
                key = r['group']
                expected = 'contact_dev_hold_margin_v2' if key in margin else 'contact_dev_v1'
                if key not in formal or protocol != expected or r['case'] != 'nominal':
                    raise ValueError(f'Nonformal case at {p} {key}')
                detail = p.parent/key/r['case']/'return.json'
                physical = read(detail)
                verdict = read(detail.with_name('result.json'))
                completed = [event['phase'] for event in verdict['events']]
                row = dict(training_run=train, checkpoint=str(checkpoint), backend=evaluation['backend'],
                           protocol=protocol, **r, physical_wall_seconds=physical['physical_wall_seconds'],
                           completed_phases=','.join(completed),
                           failure_phase=(physical['first_failure'] or {}).get('phase'),
                           error_tcp_rmse_m=(physical['tracking_errors'] or {}).get('tcp_position_rmse_m'),
                           error_door_angle_rmse_deg=(physical['tracking_errors'] or {}).get('door_angle_rmse_deg'),
                           score_path=str(detail))
                by_checkpoint[(str(checkpoint), evaluation['backend'])].append(row)
    records, all_rows = [], []
    for (ck,backend), rows in sorted(by_checkpoint.items()):
        keys = [r['group'] for r in rows]
        if len(keys) != len(set(keys)):
            raise ValueError(f'Duplicate scored case in {ck}:{backend}')
        if set(keys) != set(formal):
            continue
        rows.sort(key=lambda r:r['group'])
        checkpoint=Path(ck)
        update=int(checkpoint.stem.split('_')[-1])
        history, seconds = contact_training_budget(checkpoint.parent,update)
        if [r['update'] for r in history] != list(range(1,update+1)):
            raise ValueError(f'Incomplete training budget lineage at {ck}')
        budget=dict(contact_h32_updates=update,
                    contact_valid_transitions=history[-1]['cumulative_valid_transitions'] if history else 0,
                    contact_attempted_lane_intervals=sum(r['simulated_lane_intervals'] for r in history),
                    contact_imagined_policy_steps=sum(r['imagined_policy_steps'] for r in history),
                    measured_contact_process_seconds_through_update=seconds if history else None,
                    attributable_gpu_hours=None)
        records.append(dict(checkpoint=ck, backend=backend, contact_training_budget=budget,
                            segments_only=stats(rows), full_from_start_return=None,
                            by_side={side:stats([r for r in rows if r['group'].startswith(side+'/')])
                                     for side in ('pull','push')}))
        all_rows.extend(rows)
    if not all_rows:
        raise ValueError('No complete ten-case physical checkpoint found')
    args.output.mkdir(parents=True,exist_ok=True)
    target = args.output/'nominal_segments.csv'
    temporary = target.with_suffix('.csv.tmp')
    with temporary.open('w',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    temporary.replace(target)
    details = args.output/'nominal_score_details.jsonl'
    temporary = details.with_suffix('.jsonl.tmp')
    with temporary.open('w') as f:
        for row in all_rows:
            path = Path(row['score_path'])
            score = read(path)
            verdict = read(path.with_name('result.json'))
            score.update(checkpoint=row['checkpoint'], reference_protocol=row['protocol'],
                         completed_physical_events=verdict['events'],
                         phase_longest_ready_substeps=verdict['longest_ready_steps'])
            f.write(json.dumps(score,allow_nan=False)+'\n')
    temporary.replace(details)
    summary = args.output/'nominal_summary.json'
    temporary = summary.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(dict(primary_coordinates='fixed_effort',
                         statistic='equal weight per registered segment; five per side',
                         scope='segment_from_registered_start', records=records),indent=2,allow_nan=False)+'\n')
    temporary.replace(summary)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('training_runs',nargs='+')
    p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
