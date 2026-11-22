"""Score the one measured 20 ms interval containing the first contact failure."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.models import Dynamics

from learning.b0.contact_model import CONTEXT_NAMES, SCHEMA, ContactRepresentation
from learning.b0.contact_replay import ContactEpisode
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, make_model


def training_groups(checkpoint):
    folder = checkpoint.parent
    online = folder / 'actual_config.json'
    names = set()
    cfg_path = folder / 'config.json'
    if online.is_file():
        run = json.loads(online.read_text())
        cfg = run['cfg']
        teachers = cfg['references'] + cfg['additional_teacher_episodes']
        names.update(teachers)
        if run['initialization']['resume']:
            parent = Path(run['initialization']['resume']).parent / 'actual_config.json'
            if json.loads(parent.read_text())['cfg'] != cfg:
                raise ValueError('Resume used a different training configuration')
        cfg_path = Path(cfg['wm_checkpoint']).parent / 'config.json'
    sources = json.loads(cfg_path.read_text())['sources']
    return names | {episode['group'] for episode in sources if episode['split'] == 'train'}


@torch.no_grad()
def score_last(path, rep, dynamics, seen, device):
    ep = ContactEpisode.read(path, device)
    meta = json.loads((path / 'metadata.json').read_text())
    bounds = np.load(path / 'physics_step.npy')
    start, end = (int(i) for i in bounds[-2:])
    failure = meta['first_failure_physics_interval']
    targets = np.load(path / 'substeps/physical_target.npy', mmap_mode='r')[start:end]
    if (not ep.valid[-1] or end - start != 10 or meta['failure'] != 'lost_grip'
            or not (start <= failure < end) or end - failure - 1 != meta['post_failure_completed_physics_steps']
            or not np.array_equal(targets, np.broadcast_to(targets[0], targets.shape))):
        raise ValueError(f'Invalid terminal hold at {path}')
    q0 = ep.state[-2:-1]
    aux, state = dynamics(rep.represent(q0), ep.action[-1:], q0[:, :7], ep.context[None])
    full = rep.reconstruct_full_state(aux, state)
    predicted_tcp = rep.tcp_pose(aux, full[:, 7:31])[0][0].cpu().numpy()
    true_tcp = np.load(path / 'tcp_world.npy')[-1]
    true_jaw = float(np.load(path / 'opening_m.npy')[-1] * 1000)
    predicted_jaw = float((full[0, 29] - full[0, 30]).item() * 1000)
    actual_angle = float(np.rad2deg(np.load(path / 'qpos.npy', mmap_mode='r')[-1, -1]))
    predicted_angle = float(np.rad2deg(full[0, 61].item()))
    return dict(episode=ep.group, source=str(path), dataset_split=ep.split,
                listed_in_wm_training_sources=ep.group in seen, outcome=meta['failure'],
                terminal_policy_index=len(ep.action)-1, interval_start_substep=start, interval_end_substep=end,
                first_failure_zero_based_interval=failure, physical_substeps_after_first_failure=end-failure-1,
                observed_final_finger_load_n=np.load(path/'substeps/finger_load_N.npy', mmap_mode='r')[-1].tolist(),
                observed_door_deg=actual_angle, predicted_door_deg=predicted_angle,
                abs_door_error_deg=abs(predicted_angle-actual_angle),
                observed_tcp_world_m=true_tcp.tolist(), predicted_tcp_world_m=predicted_tcp.tolist(),
                tcp_error_mm=float(1000*np.linalg.norm(true_tcp-predicted_tcp)),
                observed_jaw_mm=true_jaw, predicted_jaw_mm=predicted_jaw, abs_jaw_error_mm=abs(true_jaw-predicted_jaw))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--episodes', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    device = 'cuda:0'
    weights = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
    if weights['schema'] != SCHEMA:
        raise ValueError('Unexpected contact representation')
    model = make_model()
    rep = ContactRepresentation(model, device)
    mapping = ActionMap(model)
    hidden = weights['cfg']['wm_hidden'] if 'cfg' in weights else weights['hidden']
    dyn = Dynamics(rep, 23, len(CONTEXT_NAMES), tensor(mapping.scale, device),
                   tensor(mapping.offset, device), tuple(hidden)).to(device)
    dyn.load_state_dict(weights['dyn'], strict=True)
    dyn.eval()
    seen = training_groups(args.checkpoint)
    rows = [score_last(path, rep, dyn, seen, device) for path in args.episodes]
    result = dict(checkpoint=str(args.checkpoint), checkpoint_sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
                  method='One prediction from the real pre-interval state and the actual 20 ms held action; observed successor from native acquisition. The first lost-grip substep occurs inside that interval.',
                  scope='Two separately collected pull-side terminal cases; each is a one-interval diagnostic outside the frozen eight-episode validation comparison.',
                  teacher_training_groups=sorted(seen), cases=rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
