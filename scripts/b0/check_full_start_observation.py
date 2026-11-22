"""Compare the inputs and actions actually seen at translated full-task development starts."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_policy import DoorMotions, sensor
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import make_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--side', choices=['pull', 'push'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((args.run / 'run_spec.json').read_text())['plan']
    root = args.run / args.side / 'full'
    ref_name = json.loads((root / 'nominal' / 'result.json').read_text())['episode']
    rep = RobotRepresentation(make_model(), 'cpu')
    bank = DoorMotions([Path(spec['source']) / ref_name], rep, 'cpu')
    frames = torch.zeros(1, dtype=torch.long)
    rows = []
    with torch.no_grad():
        for case in ('nominal', 'C02', 'C03', 'C04', 'C05'):
            trial = json.loads((root / case / 'result.json').read_text())
            raw = Path(trial['raw_directory'])
            q, v, a = [np.load(raw / (name + '.npy'), mmap_mode='r')
                       for name in ('qpos', 'qvel', 'raw_action')]
            q0, v0 = tensor(q[:1], 'cpu'), tensor(v[:1], 'cpu')
            obs = sensor(rep, full_state(q0, v0), torch.zeros(1, 23))
            wm_goal, actor_goal = bank.goals(rep, frames, q0[:, :7])
            if case == 'nominal':
                base = (q.copy(), a.copy(), obs, wm_goal, actor_goal)
            qb, ab, ob, wb, gb = base
            stop = min(51, len(q), len(qb), len(a), len(ab))
            offset = q[0, :2] - qb[0, :2]
            rows.append(dict(case=case, initial_xy_offset_m=offset.tolist(),
                sensor_max_abs=float((obs-ob).abs().max()),
                actor_goal_max_abs=float((actor_goal-gb).abs().max()),
                wm_goal_max_abs=float((wm_goal-wb).abs().max()),
                first_action_max_abs=float(np.max(np.abs(a[0]-ab[0]))),
                compared_policy_frames=stop,
                first_second_action_max_abs=float(np.max(np.abs(a[:stop]-ab[:stop]))),
                first_second_relative_offset_change_m=float(np.linalg.norm(
                    q[:stop,:2]-qb[:stop,:2]-offset,axis=1).max()),
                passed=trial['passed'], first_failure=trial['first_failure']))
    with args.output.open('x') as f:
        json.dump(dict(backend=spec['backend'], checkpoint=spec['checkpoint'], reference=ref_name,
                       initial_history='ten identical initial observations, zero prior command',
                       source=str(args.run), rows=rows),f,indent=2,allow_nan=False)
        f.write('\n')


if __name__ == '__main__':
    main()
