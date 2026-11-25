"""Calibrate camera-to-actor features and check a complete differentiable H32 update."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np
import torch
from torch.nn import functional as F

from learning.multimodal.actor import MultimodalActor, load_actor
from learning.multimodal.dataset import EpisodeDataset, training_vocabulary
from learning.multimodal.wm_replay import PhysicalReplay
from learning.multimodal.world_model import HORIZON, PerceptualDynamics, VisualBridge, camera_features, make_policy_objective
from scripts.multimodal.train_actor import bc_objective
from scripts.multimodal.train_wm import clock, fit_units, peak_mb, save_checkpoint, write_json


@torch.no_grad()
def camera_pairs(actor, dataset):
    compact, encoded = [], []
    # Slot zero is the explicit missing-frame sentinel; each real exposure is used once.
    length = len(dataset.images['rgb'])
    for start in range(1, length, 128):
        sl = slice(start, start+128)
        inputs = [dataset.images[k][sl] for k in ('rgb', 'depth', 'depth_valid')]
        compact.append(camera_features(*inputs))
        encoded.append(actor.encode_visual(*inputs))
    return torch.cat(compact), torch.cat(encoded)


def metrics(model, bridge, x, target):
    with torch.no_grad():
        y = bridge(model.v_units(x))
        return dict(frames=len(x), feature_rmse=(y-target).square().mean().sqrt().item(),
                    constant_mean_rmse=(target-bridge.mean).square().mean().sqrt().item())


def gradient_check(actor, objective, batch):
    """Reverse-mode and centered differences on one shared action-output bias direction."""
    actor.zero_grad(set_to_none=True)
    loss, extra = objective(actor, batch)
    bias = actor.head[-1].bias
    grad, = torch.autograd.grad(loss, (bias,))
    direction = grad.detach() / grad.detach().norm().clamp_min(1e-15)
    ad = float(grad.detach() @ direction)
    base = bias.detach().clone()
    rows = []
    with torch.no_grad():
        try:
            for eps in (.032, .008, .002):
                bias.copy_(base+eps*direction)
                plus = objective(actor, batch)[0].item()
                bias.copy_(base-eps*direction)
                minus = objective(actor, batch)[0].item()
                rows.append(dict(epsilon=eps, central=(plus-minus)/(2*eps), plus=plus, minus=minus))
        finally:
            bias.copy_(base)
    return dict(autograd=ad, finite=math.isfinite(ad) and all(math.isfinite(r['central']) for r in rows),
                center_loss=float(loss.detach()), difference=rows,
                h32_reward=float(extra['h32_reward']), feature_change_rms=float(extra['estimated_actor_feature_change_rms']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--wm', type=Path)
    parser.add_argument('--actor', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=600)
    parser.add_argument('--batch', type=int, default=256)
    parser.add_argument('--imagination-batch', type=int, default=32)
    parser.add_argument('--weight', type=float, default=.15)
    parser.add_argument('--seed', type=int, default=7042)
    parser.add_argument('--probe', action='store_true', help='Discard scratch-model compute measurements')
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    if not args.probe and (not args.actor or not args.wm):
        parser.error('The calibrated policy objective requires the trained common actor and WM')
    args.out.mkdir(parents=True, exist_ok=True)
    device = torch.device(args.device)
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision('high')
    torch.manual_seed(args.seed)
    rng = torch.Generator(device=device).manual_seed(args.seed+1)
    if args.probe:
        vocab = training_vocabulary(args.data)
        actor = MultimodalActor(vocab).to(device)
        ids = None
    else:
        actor, vocab, _ = load_actor(args.actor, device)
        policy_wm = torch.load(args.wm, map_location=device, weights_only=False)
        ids = [e['episode_id'] for e in policy_wm['episodes']]
    train = EpisodeDataset(args.data, 'train', vocab, device, episode_ids=ids)
    if args.probe:
        rows = torch.tensor(train.expert_rows, device=device)
        actor.fit_scalers(train.states['proprio'][rows], train.states['action'][rows])
        model = PerceptualDynamics().to(device)
        fit_units(model, PhysicalReplay(args.data, 'train', device))
    else:
        model = PerceptualDynamics(policy_wm['width']).to(device)
        model.load_state_dict(policy_wm['model'])
    model.eval().requires_grad_(False)
    actor.eval()
    actor.freeze_encoders()
    if device.type == 'cuda':
        torch.cuda.reset_peak_memory_stats(device)
    compact, target = camera_pairs(actor, train)
    bridge = VisualBridge(target.shape[-1]).to(device)
    bridge.mean.copy_(target.mean(0))
    bridge.scale.copy_(target.std(0, correction=0).clamp_min(.02))
    opt = torch.optim.AdamW(bridge.parameters(), lr=.001)
    begin = clock(device)
    for _ in range(args.steps):
        ix = torch.randint(len(compact), (args.batch,), generator=rng, device=device)
        prediction = bridge(model.v_units(compact[ix]))
        error = (prediction-target[ix]) / bridge.scale
        loss = F.smooth_l1_loss(error, torch.zeros_like(error))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        opt.step()
    bridge_sec = clock(device) - begin
    regr = {'train': metrics(model, bridge, compact, target)}
    if not args.probe:
        val = EpisodeDataset(args.data, 'validation', vocab, device)
        regr['validation'] = metrics(model, bridge, *camera_pairs(actor, val))
        del val
    cfg = dict(horizon=HORIZON, imagination_batch=args.imagination_batch, discount=.985, weight=args.weight,
               camera_period_ticks=5, bridge_updates=args.steps, bridge_batch=args.batch)
    name = 'wm_probe_objective.pt' if args.probe else 'wm_objective.pt'
    ckpt = args.out / name
    actor_hash = hashlib.sha256(args.actor.read_bytes()).hexdigest() if args.actor else None
    save_checkpoint(ckpt, dict(width=model.width, actor_visual_dim=target.shape[-1], model=model.state_dict(),
                               bridge=bridge.state_dict(), bridge_optimizer=opt.state_dict(), bridge_rng=rng.get_state(),
                               objective=cfg, common_actor_sha256=actor_hash, wm_parent=str(args.wm),
                               wm_updates=None if args.probe else policy_wm['updates']))
    objective = make_policy_objective(ckpt, device)
    sample = train.sample(args.batch, np.random.default_rng(args.seed+2))
    n_forward = 6 if args.probe else 2
    begin = clock(device)
    checks = []
    for _ in range(n_forward):
        actor.zero_grad(set_to_none=True)
        wm_loss, extra = objective(actor, sample)
        wm_loss.backward()
        wm_norm = torch.nn.utils.clip_grad_norm_(actor.parameters(), 1e12, error_if_nonfinite=True)
        checks.append(dict(model_gradient_norm=float(wm_norm),
                           h32_reward=float(extra['h32_reward']), loss=float(wm_loss.detach()),
                           feature_change_rms=float(extra['estimated_actor_feature_change_rms'])))
    runtime = clock(device) - begin
    actor.zero_grad(set_to_none=True)
    bc_loss = bc_objective(actor, actor(sample), sample['action'])
    bc_loss.backward()
    bc_norm = torch.nn.utils.clip_grad_norm_(actor.parameters(), 1e12, error_if_nonfinite=True)
    # Finite differences are diagnostic and use full fp32 matmul to limit roundoff.
    torch.set_float32_matmul_precision('highest')
    derivative = gradient_check(actor, objective, sample)
    summary = dict(kind='discarded compute pilot' if args.probe else 'calibrated training-only world model',
                   actor=str(args.actor), common_actor_sha256=actor_hash, wm=str(args.wm), objective=cfg,
                   bridge_seed=args.seed, bridge_train_s=bridge_sec, bridge_features=regr,
                   train_episode_ids=train.episode_ids, imaginary_forward_backward_count=n_forward,
                   imaginary_forward_backward_s=runtime, initial_gradients=checks, common_bc_loss=float(bc_loss.detach()),
                   common_bc_gradient_norm=float(bc_norm), gradient_check=derivative, peak_allocated_MiB=peak_mb(device))
    write_json(args.out / 'imagination.json', summary)
    print(json.dumps({k:summary[k] for k in ('imaginary_forward_backward_s','peak_allocated_MiB','gradient_check')}),
          flush=True)
    if args.probe:
        ckpt.unlink()


if __name__ == '__main__':
    main()
