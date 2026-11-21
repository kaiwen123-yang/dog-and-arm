"""Score a frozen WM on the commands its frozen Actor actually issued in F01."""
import argparse
from functools import partial
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
from supermimic.models import Dynamics

from learning.b0.evaluate import model_diagnostics
from learning.b0.model import RobotRepresentation, tensor
from learning.b0.physics import ActionMap, ROOT, make_model
from learning.b0.training import FreeRun


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--evaluation', type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads((args.evaluation / 'evaluation.json').read_text())
    ckpt = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    spec = json.loads((args.evaluation.parent / 'actual_config.json').read_text())
    same_run = args.evaluation.parent.resolve() == args.checkpoint.parent.resolve()
    restart = spec.get('checkpoint_restart')
    if (spec['cfg'] != ckpt['cfg'] or not
            (same_run or (restart and Path(restart).resolve() == args.checkpoint.resolve()))):
        raise ValueError('Checkpoint and evaluation have different training provenance')
    if (evidence['seed'], evidence['actor_updates']) != (ckpt['seed'], ckpt['updates']):
        raise ValueError('The evaluation must use the supplied checkpoint')
    model = make_model()
    action = ActionMap(model)
    rep = RobotRepresentation(model, 'cpu')
    dyn = Dynamics(rep, model.nu, 1, tensor(action.scale, 'cpu'), tensor(action.offset, 'cpu'),
                   tuple(ckpt['cfg']['wm_hidden']))
    dyn.load_state_dict(ckpt['dyn'])
    dyn.eval().requires_grad_(False)
    rollout = partial(FreeRun.rollout, SimpleNamespace(device='cpu', rep=rep, dyn=dyn))
    result = {}
    for name in ('support', 'moving_arm', 'park'):
        case = name + '_F01'
        folder = ROOT / evidence['raw_path'] / 'physical' / case
        counts = np.load(folder / 'substep_count.npy')
        # A partial last tick has no 20 ms model target. Keep it in the actual task score.
        incomplete = np.flatnonzero(counts != 10)
        n = len(counts) if not len(incomplete) else int(incomplete[0])
        if len(incomplete) and incomplete.tolist() != [len(counts) - 1]:
            raise ValueError(f'{case} has an interior partial interval')
        ep = {k: np.load(folder / (k + '.npy'))[:n+1] for k in ('qpos', 'qvel', 't', 'tcp_world')}
        a = np.load(folder / 'action_clipped.npy')[:n]
        result[case] = model_diagnostics(model, ep, a, rollout, episode_id=case, train_episode_ids=[])
    output = dict(checkpoint=str(args.checkpoint), seed=ckpt['seed'], actor_updates=ckpt['updates'],
                  source='post-checkpoint deterministic Actor development trajectories, open-loop WM', cases=result)
    (args.evaluation / 'on_policy_model_errors.json').write_text(json.dumps(output, indent=2,
                                                                           allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
