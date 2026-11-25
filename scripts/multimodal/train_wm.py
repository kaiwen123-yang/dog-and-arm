"""Fit the MM-01 partial-observation world model on episode-local physical data."""
import argparse
import json
import os
from pathlib import Path
import time

import torch
from torch.nn import functional as F

from learning.b0.physics import ActionMap, make_model
from learning.multimodal.wm_replay import PhysicalReplay
from learning.multimodal.world_model import PerceptualDynamics


def save_checkpoint(path, state):
    tmp = path.with_name(path.name + '.tmp')
    torch.save(state, tmp)
    os.replace(tmp, path)


def write_json(path, value):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    os.replace(tmp, path)


def clock(device):
    if device.type == 'cuda':
        torch.cuda.synchronize(device)
    return time.perf_counter()


def peak_mb(device):
    return torch.cuda.max_memory_allocated(device) / 2**20 if device.type == 'cuda' else 0.


def fit_units(model, replay):
    # Robot-servo definition only. No door pose, friction or damping enters the WM.
    mapping = ActionMap(make_model())
    parts = replay.parts
    model.fit_units(parts['p'], parts['o'], parts['vision'][parts['fresh']],
                    parts['p'].new_tensor(mapping.offset), parts['p'].new_tensor(mapping.scale))


def regression(x, y, scale):
    return F.smooth_l1_loss((x-y) / scale, torch.zeros_like(x))


def physical_loss(model, b):
    state = model.initial(b['history'], b['previous_history'], b['vision'][:, 0])
    loss = regression(state.obj, b['o'][:, 0], model.o_scale)
    loss = loss + .15 * F.binary_cross_entropy_with_logits(
        state.contact_logits, b['prev_contact'][:, 0])
    physical, vision, contact, labels = [], [], [], []
    horizon = b['p'].shape[1] - 1
    for step in range(horizon):
        state = model.step(state, b['a'][:, step], b['prev'][:, step])
        physical.append(model.sensor(state))
        labels.append(state.obj)
        vision.append(state.vision)
        contact.append(state.contact_logits)
    sensor, objects, images, logits = (torch.stack(x, 1) for x in (physical, labels, vision, contact))
    p = b['p'][:, 1:]
    # Separate geometry/rate/IMU blocks so high-dimensional encoders cannot
    # suppress metric rod, passive hinge or comparatively rare finger events.
    loss = loss + regression(sensor[..., :23], p[..., :23], .25 * model.p_scale[:23])
    loss = loss + .6 * regression(sensor[..., 23:46], p[..., 23:46], model.p_scale[23:46])
    loss = loss + .3 * regression(sensor[..., 46:], p[..., 46:], model.p_scale[46:])
    loss = loss + regression(objects, b['o'][:, 1:], model.o_scale)
    loss = loss + .3 * F.binary_cross_entropy_with_logits(logits, b['contact'][:, :-1])
    # Stored camera frames are sample-and-hold. An exposure supplies one target.
    valid = b['fresh'][:, 1:].float()
    visual_error = F.smooth_l1_loss((images - b['vision'][:, 1:]) / model.v_scale,
                                    torch.zeros_like(images), reduction='none').mean(-1)
    return loss + (valid * visual_error).sum() / valid.sum().clamp_min(1.)


@torch.no_grad()
def evaluate(model, replay, device, samples=768):
    result = {}
    model.eval()
    for h in (1, 7, 32):
        pool, _ = replay.starts(h)
        # Fixed equal-spaced windows sample the entire validation set without balancing by contact.
        indices = torch.linspace(0, len(pool)-1, min(samples, len(pool)), device=device).long()
        measured = []
        for ids in indices.split(96):
            b = replay.window(pool[ids], h)
            st = model.initial(b['history'], b['previous_history'], b['vision'][:, 0])
            for k in range(h):
                st = model.step(st, b['a'][:, k], b['prev'][:, k])
            p = model.sensor(st)
            load = b['contact'][:, h-1, :2]
            dual = b['contact'][:, h-1, 2]
            pred = st.contact_logits[:, :2].sigmoid()
            obj, pa = b['o'][:, h], b['p'][:, h]
            cols = [
                (st.obj[:, 0] - obj[:, 0]).abs().rad2deg(),
                (st.obj[:, 1] - obj[:, 1]).abs(),
                1000*(st.obj[:, 2:] - obj[:, 2:]).norm(dim=-1),
                (p[:, :12] - pa[:, :12]).abs().mean(-1),
                (p[:, 35:39] - pa[:, 35:39]).abs().mean(-1),
                (p[:, 16:22] - pa[:, 16:22]).abs().mean(-1).rad2deg(),
                1000*(p[:, 22]-pa[:, 22]).abs(),
                (st.vision-b['vision'][:, -1]).square().mean(-1).sqrt(),
                (b['vision'][:, 0]-b['vision'][:, -1]).square().mean(-1).sqrt(),
                (pred-load).square().mean(-1),
                ((pred > .5) == load.bool()).float().mean(-1),
                (st.contact_logits[:, 2].sigmoid()-dual).abs(),
            ]
            measured.append(torch.stack((load.sum(-1), dual, *cols), -1).cpu())
        vals = torch.cat(measured)
        metrics = ('angle_mae_deg', 'hinge_rate_mae_rad_s', 'rod_err_mm', 'leg_mae_rad',
                   'wheel_rate_mae_rad_s', 'arm_mae_deg', 'jaw_mae_mm',
                   'pooled_rgbd_rmse', 'held_image_rmse', 'finger_brier', 'finger_accuracy', 'dual_fraction_mae')
        modes = {'all': torch.ones(len(vals), dtype=torch.bool),
                 'neither_finger': vals[:, 0] == 0, 'one_finger': vals[:, 0] == 1,
                 'two_without_overlap': (vals[:, 0] == 2) & (vals[:, 1] == 0),
                 'simultaneous_contact': vals[:, 1] > 0}
        result[str(h)] = {mode: dict(n=int(mask.sum()),
                                     **(dict(zip(metrics, vals[mask, 2:].mean(0).tolist())) if mask.any() else {}))
                          for mode, mask in modes.items()}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--steps', type=int, required=True, help='Absolute optimizer update endpoint')
    ap.add_argument('--resume', type=Path)
    ap.add_argument('--probe', action='store_true', help='Measure a discarded fit on real transitions')
    ap.add_argument('--only', action='append', help='Restrict to named training episodes for the representative probe')
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--batch', type=int, default=128)
    ap.add_argument('--horizon', type=int, default=7)
    ap.add_argument('--seed', type=int, default=7041)
    ap.add_argument('--width', type=int, default=192)
    ap.add_argument('--lr', type=float, default=.001)
    ap.add_argument('--evaluate', action='store_true')
    ap.add_argument('--validation-samples', type=int, default=768)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    device = torch.device(args.device)
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision('high')
    torch.manual_seed(args.seed)
    replay = PhysicalReplay(args.data, 'train', device, only=args.only)
    rng = torch.Generator(device=device).manual_seed(args.seed + 1)
    model = PerceptualDynamics(args.width).to(device)
    fit_units(model, replay)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    start = 0
    if args.resume:
        source = torch.load(args.resume, map_location=device, weights_only=False)
        if source['width'] != args.width or source['method'] != 'MM01-GenCoord-RGBD':
            raise ValueError('Incompatible continuation checkpoint')
        model.load_state_dict(source['model'])
        opt.load_state_dict(source['optimizer'])
        rng.set_state(source['sampler_rng'].cpu())
        start = source['updates']
    if args.steps < start or (args.steps == start and not args.evaluate):
        raise ValueError('No requested updates or validation')
    if device.type == 'cuda':
        torch.cuda.reset_peak_memory_stats(device)
    begin = clock(device)
    train_log = []
    losses = []
    frequency = min(100, max(1, (args.steps-start)//4))
    for i in range(start+1, args.steps+1):
        pos = replay.draw_starts(args.horizon, args.batch, rng, True)
        b = replay.window(pos, args.horizon)
        opt.zero_grad(set_to_none=True)
        loss = physical_loss(model, b)
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
        opt.step()
        losses.append(loss.detach())
        if i == args.steps or i % frequency == 0 or i == start+1:
            row = dict(update=i, mean_loss=float(torch.stack(losses).mean()),
                       preclip_grad_norm=float(norm), elapsed_s=clock(device)-begin)
            losses.clear()
            train_log.append(row)
            print(json.dumps(row), flush=True)
            if not args.probe:
                save_checkpoint(args.out / 'wm.pt', dict(
                    method='MM01-GenCoord-RGBD', width=args.width, model=model.state_dict(),
                    optimizer=opt.state_dict(), sampler_rng=rng.get_state(), updates=i,
                    episodes=replay.summary(), settings={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()}))
    elapsed = clock(device)-begin
    starts, contacts = replay.starts(args.horizon)
    summary = dict(episodes=replay.summary(), train_window_count=len(starts), contact_window_pool=len(contacts),
                   seed=args.seed, horizon=args.horizon, batch=args.batch,
                   initial_updates=start, final_updates=args.steps, retained_updates=0 if args.probe else args.steps-start,
                   discarded_probe_updates=args.steps-start if args.probe else 0,
                   learning_rate=args.lr, width=args.width, train_wall_s=elapsed,
                   optimizer_steps_per_s=(args.steps-start)/max(elapsed,1e-8),
                   peak_allocated_MiB=peak_mb(device), physical_samples=(args.steps-start)*args.batch*args.horizon,
                   loss_trace=train_log, torch_version=torch.__version__, cuda=torch.version.cuda,
                   units='50 Hz policy, 10 physical substeps, GenCoord semi-implicit coefficient 0.55',
                   window_sampling='2/3 uniform legal starts and 1/3 positive finger interval start when available')
    if args.evaluate:
        val = PhysicalReplay(args.data, 'validation', device)
        summary['validation_episodes'] = val.summary()
        summary['validation_by_horizon'] = evaluate(model, val, device, args.validation_samples)
    write_json(args.out / ('wm_probe.json' if args.probe else 'wm_training.json'), summary)


if __name__ == '__main__':
    main()
