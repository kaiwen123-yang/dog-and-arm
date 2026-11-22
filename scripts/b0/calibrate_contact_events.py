"""Calibrate B0 read-only events on archived native controls; no teacher invocation."""
import argparse
import csv
import json
from pathlib import Path
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from learning.b0.physics import build, settings


def compare(path, side, ref_path=None):
    cfg = json.loads((path / 'config.json').read_text())
    m = build(cfg)
    d = mj.MjData(m)
    reference = FrozenDoorReference.from_episode(ref_path or path, m)
    audit = ContactEvents(m, cfg, side, reference, hold_seconds=cfg.get('grip_hold_s', .5))
    raw = path / 'substeps'
    q, v, ctrl = [np.load(raw / (name+'.npy'), mmap_mode='r') for name in ('qpos','qvel','ctrl')]
    mj.mj_resetDataKeyframe(m, d, m.key('home').id)
    d.qpos[:] = q[0]
    d.qvel[:] = v[0]
    mj.mj_forward(m,d)
    peak_delta = 0.
    for k, command in enumerate(ctrl):
        q0, v0 = d.qpos.copy(), d.qvel.copy()
        d.ctrl[:] = command
        mj.mj_step(m,d)
        peak_delta = max(peak_delta, float(np.max(np.abs(d.qpos-q[k+1]))))
        audit.observe(d, None, q0, v0)
        if audit.failure or audit.passed:
            break
    old = json.loads((path / 'summary.json').read_text())
    times = {e['phase']: round(e['time_s']/audit.dt) for e in old['events']}
    return dict(source_id=path.name, fixed_reference_id=(ref_path or path).name, input='archived actual actuator ctrl for each solved 2 ms interval, XML order',
                source_physics_steps=len(ctrl), evaluated_substeps=audit.step, passed=audit.passed,
                failure=audit.failure, max_replay_qpos_difference=peak_delta,
                events=[dict(e, original_end_step=times.get(e['phase']),
                             delta_steps=e['end_step']-times[e['phase']] if e['phase'] in times else None) for e in audit.events])


def collision_trial(path):
    """Compare geometry identities, force cutoff, exact failing time in P6's raw final contact rows."""
    cfg = json.loads((path/'config.json').read_text())
    ref = json.loads((path/'summary.json').read_text())
    m = build(cfg)
    from learning.b0.physics import ContactMeter
    judge = ContactMeter(m, 'preview_floor', 'back', cfg['contact_threshold_n'], cfg['wheel_threshold_n'])
    final_s = round(ref['sim_time_s'] - cfg['timestep_s'], 6)
    contacts = []
    with (path/'contacts.csv').open() as stream:
        for row in csv.DictReader(stream):
            if abs(float(row['time_s']) - final_s) > 1.e-6 or float(row['normal_n']) <= judge.contact_threshold_n:
                continue
            g1,g2 = int(row['geom1_id']),int(row['geom2_id'])
            if judge.robot[g2]:
                g1,g2 = g2,g1
            if judge.robot[g1] and judge.is_door[g2]:
                label,index = judge._door_pair(g1,g2)
                contacts.append(dict(actual_geom1=judge.names[g1],actual_geom2=judge.names[g2],
                                     normal_n=float(row['normal_n']),label=label,allowed=index is not None))
    reasons = sorted({r['label'] for r in contacts if not r['allowed']})
    failure = 'unexpected_contact:' + ','.join(reasons) if reasons else None
    return dict(archive_run=path.name, original_failure=ref['failure'], interval_start_s=final_s,
                interval_end_s=ref['sim_time_s'], contacts=contacts, recovered_failure=failure,
                agrees=ref['failure']==failure,
                coverage='archived failing interval collision pairs only; no earlier 500 Hz poses/controls in this archive')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--reference', type=Path, help='fixed nominal reference (defaults to source for calibration)')
    parser.add_argument('--side', choices=('push','pull'))
    parser.add_argument('--collision-record', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args()
    if not args.collision_record and not args.side:
        parser.error('--side is required for a trajectory replay')
    result = collision_trial(args.episode) if args.collision_record else compare(args.episode,args.side,args.reference)
    result['mujoco_version']=mj.__version__
    print(json.dumps(result, indent=2))
    args.output.parent.mkdir(exist_ok=True,parents=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
