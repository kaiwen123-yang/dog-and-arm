"""Fit the O1 door GenCoord WM on explicitly listed measured episodes."""
import argparse
import csv
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('TORCH_COMPILE_DISABLE', '1')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import numpy as np
import torch
from supermimic.learners.wm_learner import WorldModelLearner
from supermimic.models import Dynamics

from learning.b0.contact_model import (CONTEXT_NAMES, SCHEMA, ContactRepresentation, ContactTcpLoss,
                                      ContactWorldModelCfg, transfer_wm)
from learning.b0.contact_replay import ContactEpisode, ContactWindows, MODES
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, WHEELS, make_model


def prediction_errors(rep, aux, state, target, wheel_v):
    full = rep.reconstruct_full_state(aux, state)
    xyz = rep.tcp_pose(aux, full[..., 7:31])[0]
    true_xyz = rep.tcp_pose(target[..., :7], target[..., 7:31])[0]
    diff = full-target
    return dict(tcp_mm=1000*torch.linalg.vector_norm(xyz-true_xyz, dim=-1),
                root_mm=1000*torch.linalg.vector_norm(diff[..., :3], dim=-1),
                root_angle_deg=torch.rad2deg(2*torch.atan2(
                    torch.minimum(torch.linalg.vector_norm(full[..., 3:7]-target[..., 3:7], dim=-1),
                                  torch.linalg.vector_norm(full[..., 3:7]+target[..., 3:7], dim=-1)),
                    torch.maximum(torch.linalg.vector_norm(full[..., 3:7]-target[..., 3:7], dim=-1),
                                  torch.linalg.vector_norm(full[..., 3:7]+target[..., 3:7], dim=-1))))*2,
                jaw_mm=1000*(diff[..., 29]-diff[..., 30]).abs(),
                finger_residual_mm=1000*(diff[..., 29]+diff[..., 30]).abs(),
                wheel_speed_rad_s=diff.index_select(-1, wheel_v).square().mean(-1).sqrt(),
                door_deg=torch.rad2deg(diff[..., 61].abs()),
                door_speed_rad_s=diff[..., 62].abs())


@torch.no_grad()
def score(rep, dyn, validation, model, batch_size=192):
    device = validation[0].state.device
    wheel_v = torch.tensor([31+model.joint(n).dofadr.item() for n in WHEELS], device=device)
    rows = []
    for ep in validation:
        for horizon in (1, 7, 32):
            indices = ep.starts(horizon)
            values = {}
            for start in range(0, len(indices), batch_size):
                ix = torch.as_tensor(indices[start:start+batch_size], device=device)
                actual = ep.state[ix]
                aux, r = actual[..., :7], rep.represent(actual)
                hold = aux, r
                velocity_aux, velocity_r = hold
                zero = aux.new_zeros((len(ix), rep.prediction_dim))
                for j in range(horizon):
                    aux, r = dyn(r, ep.action[ix+j], aux, ep.context.expand(len(ix), -1))
                    velocity_aux, velocity_r = rep.apply_prediction(velocity_aux, velocity_r, zero, rep.dt)
                target = ep.state[ix+horizon]
                for label, (a, p) in (('wm', (aux, r)), ('hold', hold), ('constant_velocity', (velocity_aux, velocity_r))):
                    for name, error in prediction_errors(rep, a, p, target, wheel_v).items():
                        values.setdefault((label, name), []).append(error.cpu().numpy())
            # Group by first physical 20 ms interval of each h-step forecast.
            # All windows, including tails ending at a valid terminal, are scored.
            for mode in (*MODES, 'all'):
                chosen = np.ones(len(indices), dtype=bool) if mode == 'all' else ep.modes[indices] == mode
                for (label, metric), batches in values.items():
                    data = np.concatenate(batches)[chosen]
                    valid = np.isfinite(data)
                    sample = data[valid].astype(np.float64)
                    rows.append(dict(group=ep.group, side=ep.side, steps=horizon, mode=mode,
                                     predictor=label, metric=metric, windows=len(data),
                                     nonfinite=int((~valid).sum()),
                                     rmse=np.sqrt(np.mean(sample**2)) if len(sample) else None,
                                     p95=np.percentile(sample, 95) if len(sample) else None,
                                     maximum=sample.max() if len(sample) else None))
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--episodes', type=Path, nargs='+', required=True)
    p.add_argument('--run', required=True)
    p.add_argument('--device', default='cuda:0')
    p.add_argument('--minibatches', type=int, default=200)
    p.add_argument('--batch-size', type=int, default=256)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--tcp-loss', action='store_true', help='Add a 5 mm world TCP loss from differentiable robot kinematics')
    p.add_argument('--train-h32', action='store_true',
                   help='Replace the last two seven-step batches in each block of ten with H32 supervision')
    p.add_argument('--from-b003', type=Path)
    p.add_argument('--resume-wm', type=Path, help='Continue a completed teacher-only WM minibatch in a fresh run')
    a = p.parse_args()
    if Path(a.run).name != a.run or a.run in ('', '.', '..') or a.minibatches <= 0 or a.batch_size <= 0:
        p.error('Use a new run name and positive update/batch sizes')
    torch.manual_seed(a.seed)
    torch.set_float32_matmul_precision('high')
    episodes = [ContactEpisode.read(d, a.device) for d in a.episodes]
    if len({ep.group for ep in episodes}) != len(episodes):
        raise ValueError('Duplicate source episode among supplied groups')
    train = [ep for ep in episodes if ep.split == 'train']
    val = [ep for ep in episodes if ep.split == 'validation']
    if not train or not val:
        raise ValueError('Supply separate training and validation episodes')
    model = make_model()
    rep = (ContactTcpLoss if a.tcp_loss else ContactRepresentation)(model, a.device)
    mapping = ActionMap(model)
    hidden = (2048, 2048, 2048)
    dynamics = Dynamics(rep, 23, len(CONTEXT_NAMES), tensor(mapping.scale, a.device),
                        tensor(mapping.offset, a.device), hidden).to(a.device)
    previous = None
    start = 0
    migrated = []
    if a.resume_wm:
        previous = torch.load(a.resume_wm, weights_only=False, map_location='cpu')
        prior_cfg = json.loads((a.resume_wm.parent / 'config.json').read_text())
        if (a.from_b003 is not None or previous['schema'] != SCHEMA or previous['seed'] != a.seed
                or previous['args']['batch_size'] != a.batch_size or tuple(previous['hidden']) != hidden
                or previous['args']['episodes'] != a.episodes):
            raise ValueError('Continuation requires identical data, batch, seed and network shape')
        start = previous['minibatches']
        if a.minibatches <= start:
            raise ValueError('--minibatches is the absolute endpoint of this WM run')
        migrated = prior_cfg['migrated']
        dynamics.load_state_dict(previous['dyn'])
    elif a.from_b003:
        source = torch.load(a.from_b003, weights_only=False, map_location='cpu')
        migrated = transfer_wm(dynamics, source['dyn'])
        del source
    horizons = (1, 7, 32) if a.train_h32 else (1, 7)
    windows = {s: ContactWindows(train, s) for s in horizons}
    learners = {}
    for s in horizons:
        cfg = ContactWorldModelCfg(batch_size=a.batch_size, horizon=s+1, num_batches=1)
        if a.tcp_loss:
            cfg.nominal_error_tcp_m = .005
        learners[s] = WorldModelLearner(dynamics, rep, cfg, a.device)
    for learner in learners.values():
        learner.optimizers = learners[7].optimizers
    if previous is None:
        for ep in train:
            valid = torch.as_tensor(ep.valid, device=a.device)
            learners[7].update_normalization(ep.state[:-1][valid], ep.action[valid])
    else:
        for opt, weights in zip(learners[7].optimizers, previous['optimizers'], strict=True):
            opt.load_state_dict(weights)
        torch.set_rng_state(previous['torch_rng'])
        torch.cuda.set_rng_state(previous['cuda_rng'], a.device)
        del previous
    out = ROOT / 'results/b0' / a.run
    out.mkdir(parents=True, exist_ok=False)
    def snapshot(count):
        weights = dict(schema=SCHEMA, dyn=dynamics.state_dict(), optimizers=[o.state_dict() for o in learners[7].optimizers],
                       torch_rng=torch.get_rng_state(), cuda_rng=torch.cuda.get_rng_state(a.device),
                       minibatches=count, hidden=hidden, seed=a.seed, args=vars(a))
        torch.save(weights, out / f'wm_{count:06d}.pt')
    config = dict(schema=SCHEMA, seed=a.seed, device=torch.cuda.get_device_name(a.device),
                  torch=torch.__version__, from_b003=prior_cfg['from_b003'] if a.resume_wm else str(a.from_b003) if a.from_b003 else None,
                  resume_wm=str(a.resume_wm) if a.resume_wm else None, start_minibatch=start,
                  migrated=migrated, optimization='fixed O1 Muon/Adam, lr=0.0002, no Actor or Critic update',
                  full=rep.full_state_dim, representation=rep.rep_state_dim, prediction=rep.prediction_dim,
                  context=list(CONTEXT_NAMES), batch_size=a.batch_size, hidden=hidden, minibatches=a.minibatches,
                  training_horizons=horizons, h32_per_ten=2 if a.train_h32 else 0, tcp_loss=a.tcp_loss,
                  loss_scales=vars(learners[7].cfg), actual_physics='native held teacher',
                  sources=[dict(path=str(ep.path), group=ep.group, split=ep.split, side=ep.side,
                                valid_steps=int(ep.valid.sum()), partial_steps=int((~ep.valid).sum()),
                                mode_counts={m:int((ep.modes[ep.valid]==m).sum()) for m in MODES}) for ep in episodes])
    (out/'config.json').write_text(json.dumps(config, indent=2)+'\n')
    snapshot(start)
    counts = dict.fromkeys(horizons, 0)
    with (out/'losses.jsonl').open('x', buffering=1) as log:
        for k in range(start, a.minibatches):
            horizon = 1 if k % 10 < 2 else 7
            if a.train_h32 and k % 10 >= 8:
                horizon = 32
            metrics = learners[horizon].update([windows[horizon].sample(a.batch_size)])
            counts[horizon] += 1
            obj = dict(minibatch=k+1, scored_steps=horizon, **{n:v.item() for n,v in metrics.items()})
            log.write(json.dumps(obj, allow_nan=False)+'\n')
            if k+1 in (50,200,1000) or k+1 == a.minibatches:
                snapshot(k+1)
    dynamics.eval()
    # Frozen weights retain the derivative to real contact-neighbourhood commands.
    for parameter in dynamics.parameters():
        parameter.requires_grad_(False)
    choices = [(ep, int(i)) for ep in val for i in ep.starts(7) if ep.modes[i] == 'two_finger']
    gradient = None
    if choices:
        ep, i = choices[len(choices)//2]
        aux = ep.state[i:i+1, :7]
        r = rep.represent(ep.state[i:i+1])
        actions = ep.action[i:i+7].detach().clone().requires_grad_()
        for command in actions.unbind(0):
            aux, r = dynamics(r, command[None], aux, ep.context[None])
        dtcp = rep.tcp_pose(aux, r[..., 10:34])[0]
        grads = [torch.autograd.grad(output, actions, retain_graph=True)[0] for output in (r[0,58], dtcp[0,0])]
        gradient = dict(episode=ep.group, start=i, horizon=7, output='door rad and TCP world x m',
                        door_first_action_l2=grads[0][0].norm().item(), tcp_first_action_l2=grads[1][0].norm().item())
    scored = score(rep, dynamics, val, model)
    with (out/'validation.csv').open('x') as f:
        writer = csv.DictWriter(f, fieldnames=scored[0], lineterminator='\n')
        writer.writeheader()
        writer.writerows(scored)
    (out/'outcome.json').write_text(json.dumps(dict(completed=a.minibatches, window_updates=counts,
              teacher_samples=(a.minibatches-start)*a.batch_size, online_samples=0, gradient=gradient), indent=2)+'\n')
    print(out, counts, gradient, flush=True)


if __name__ == '__main__':
    main()
