"""Compare two measured full references before the teacher's scheduled hold extension."""
from argparse import ArgumentParser
import json
from pathlib import Path

import numpy as np


def read_phases(path, meta):
    phase = np.load(path / 'substeps/phase.npy', mmap_mode='r')
    starts = np.r_[0, np.where(np.diff(phase) != 0)[0] + 1]
    return {meta['phases'][int(phase[t])]: int(t) for t in starts}


def main():
    p = ArgumentParser(description=__doc__)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--after', type=Path, required=True)
    p.add_argument('--phase', choices=('hold', 'final'), required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    paths = [args.before, args.after]
    metas = [json.loads((path/'metadata.json').read_text()) for path in paths]
    if any(not m['full_task'] or not m['held_action_replay'] or not m['success'] for m in metas):
        raise ValueError('Require two complete measured references')
    for field in ('task', 'wm_split', 'physics_dt', 'policy_dt', 'initial_perturbation', 'target_angle_deg'):
        if metas[0][field] != metas[1][field]:
            raise ValueError(f'Reference identity mismatch: {field}')
    phases = [read_phases(path, m) for path, m in zip(paths, metas)]
    stop = min(a[args.phase] for a in phases)
    q, command = [[np.load(path / 'substeps' / name, mmap_mode='r')[:stop] for path in paths]
                  for name in ('qpos.npy', 'physical_target.npy')]
    diff = q[1] - q[0]
    changed = np.flatnonzero(np.any(diff != 0, axis=1))
    result = dict(before=str(args.before), after=str(args.after), phase=args.phase,
                  measured_starts=phases, compared_substeps=stop, physics_dt=metas[0]['physics_dt'],
                  initial_identical=bool(np.array_equal(q[0][0],q[1][0])),
                  first_nonidentical_state=int(changed[0]) if changed.size else None,
                  max_root_xy_difference_m=float(np.linalg.norm(diff[:, :2], axis=1).max()),
                  max_door_angle_difference_deg=float(np.rad2deg(abs(diff[:, -1])).max()),
                  max_per_channel_target_difference=np.abs(command[0]-command[1]).max(axis=0).tolist())
    with args.output.open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write('\n')


if __name__ == '__main__':
    main()
