"""Re-score identical legal physical transitions with both action-rate definitions."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_model import ContactRepresentation, contact_state
from learning.b0.contact_policy import DoorMotions
from learning.b0.contact_reward import reward_actions, reward_terms
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, make_model


def measure(cohort, config, device):
    def array(name):
        return np.load(cohort / (name + '.npy'), mmap_mode='r')
    # Terminal rows that failed prior to the 20 ms endpoint have a diagnostic
    # successor beyond failure. They cannot supply a legal 20 ms score.
    fail = array('first_fail_substep')
    eligible = array('valid') & ((fail == 0) | (fail == 10))
    def rows(name):
        return tensor(array(name)[eligible], device)
    action = rows('clipped').requires_grad_()
    previous = rows('prev_action')
    model = make_model()
    rep = ContactRepresentation(model, device)
    paths = [Path(config['reference_directory']) / name for name in config['references']]
    bank = DoorMotions(paths, rep, device)
    target = bank.body_state(torch.as_tensor(array('frame')[eligible]+1, device=device))
    state = contact_state(rows('next_qpos'), rows('next_qvel'))
    aux, features = state[:, :7], rep.represent(state)
    result = {}
    for mode in ('canonical', 'fixed_effort'):
        terms = reward_terms(rep, features, aux, action, previous, target, coordinates=mode)
        rep.reward_coordinates = mode
        official = rep.compute_wm_reward_from_reference(
            features, aux, rep.joint_state(features), action, previous, *target)
        torch.testing.assert_close(sum(terms.values()), official, atol=3e-5, rtol=2e-6)
        gradient, = torch.autograd.grad(terms['action_rate'].sum(), action)
        norm = gradient.norm(dim=-1)
        result[mode] = dict(mean_reward=float(official.detach().mean()),
                            components_mean={k:float(v.detach().mean()) for k,v in terms.items()},
                            action_rate_gradient_canonical_l2_mean=float(norm.mean()),
                            action_rate_gradient_canonical_l2_max=float(norm.max()),
                            j2_gradient_abs_mean=float(gradient[:,17].abs().mean()),
                            max_abs_sum_error=float((sum(terms.values())-official).detach().abs().max()))
    # Both branches must score home against the reset sentinel as zero in effort units.
    home = rep.reward_home[None]
    act, previous_reset = reward_actions(rep, home, torch.zeros_like(home), 'fixed_effort', False)
    torch.testing.assert_close(act, previous_reset)
    _, previous_zero = reward_actions(rep, home, torch.zeros_like(home), 'fixed_effort', True)
    return dict(source=str(cohort),all_valid_intervals=int(array('valid').sum()),
                scored_complete_through_20ms=int(eligible.sum()),action_channels=ActionMap(model).names,
                reset_effort_previous_l2=float(previous_reset.norm()),
                real_canonical_zero_effort_l2=float(previous_zero.norm()),scores=result,
                equal_canonical_delta_j2_rate_ratio=float(rep.reward_unit[17].reciprocal().square()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', required=True, type=Path)
    parser.add_argument('--source-config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    measured = measure(args.cohort, json.loads(args.source_config.read_text())['cfg'], 'cuda:0')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(measured, f, indent=2, allow_nan=False)
        f.write('\n')
