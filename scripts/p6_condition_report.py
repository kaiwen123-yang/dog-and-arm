#!/usr/bin/env python3
"""Summarize an explicitly selected, single-control-version set of P6 trials."""
import argparse
import csv
import json
from pathlib import Path

from p6_scene import CASES


def read_row(directory, root):
    cfg = json.loads((directory / 'config.json').read_text())
    s = json.loads((directory / 'summary.json').read_text())
    stage, case = s['stage'], s['case']
    if (cfg['stage'], cfg['case'], cfg['perturbation']) != (stage, case, CASES[case]):
        raise ValueError(f'Condition mismatch in {directory}')
    if cfg.get('arrival_only') or stage not in ('mobile', 'push'):
        raise ValueError(f'Expected a full mobile door task in {directory}')
    if (s['assembly_revision'], s['arm_root_in_m1_m']) != (cfg['assembly_revision'], cfg['arm_root_in_m1_m']):
        raise ValueError(f'Inconsistent assembly identifiers in {directory}')
    events = {e['phase']: e for e in s['events']}
    phases = s['phases']
    open_start = events.get('grasp', {}).get('time_s')
    opening = None if open_start is None or 'open' not in phases else (
        events.get('open', {}).get('time_s', s['sim_time_s']) - open_start)
    axes = [s['arm_joint_limit_min'][f'piper_joint{i}'] for i in range(1, 7)]
    margins = [j['min_margin_deg'] for j in axes]
    holds = [events.get(phase, {}).get('continuous_s', 0.) for phase in ('post_release_hold', 'final')]
    complete = s['task_success']
    if complete and (list(events) != s['planned_phases'] or len(events) != 13):
        raise ValueError(f'Missing stage transitions in {directory}')
    reasons = []
    if not complete:
        reasons.append(s['failure'] or 'incomplete')
    if min(margins) < 0:
        reasons.append('joint_limit')
    if any(s['warnings']) or s['unexpected']:
        reasons.append('warning_or_contact')
    if complete and min(holds) + 1e-9 < cfg['post_hold_s']:
        reasons.append('parking_window')
    both_s = phases.get('open', {}).get('both_contact_s', 0.)
    row = dict(stage=stage, case=case, passed=not reasons, failure='|'.join(reasons), task_success=complete,
               run=str(directory.relative_to(root)), mount=s['assembly_revision'], steps=s['physics_steps'],
               final_deg=s['final_deg'], sim_s=s['sim_time_s'], open_s=opening,
               open_budget_left_s=None if opening is None else cfg['phase_timeout_s']['open'] - opening,
               open_both_s=both_s, open_both_fraction=None if not opening else both_s / opening,
               grip_confirm_s=events.get('grasp', {}).get('continuous_s'), post_release_park_s=holds[0],
               final_park_s=holds[1], max_grip_mm=s['max_grip_error_m']*1000,
               max_station_drift_mm=s['max_base_drift_m']*1000, max_door_force_N=s['max_door_force_N'],
               max_tilt_deg=s['max_tilt_deg'],
               min_wheel_N=min(min(p['min_wheel_N']) for p in phases.values()),
               min_open_wheel_N=min(phases['open']['min_wheel_N']) if 'open' in phases else None,
               max_grip_slip_m_s=max((phases[k]['max_slip_m_s'] for k in ('grasp','open','hold','release')
                                      if k in phases), default=None),
               max_contiguous_saturation_s=max(s['max_contiguous_saturation_s'].values()),
               limiting_joint=f'J{margins.index(min(margins))+1}', J5_time_s=axes[4]['time_s'],
               J5_phase=axes[4]['phase'], J5_nearest_limit=axes[4]['nearest_limit'])
    row.update({f'J{i}_margin_deg': margin for i, margin in enumerate(margins, 1)})
    for phase in ('retreat_arm', 'post_release_hold', 'stow', 'retreat_base', 'final'):
        gap = phases.get(phase, {}).get('min_robot_door_clearance_m_25hz')
        row[f'{phase}_min_gap_mm_25hz'] = None if gap is None else gap*1000
    controls = {k:v for k,v in cfg.items() if k not in ('case', 'perturbation', 'arrival_only')}
    return row, controls


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('runs', nargs='+', type=Path, help='individual case directories')
    args = parser.parse_args()
    baseline, rows = {}, {}
    for path in args.runs:
        row, controls = read_row(path.resolve(), args.output.resolve().parent)
        key = row['stage'], row['case']
        if key in rows or controls != baseline.setdefault(key[0], controls):
            raise ValueError(f'Duplicate or changed controls at {path}')
        rows[key] = row
    with args.output.open('w') as f:
        writer = csv.DictWriter(f, next(iter(rows.values())).keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows[k] for k in sorted(rows))


if __name__ == '__main__':
    main()
