"""Measure how actions affect a predicted physical TCP with all WM parameters frozen."""
import argparse
import json
from pathlib import Path

import torch
from supermimic.models import Dynamics

from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import make_model, ActionMap
from learning.b0.reference import load_episode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('checkpoint', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    checkpoint = torch.load(args.checkpoint, weights_only=True, map_location='cpu')
    device = 'cpu'
    model = make_model()
    amap = ActionMap(model)
    rep = RobotRepresentation(model, device)
    dyn = Dynamics(rep, 23, 1, tensor(amap.scale, device), tensor(amap.offset, device),
                   tuple(checkpoint['cfg']['wm_hidden']))
    dyn.load_state_dict(checkpoint['dyn'])
    dyn.eval().requires_grad_(False)
    episode = load_episode(Path(checkpoint['cfg']['reference_root']) / 'moving_arm_wm_validation')
    k = 100
    s = full_state(tensor(episode['qpos'][k:k+1], device), tensor(episode['qvel'][k:k+1], device))
    aux, r = s[:, :7], rep.represent(s)
    actions = tensor(episode['action_clipped'][k:k+7], device).requires_grad_()
    for a in actions.unbind(0):
        aux, r = dyn(r, a[None], aux, torch.ones(1, 1))
    # Direct physical output. No action-rate penalty or value head contributes.
    tcp = rep.world_frame_bodies(aux, r)[0][0, -1]
    jac = torch.stack([torch.autograd.grad(x, actions, retain_graph=True)[0] for x in tcp])
    norms = jac.square().sum((0, 2)).sqrt()
    result = dict(checkpoint=str(args.checkpoint), actor_update=checkpoint['updates'], episode='moving_arm_wm_validation',
                  start=k, horizon=7, loss_output='predicted world TCP xyz, metres',
                  jacobian_shape=list(jac.shape), jacobian_frobenius_per_action_step=norms.tolist(),
                  all_wm_parameters_frozen=not any(p.requires_grad for p in dyn.parameters()),
                  any_wm_parameter_gradient=any(p.grad is not None for p in dyn.parameters()))
    if not torch.isfinite(jac).all() or norms[0] == 0:
        raise RuntimeError(f'invalid 7-step TCP gradient: {result}')
    with args.output.open('x') as f:
        f.write(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    main()
