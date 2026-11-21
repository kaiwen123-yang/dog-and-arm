"""Compare two differentiable rewards on the same already measured physical trajectories."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
import yaml

from learning.b0.model import FreeTrackingRepresentation, RobotRepresentation, full_state, tensor
from learning.b0.physics import ROOT, make_model
from learning.b0.reference import load_episode


def state(q, v):
    return full_state(tensor(q, 'cpu'), tensor(v, 'cpu'))


def measure(rep, reference, q, v, actions):
    # O1 scores the post-step robot against the current command, then advances the clip.
    n = len(actions)
    target = state(reference['qpos'][:n], reference['qvel'][:n])
    bodies = rep.fk(target[:, :3], target[:, 3:7], target[:, 7:31],
                    target[:, 31:34], target[:, 34:37], target[:, 37:])
    actual = state(q[1:n+1], v[1:n+1]).requires_grad_(True)
    rep_state = rep.represent(actual)
    prev = np.concatenate((reference['last_action'][:1], actions[:-1]))
    reward = rep.compute_wm_reward_from_reference(rep_state, actual[:, :7], rep.joint_state(rep_state),
                                                  tensor(actions, 'cpu'), tensor(prev, 'cpu'), *bodies)
    gradient = torch.autograd.grad(reward.sum(), actual)[0]
    if not torch.isfinite(gradient).all():
        raise ValueError('Non-finite reward gradient on recorded physical states')
    return dict(mean_reward_s=float((reward.detach() / rep.dt).mean()),
                mean_gradient_norm=float(gradient.norm(dim=1).mean()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evaluation', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / 'config/b0/free_metric_cloud.yaml').read_text())
    provenance = json.loads((args.evaluation / 'evaluation.json').read_text())
    raw = ROOT / provenance['raw_path'] / 'physical'
    model = make_model()
    reps = {'original': RobotRepresentation(model, 'cpu'),
            'metric': FreeTrackingRepresentation(model, cfg['free_tracking_reward'], 'cpu')}
    rows = []
    for name in ('support', 'moving_arm', 'park'):
        ref = load_episode(Path(cfg['reference_root']) / name)
        case = raw / f'{name}_F01'
        for actor, q, v, a in (
            ('native_teacher', ref['qpos'], ref['qvel'], ref['action_clipped']),
            ('actor_F01', *(np.load(case / (field + '.npy')) for field in ('qpos', 'qvel', 'action_clipped')))):
            rows.append(dict(reference=name, source=actor, transitions=len(a),
                             scores={key: measure(rep, ref, q, v, a) for key, rep in reps.items()}))
    args.out.write_text(json.dumps(dict(evaluation=str(args.evaluation), rows=rows),
                                   indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
