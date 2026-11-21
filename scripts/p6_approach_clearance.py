#!/usr/bin/env python3
"""Measure frame clearance on logged P6 back-approach poses (25 Hz, no integration)."""
import argparse
import csv
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from p6_contacts import ContactMeter
from p6_scene import build


def measure(model, meter, directory):
    cfg = json.loads((directory / 'config.json').read_text())
    data = mj.MjData(model)
    joints = [model.joint(i).name for i in model.actuator_trnid[:, 0]]
    addresses = model.jnt_qposadr[model.actuator_trnid[:, 0]]
    frame = [i for i in meter.door_collision if model.geom_bodyid[i] == 0]
    best = np.inf
    samples = 0
    info = {'case': cfg['case']}
    with (directory / 'timeseries.csv').open() as f:
        for row in csv.DictReader(f):
            if row['phase'] not in ('approach_base', 'settle'):
                break
            data.qpos[:3] = [float(row['root_' + k]) for k in 'xyz']
            data.qpos[3:7] = [float(row['root_quat_' + k]) for k in 'wxyz']
            data.qpos[addresses] = [float(row['q_' + name]) for name in joints]
            finger1 = data.joint('piper_gripper_joint1').qpos[0]
            data.joint('piper_gripper_joint2').qpos[0] = finger1 - float(row['actual_width_m'])
            data.joint('door_single_hinge').qpos[0] = np.deg2rad(float(row['door_deg']))
            mj.mj_kinematics(model, data)
            distance, robot_geom, frame_geom = min(
                (mj.mj_geomDistance(model, data, i, j, 4.0, None), i, j)
                for i in meter.robot_collision for j in frame
            )
            if samples == 0:
                info['start_clearance_mm'] = 1000 * distance
            samples += 1
            if distance < best:
                best = distance
                info.update(min_clearance_mm=1000 * distance, time_s=row['time_s'],
                            phase=row['phase'], robot_geom=meter.names[robot_geom],
                            frame_geom=meter.names[frame_geom])
    return dict(**info, samples_25hz=samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', type=Path, nargs='+', help='raw back-side runs sharing the same geometry')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cfg = json.loads((args.runs[0] / 'config.json').read_text())
    model = build(cfg)
    meter = ContactMeter(model, 'preview_floor', 'back')
    rows = sorted((measure(model, meter, d) for d in args.runs), key=lambda r: r['case'])
    with args.output.open('w') as f:
        writer = csv.DictWriter(f, rows[0].keys(), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
