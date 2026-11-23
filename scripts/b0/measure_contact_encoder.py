"""Measure the reference encoder on the same physical training cohort at each checkpoint."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_model import ContactRepresentation
from learning.b0.contact_policy import DoorMotions, actor_goal_schema, build_actor
from learning.b0.model import tensor
from learning.b0.physics import make_model


@torch.no_grad()
def measure(cohort, checkpoints):
    valid = np.load(cohort / 'valid.npy') & (np.load(cohort / 'first_fail_substep.npy') == 0)
    frames = torch.as_tensor(np.load(cohort / 'frame.npy')[valid], device='cuda')
    q = tensor(np.load(cohort / 'qpos.npy', mmap_mode='r')[valid], 'cuda')
    model = make_model()
    rep = ContactRepresentation(model, 'cuda')
    rows = []
    for path in checkpoints:
        state = torch.load(path, map_location='cpu', weights_only=False)
        cfg = state['cfg']
        refs = [Path(cfg['reference_directory']) / name for name in cfg['references']]
        bank = DoorMotions(refs, rep, 'cuda', actor_schema=actor_goal_schema(cfg))
        _, goal = bank.goals(rep, frames, q[:, :7], q[:, 31])
        actor, _ = build_actor(rep, cfg, model, 'cuda')
        actor.load_state_dict(state['actor'])
        actor.eval()
        normalized = actor.goal_normalizers['motion'](goal)
        z = actor.encoders['motion'](normalized).tanh()
        current_j4 = normalized[:, 19].abs()
        rows.append(dict(checkpoint=str(path), samples=len(frames), absolute_current_j4_normalized_p95=
                         torch.quantile(current_j4, .95).item(), absolute_current_j4_normalized_max=current_j4.max().item(),
                         raw_current_j4_max_rad=goal[:, 19].abs().max().item(),
                         abs_latent_ge_099_fraction=z.abs().ge(.99).float().mean().item(),
                         mean_tanh_derivative=(1.-z.square()).mean().item()))
    return dict(cohort=str(cohort), scope='recorded complete non-terminal training intervals; current reference slot', rows=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, required=True)
    parser.add_argument('--checkpoints', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(measure(args.cohort, args.checkpoints), stream, indent=2, allow_nan=False)
        stream.write('\n')
