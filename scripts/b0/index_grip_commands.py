"""Recover stable-grip command changes from already scored physical cases (native environment)."""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from learning.b0.physics import ActionMap, FINGERS, make_model


def measure(index):
    models = {side:make_model(task,1) for side,task in [('pull','mobile'),('push','push')]}
    with index.open() as source:
        for entry in csv.DictReader(source):
            side, segment = entry['group'].split('/')
            if segment != 'stable_grip':
                continue
            path = Path(entry['score_path']).with_name('result.json')
            case = json.loads(path.read_text())
            plan = json.loads((path.parents[3]/'run_spec.json').read_text())['plan']
            raw = Path(case['raw_directory'])
            reference = Path(plan['source'])/case['episode']
            model = models[side]
            mapping = ActionMap(model)
            def physical(action):
                return mapping.offset+mapping.scale*action
            current = physical(np.load(raw/'clipped_action.npy', mmap_mode='r')[0])
            previous = physical(np.asarray(case['score_initial_previous_action']))
            target = physical(np.load(reference/'action_clipped.npy', mmap_mode='r')[case['start_substep']//10])
            obs = np.load(raw/'qpos.npy', mmap_mode='r')
            f1, f2 = [model.joint(n).qposadr.item() for n in FINGERS]
            yield dict(run=entry['training_run'],update=int(Path(entry['checkpoint']).stem.split('_')[-1]),
                       side=side,checkpoint=entry['checkpoint'],case_result=str(path),scored_substeps=case['physics_steps'],
                       failure=(case['first_failure'] or {}).get('reason'),force_peak_n=case['measured_peak_net_force_n'],
                       first_command_j2_rad=current[17],previous_command_j2_rad=previous[17],ref_command_j2_rad=target[17],
                       first_command_opening_mm=1000*current[22],previous_command_opening_mm=1000*previous[22],
                       ref_command_opening_mm=1000*target[22],measured_start_opening_mm=1000*(obs[0,f1]-obs[0,f2]),
                       measured_stop_opening_mm=1000*(obs[-1,f1]-obs[-1,f2]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nominal_segments',type=Path)
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    rows = list(measure(args.nominal_segments))
    if not rows:
        parser.error('No measured stable-grip cases')
    temp = args.output.with_suffix('.tmp')
    with temp.open('w',newline='') as stream:
        writer = csv.DictWriter(stream, rows[0])
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(args.output)
