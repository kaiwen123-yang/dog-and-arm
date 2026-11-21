#!/usr/bin/env python3
"""Extract measured joint minima and accepted parking windows for a P6 manifest."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def measurements(manifest_dir, raw_dir, record):
    path = Path(record['run'])
    summary = json.loads((manifest_dir / path / 'summary.json').read_text())
    raw = raw_dir / path
    steps = np.loadtxt(raw / 'joint_margins_500hz.csv', delimiter=',', skiprows=1,
                       usecols=(0, 2, 3, 4, 5, 6, 7))
    times, margins = steps[:, 0], steps[:, 1:]
    logged = [summary['arm_joint_limit_min'][f'piper_joint{i}'] for i in range(1, 7)]
    extrema = np.argmin(margins, axis=0)
    row = dict(stage=record['stage'], case=record['case'], samples_500hz=len(times)-1,
               steps_any_joint_outside=int((margins[1:] < 0.).any(axis=1).sum()),
               max_minimum_difference_rad=max(abs(margins[k, j]-logged[j]['min_margin_rad'])
                                              for j, k in enumerate(extrema)),
               max_minimum_time_difference_s=max(abs(times[k]-logged[j]['time_s'])
                                                 for j, k in enumerate(extrema)))
    with (raw / 'timeseries.csv').open() as stream:
        samples = list(csv.DictReader(stream))
    events = {e['phase']: e for e in summary['events']}
    for phase in ('post_release_hold', 'final'):
        event = events.get(phase)
        window = [] if event is None else [
            s for s in samples if s['phase'] == phase
            and float(s['time_s']) >= event['time_s'] - event['continuous_s'] - 1e-8
        ]
        row[phase+'_observations_25hz'] = len(window)
        row[phase+'_max_speed_mm_s'] = max((1000*np.hypot(float(s['world_v_x']),float(s['world_v_y']))
                                           for s in window), default=None)
        row[phase+'_max_abs_yaw_deg_s'] = max((abs(np.rad2deg(float(s['world_omega_z'])))
                                              for s in window), default=None)
        row[phase+'_max_door_contact_N'] = max((float(s['door_norm_sum_N']) for s in window), default=None)
    opening = [s for s in samples if s['phase'] == 'open']
    for finger in (1, 2):
        row[f'open_min_finger{finger}_normal_N_25hz'] = min(
            (float(s[f'finger_N_{finger}']) for s in opening), default=None)
    friction = json.loads((manifest_dir / path / 'contact_friction.json').read_text())
    row['contact_categories_25hz'] = ','.join(friction)
    for prefix in ('finger', 'wheel_ground'):
        row[prefix+'_friction_observed'] = ','.join(str(mu) for mu in sorted(
            {mu for pair, values in friction.items() if pair.startswith(prefix) for mu in values}))
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('raw_dir', type=Path, help='raw results tree with the same run subdirectories')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.manifest.open() as source, args.output.open('w') as dest:
        writer = None
        for record in csv.DictReader(source):
            row = measurements(args.manifest.parent, args.raw_dir, record)
            if writer is None:
                writer = csv.DictWriter(dest, row.keys(), lineterminator='\n')
                writer.writeheader()
            writer.writerow(row)


if __name__ == '__main__':
    main()
