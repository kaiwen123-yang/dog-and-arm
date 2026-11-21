#!/usr/bin/env python3
"""Freeze the unseen door-condition list and check initial geometry, with no simulation stepping."""
# ruff: noqa: E402 -- direct script entry uses the project source tree.
import argparse
import json
from pathlib import Path
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.b0.evaluate import PROTOCOL, case_initial_qpos
from learning.b0.physics import make_model
from learning.b0.reference import load_episode
from p6_contacts import ContactMeter
from p6_scene import CASES, settings


def initial_contacts(model, data, meter):
    pairs = []
    floor = model.geom('preview_floor').id
    max_floor = 0.
    for c in data.contact:
        if c.dist >= -1.e-6:
            continue
        pair = [int(c.geom1), int(c.geom2)]
        other = pair[1] if pair[0] == floor else pair[0]
        if floor in pair and model.geom_bodyid[other] in meter.wheels:
            max_floor = max(max_floor, -float(c.dist))
        else:
            pairs.append([meter.names[pair[0]], meter.names[pair[1]], float(c.dist)])
    return pairs, max_floor


def inspect(model, data, meter, q, v):
    data.qpos[:] = q
    data.qvel[:] = v
    mj.mj_forward(model, data)
    disallowed, floor = initial_contacts(model, data, meter)
    clearance, pair = meter.door_clearance(data)
    return dict(disallowed_penetrations=disallowed, wheel_floor_depth_m=floor,
                robot_door_clearance_m=float(clearance), closest_robot_door_geoms=pair)


def valid(row, allowed_floor):
    return (not row['disallowed_penetrations'] and row['wheel_floor_depth_m'] <= allowed_floor + 1.e-6
            and row['robot_door_clearance_m'] > 0.)


def register(reference_dir, manifest_path, geometry_path):
    if manifest_path.exists() or geometry_path.exists():
        raise FileExistsError('Use new output paths. A frozen manifest must not be overwritten.')
    rng = np.random.default_rng(2026112106)
    defaults = dict(dx=0., dy=0., yaw=0., door=0., wheel_mu=1., finger_mu=1.,
                    hinge_friction=1., hinge_damping=1.)
    low = [-.05, -.05, -5., 0., .8, .8, .5, .5]
    high = [.05, .05, 5., 5., 1.2, 1.2, 1.5, 1.5]
    development = [defaults | case for case in CASES.values()]
    manifest = dict(version='b0_door_held_out_v1', split='held_out_sealed_until_B0-06',
                    rng='numpy.random.default_rng(2026112106), pull then push, one uniform vector in field order per candidate, rounded to 8 decimals.',
                    fields=list(defaults), lower=low, upper=high, regression_ids=list(range(1, 21)),
                    geometry='Any non-wheel-ground penetration deeper than 1e-6 m, any non-positive robot-door clearance, or wheel-floor depth > nominal + 1e-6 m excludes the sample, before policy evaluation.',
                    application='Apply perturbation via p6_scene.settings and build exactly as for C01-C20. XY / yaw modify only initial pose. Friction and damping multipliers are static per episode.',
                    target_per_side=40, denominator_per_side=50, independent_seeds=[0, 1, 2],
                    cases={}, rejected={})
    audit = {'mujoco': mj.__version__, 'method': 'mj_forward at initial state only; no policy/teacher or integration',
             'free_motion': {}, 'held_out_door': {}}
    for name in PROTOCOL['references']:
        ep = load_episode(reference_dir / name)
        if name == PROTOCOL['references'][0]:
            model = make_model()
            data = mj.MjData(model)
            meter = ContactMeter(model, 'preview_floor')
        nominal = inspect(model, data, meter, ep['qpos'][0], ep['qvel'][0])
        rows = {}
        for case in PROTOCOL['cases']:
            q = case_initial_qpos(model, ep['qpos'][0], case)
            row = inspect(model, data, meter, q, ep['qvel'][0])
            row['valid'] = valid(row, nominal['wheel_floor_depth_m'])
            if not row['valid']:
                raise ValueError(f"Invalid preregistered initial geometry in {name} {case['id']}")
            rows[case['id']] = row
        audit['free_motion'][name] = rows
    for side, stage in [('pull', 'mobile'), ('push', 'push')]:
        cfg = settings(stage, 1)
        model = make_model(stage)
        data = mj.MjData(model)
        meter = ContactMeter(model, 'preview_floor', 'front' if side == 'pull' else 'back')
        mj.mj_resetDataKeyframe(model, data, model.key('home').id)
        q0, v0 = data.qpos.copy(), data.qvel.copy()
        yaw = cfg['base_yaw_rad']
        q0[:2] = np.asarray(cfg['base_xyz_m'][:2]) - cfg['travel_m'] * np.array([np.cos(yaw), np.sin(yaw)])
        q0[3:7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        nominal = inspect(model, data, meter, q0, v0)
        accepted, rejected, rows = [], [], {}
        while len(accepted) < 50:
            perturb = dict(zip(defaults, np.round(rng.uniform(low, high), 8).tolist()))
            if perturb in development or any(x['perturbation'] == perturb for x in accepted):
                rejected.append(dict(perturbation=perturb, reason='duplicate'))
                continue
            case = dict(dx_m=perturb['dx'], dy_m=perturb['dy'], dyaw_deg=perturb['yaw'])
            q = case_initial_qpos(model, q0, case)
            q[model.joint('door_single_hinge').qposadr] = np.deg2rad(perturb['door'])
            row = inspect(model, data, meter, q, v0)
            if not valid(row, nominal['wheel_floor_depth_m']):
                rejected.append(dict(perturbation=perturb, reason='initial_geometry', audit=row))
                continue
            ident = f'H{len(accepted) + 1:02}'
            accepted.append(dict(id=ident, perturbation=perturb))
            rows[ident] = row
        manifest['cases'][side] = accepted
        manifest['rejected'][side] = rejected
        audit['held_out_door'][side] = rows
    for path, value in ((manifest_path, manifest), (geometry_path, audit)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_dir', type=Path)
    parser.add_argument('manifest_path', type=Path)
    parser.add_argument('geometry_path', type=Path)
    args = parser.parse_args()
    register(args.reference_dir, args.manifest_path, args.geometry_path)
