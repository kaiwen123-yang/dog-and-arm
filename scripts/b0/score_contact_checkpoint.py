"""Measure an online contact WM on independent full validation episodes."""
import argparse
import csv
from pathlib import Path

import torch
from supermimic.models import Dynamics

from learning.b0.contact_model import CONTEXT_NAMES, SCHEMA, ContactRepresentation
from learning.b0.contact_replay import ContactEpisode
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, make_model
from scripts.b0.fit_contact_model import score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--episodes', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    device = 'cuda:0'
    checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    if checkpoint['schema'] != SCHEMA:
        raise ValueError('Mismatched contact model schema')
    validation = [ContactEpisode.read(path, device) for path in args.episodes]
    if any(episode.split != 'validation' for episode in validation):
        raise ValueError('Supply complete independent validation episodes')
    model = make_model()
    rep = ContactRepresentation(model, device)
    mapping = ActionMap(model)
    dynamics = Dynamics(rep, 23, len(CONTEXT_NAMES), tensor(mapping.scale, device),
                        tensor(mapping.offset, device), tuple(checkpoint['cfg']['wm_hidden'])).to(device)
    dynamics.load_state_dict(checkpoint['dyn'])
    dynamics.eval()
    rows = score(rep, dynamics, validation, model)
    with args.output.open('x') as output:
        writer = csv.DictWriter(output, fieldnames=rows[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
