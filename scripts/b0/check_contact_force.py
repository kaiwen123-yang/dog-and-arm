"""Check a frozen force surrogate on the existing unmodified online policy cohorts."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_force import PeakDoorForce
from learning.b0.contact_model import ContactRepresentation, contact_context, contact_state
from learning.b0.physics import ActionMap, make_model
from scripts.b0.fit_contact_force import score


@torch.no_grad()
def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--weights', type=Path, required=True)
    p.add_argument('--train-config', type=Path, required=True)
    p.add_argument('--cohorts', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    cfg = json.loads(args.train_config.read_text())['cfg']
    device = 'cuda:0'
    m = make_model()
    rep = ContactRepresentation(m,device)
    head = PeakDoorForce(ActionMap(m),device)
    head.load_state_dict(torch.load(args.weights,map_location=device,weights_only=True))
    head.eval()
    sides, usable = [], []
    for ref in cfg['references']:
        path = Path(cfg['reference_directory'])/ref
        meta = json.loads((path/'metadata.json').read_text())
        n = meta['full_intervals']
        phases = np.array(meta['phases'])[np.load(path/'substeps/phase.npy',mmap_mode='r')[:n*10]].reshape(n,10)
        usable.extend(np.isin(phases, ('open','hold')).all(axis=1).tolist()+[False])
        sides.extend([meta['task']=='push']*(n+1))
    can_score, sides = np.array(usable), np.array(sides)
    contexts = torch.stack([contact_context(m,s,device) for s in ('pull','push')])
    report = {}
    for d in args.cohorts:
        def read(field):
            return np.load(d/(field+'.npy'),mmap_mode='r')
        frames = read('frame')
        valid = read('valid') & can_score[frames]
        def actual(field):
            return torch.as_tensor(read(field)[valid], device=device, dtype=torch.float32)
        measured = actual('sub_door_robot_force_N').norm(dim=-1)
        f = rep.represent(contact_state(actual('qpos'),actual('qvel')))
        c = contexts[torch.as_tensor(sides[frames[valid]],device=device).long()]
        report[str(d)] = score(head,(f,actual('clipped'),c,measured),device)
        # A zero resultant is also physically possible when both fingers are off the rod.
        finger_load = actual('sub_finger_load_N')
        dual = (finger_load > .01).all(-1)
        peak = measured.amax(-1)
        modifier = (1 + (peak / 6.).pow(4)).reciprocal()
        for index, side in enumerate(('pull', 'push')):
            mask = c[:,0] == index
            no_dual = mask & ~dual.any(-1)
            loose = mask & (finger_load <= .01).all(dim=(-1,-2))
            report[str(d)][side].update(
                all_ten_dual=int((mask & dual.all(-1)).sum()),
                no_dual_substeps=int(no_dual.sum()),
                both_unloaded_all_ten=int(loose.sum()),
                both_unloaded_force_weight_above_099=int((loose & (modifier > .99)).sum()))

    with args.output.open('x') as stream:
        json.dump(dict(weights=str(args.weights), source='all valid complete open/hold intervals, including physical terminal successors',results=report),stream,indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
