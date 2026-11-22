"""Local grip-force surrogate fitted and tested on independent real Warp transitions."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from learning.b0.contact_force import PeakDoorForce
from learning.b0.contact_model import ContactRepresentation, contact_context, contact_state
from learning.b0.contact_warp import ContactPlant, PHASE_ID
from learning.b0.physics import ActionMap, make_model


@torch.no_grad()
def collect(plant, rep, root, split, batches, device):
    data = []
    for side_id, side in enumerate(('pull', 'push')):
        for angle in (0, 5, 15):
            name = f'{side}_{angle}_{split}' + ('_grip' if angle == 0 else '')
            path = root/name
            meta = json.loads((path/'metadata.json').read_text())
            if not meta['success'] or meta['wm_split'] != split:
                raise ValueError(path)
            def load(key):
                return torch.as_tensor(np.load(path/(key+'.npy')), device=device, dtype=torch.float32)
            q, v, actions = (load(key) for key in ('qpos', 'qvel', 'action_clipped'))
            n = meta['full_intervals']
            phase_indices = np.load(path/'substeps/phase.npy')[:n*10].reshape(n,10)
            ids = torch.tensor([PHASE_ID[p] for p in meta['phases']], device=device)[phase_indices]
            # All 110 physics steps must lie in open or hold; use only valid prior prefixes.
            grip = (ids == PHASE_ID['open']) | (ids == PHASE_ID['hold'])
            candidates = grip.all(-1).unfold(0, 11, 1).all(-1).nonzero().flatten()+10
            side_tensor = torch.full((plant.count,), side_id, device=device, dtype=torch.long)
            context = contact_context(plant.model, side, device).expand(plant.count,-1)
            for _ in range(batches):
                frames = candidates[torch.randint(len(candidates), (plant.count,), device=device)]
                plant.reset(q[frames-10], v[frames-10])
                valid = torch.ones_like(frames, dtype=torch.bool)
                for k in range(-10, 0):
                    r = plant.step_contact(actions[frames+k], side_tensor, ids[frames+k])
                    valid &= r['valid_full_interval'] & (r['first_fail_substep'] == 0)
                state = contact_state(plant.data.qpos[:], plant.data.qvel[:])
                features = rep.represent(state)
                applied = actions[frames].clone()
                # Log-uniform physical offsets cover both sides of the 6 N threshold.
                amp = 10**torch.empty((plant.count,1),device=device).uniform_(-4., -1.15)
                amp[::8] = 0  # matched unperturbed examples
                applied[:,16:] += torch.randn_like(applied[:,16:])*amp*torch.tensor(
                    [1.]*6+[.08],device=device)/plant.scale[16:]
                applied.clamp_(-1,1)
                r = plant.step_contact(applied, side_tensor, ids[frames], record=True)
                valid &= r['valid_full_interval']
                forces = r['substeps']['door_robot_force_N'].norm(dim=-1)
                data.append(tuple(t[valid].detach().cpu() for t in
                                  (features, applied, context, forces, frames, torch.full_like(frames,angle))))
    return tuple(torch.cat(items) for items in zip(*data))


def score(force, data, device):
    rep, a, ctx, labels = [x.to(device) for x in data[:4]]
    peak = labels.amax(-1)
    with torch.no_grad():
        pred = force(rep, a, ctx)
    def group(use):
        target, estimate = peak[use], pred[use]
        return dict(n=len(target), actual_over_6=int((target>6).sum()), pred_over_6=int((estimate>6).sum()),
                    missed_over_6=int(((target>6)&(estimate<=6)).sum()),
                    false_alarm=int(((target<=6)&(estimate>6)).sum()),
                    mae_n=float((target-estimate).abs().mean()) if len(target) else None,
                    near_limit_n=int(((target-6).abs()<=2).sum()))
    return {side:group(ctx[:,0]==index) for index, side in enumerate(('pull','push'))}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--references', type=Path, default=Path('results/raw_large/b0/contact_held_r1'))
    args = p.parse_args()
    if args.run in ('','.','..') or Path(args.run).name != args.run:
        p.error('Use a fresh run name')
    out = Path('results/b0')/args.run
    raw = Path('results/raw_large/b0')/args.run
    out.mkdir(exist_ok=False)
    raw.mkdir(exist_ok=False)
    device = 'cuda:0'
    torch.manual_seed(20261122)
    model = make_model()
    plant = ContactPlant(model, 128, device)
    rep = ContactRepresentation(model,device)
    values = {}
    keys = ('rep','action','context','net_force_2ms_n','frame','goal_deg')
    for split, batches in (('train',16), ('validation',6)):
        values[split] = collect(plant,rep,args.references,split,batches,device)
        (raw/split).mkdir()
        for key, value in zip(keys, values[split]):
            np.save(raw/split/(key+'.npy'), value.numpy())
    force = PeakDoorForce(ActionMap(model), device)
    opt = torch.optim.AdamW(force.parameters(), lr=.001, weight_decay=.0001)
    train = [x.to(device) for x in values['train'][:4]]
    target = train[3].amax(-1)
    for _ in range(2000):
        i = torch.randint(len(target),(512,),device=device)
        estimate = force(train[0][i], train[1][i], train[2][i])
        loss = F.smooth_l1_loss(estimate.log1p(),target[i].log1p(),beta=.1)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
    torch.save(force.state_dict(),out/'force_002000.pt')
    report = dict(seed=20261122,updates=2000,label='maximum norm of signed door/robot resultant at 10 physical substeps',
                  inputs='current model representation, clipped action and side; open/hold phases only',
                  train_groups=6,validation_groups=6,results={s:score(force,d,device) for s,d in values.items()})
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
