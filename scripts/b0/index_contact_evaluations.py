"""Index complete learned-policy evaluations without pooling versions, directions, or restarts."""
import argparse
import csv
import json
from pathlib import Path


def records(run):
    spec = json.loads((run/'evaluation.json').read_text())
    with (run/'cases.csv').open() as stream:
        cases = list(csv.DictReader(stream))
    if len(cases) != spec['evaluated'] or sum(c['passed']=='True' for c in cases) != spec['passed']:
        raise ValueError(f'{run}: summary and cases disagree')
    seen = set()
    for case in cases:
        key = (case['side'],case['segment'],case['case'])
        folder = run.joinpath(*key)
        path = folder/'result.json'
        trial = json.loads(path.read_text())
        if key in seen or (case['passed']=='True') != trial['passed'] or int(case['physics_steps']) != trial['physics_steps']:
            raise ValueError(f'Inconsistent or duplicate trial {path}')
        seen.add(key)
        fail = trial['first_failure'] or {}
        video = folder/'episode.mp4'
        yield dict(run=run.name, checkpoint=spec['checkpoint'], protocol=Path(spec['manifest']).name,
                   reference_root=Path(spec['source']).name, reference=trial['episode'],
                   backend=spec['backend'], mujoco=spec['mujoco'], **case,
                   failure_phase=fail.get('phase',''), peak_ready_hold_steps=trial.get('longest_ready_steps',{}).get('hold',''),
                   result=path.as_posix(), video=video.as_posix() if video.is_file() else '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,nargs='+',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    if len(set(args.runs)) != len(args.runs):
        parser.error('Repeated run path')
    data = [row for run in args.runs for row in records(run)]
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(data[0]),lineterminator='\n')
        writer.writeheader()
        writer.writerows(data)


if __name__ == '__main__':
    main()
