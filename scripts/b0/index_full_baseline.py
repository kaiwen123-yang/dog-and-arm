"""Summarize completed full-task runs by checkpoint, reference, side, and physics backend."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from scripts.b0.index_contact_evaluations import records


def save_csv(path, data):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(data)


def summarize(run, cases):
    nom, = [c for c in cases if c['case'] == 'nominal']
    trial = json.loads(Path(nom['result']).read_text())
    spec = json.loads((run/'evaluation.json').read_text())
    reg = {c['case']: c for c in cases if c['case'] != 'nominal'}
    if spec['requested_dev'] and trial['passed']:
        if set(reg) != {f'C{k:02d}' for k in range(1,21)}:
            raise ValueError(f'Incomplete development manifest at {run}/{nom["side"]}')
    elif reg:
        raise ValueError(f'Unexpected development cases in {run}/{nom["side"]}')
    for c in cases:
        detail = json.loads(Path(c['result']).read_text())
        if detail['start_substep'] or detail['prefix_physics_steps'] or detail['segment'] != 'full':
            raise ValueError(c['result'])
        if detail['passed']:
            events = detail['events']
            if [e['phase'] for e in events] != detail['phases']:
                raise ValueError(f'Incomplete physical sequence in {c["result"]}')
            holds = [e['ticks'] for e in events if e['phase'] in ('post_release_hold','final')]
            if holds != [1500,1500] or detail['first_failure'] is not None:
                raise ValueError(f'Incomplete parking in {c["result"]}')
    failures = Counter(c['failure'] for c in reg.values() if c['passed'] == 'False')
    good = sum(c['passed'] == 'True' for c in reg.values())
    return dict(run=run.name, checkpoint=spec['checkpoint'], reference_root=spec['source'],
                backend=spec['backend'], mujoco=spec['mujoco'], side=nom['side'],
                nominal_pass=trial['passed'], nominal_final_deg=trial['final_door_deg'],
                nominal_steps=trial['physics_steps'], nominal_last_phase=trial['last_physical_observation']['phase'],
                nominal_failure=nom['failure'], dev_pass=good, dev_evaluated=len(reg), dev_registered=20,
                dev_status=('passed' if good >= 18 else 'below_threshold') if reg else
                    ('nominal_failed' if not trial['passed'] else 'nominal_only'),
                dev_failure_counts=json.dumps(failures, sort_keys=True))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if len(set(args.runs)) != len(args.runs):
        p.error('Repeated run directory')
    all_cases, scores = [], []
    for run in args.runs:
        rows = list(records(run))
        for side in sorted({c['side'] for c in rows}):
            scores.append(summarize(run, [c for c in rows if c['side']==side]))
        all_cases.extend(rows)
    args.output.mkdir(exist_ok=True, parents=True)
    save_csv(args.output/'full_case_index.csv', all_cases)
    save_csv(args.output/'full_scores.csv', scores)


if __name__ == '__main__':
    main()
