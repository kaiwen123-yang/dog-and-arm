"""Continue physical dynamics, bind one encoder and score the two prediction modes for MM-02."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from learning.multimodal.actor import load_actor
from learning.multimodal.mm02_trajectory import (
    closed_prediction, encoder_id, frozen_dynamics, open_prediction, starting_observations)
from learning.multimodal.wm_replay import PhysicalReplay
from learning.multimodal.world_model import HORIZON, PerceptualDynamics, VisualBridge, camera_features
from scripts.multimodal.train_wm import clock, peak_mb, physical_loss, save_checkpoint, write_json


TRAIN_SCENES = {'tr_nominal', 'tr_offset', 'tr_load'}
SCHEMA = 'mm02_actual_action_h7_v1'


def metadata(path):
    return json.loads((Path(path)/'metadata.json').read_text())


def training_members(membership, parent):
    original = [Path(path) for path in membership['old_train']]
    if parent.get('schema') == SCHEMA:
        inherited = [Path(path) for path in parent['mm01_physical_episodes']]
    else:
        if parent.get('method') != 'MM01-GenCoord-RGBD' or parent['updates'] != 2800:
            raise ValueError('Expected full 2,800-update MM-01 world-model/optimizer checkpoint')
        by_id = {metadata(path)['episode_id']: path for path in original}
        data_root = original[0].parent
        inherited = [by_id.get(item['episode_id'], data_root/item['episode_id']) for item in parent['episodes']]
        if not set(original).issubset(set(inherited)):
            raise ValueError('The original demo set differs from the restored WM members')
    additions = [Path(path) for path in membership['new_train'] + membership['cumulative_train_recovery']]
    members = inherited + additions
    ids = set()
    for path in members:
        m = metadata(path)
        if m['split'] != 'train' or m['scene_id'] not in TRAIN_SCENES or m['episode_id'] in ids:
            raise ValueError(f'{path}: duplicate identity or invalid training scene')
        ids.add(m['episode_id'])
    return list(map(str, members)), list(map(str, inherited))


def restore_rng(state, device):
    torch.set_rng_state(state['torch_cpu_rng'].cpu())
    if device.type == 'cuda':
        torch.cuda.set_rng_state(state['torch_device_rng'].cpu(), device)


def global_rng(device):
    return {'torch_cpu_rng': torch.get_rng_state(),
            'torch_device_rng': torch.cuda.get_rng_state(device) if device.type == 'cuda' else None}


def applied_count(journal):
    if not journal.exists():
        return 0
    with journal.open() as stream:
        return sum(1 for _ in stream)


def mark_applied(journal, step):
    with journal.open('a') as stream:
        stream.write(f'{step}\n')


@torch.no_grad()
def saturation(model, replay, inherited_count):
    cutoff = replay.episodes[inherited_count]['start'] if len(replay.episodes)>inherited_count else len(replay.base)
    answer = {}
    for name, rows in {'inherited': slice(0, cutoff), 'mm02': slice(cutoff, None)}.items():
        if not len(replay.base[rows]):
            continue
        p, o, v = [replay.parts[key][rows] for key in ('p', 'o', 'vision')]
        fresh = replay.parts['fresh'][rows]
        v = v[fresh]
        result = {'states': len(p), 'real_exposure_states': len(v)}
        for key, x, mean, scale, limit in (('proprio', p, model.p_mean, model.p_scale, 12),
                ('object', o, model.o_mean, model.o_scale, 12), ('vision', v, model.v_mean, model.v_scale, 10)):
            mask = ((x-mean)/scale).abs() > limit
            result[key] = {'limit': limit, 'values': mask.numel(), 'beyond': int(mask.sum()),
                           'fraction': float(mask.float().mean()) if mask.numel() else None}
        answer[name] = result
    return answer


def wm(args, membership, device):
    parent = torch.load(args.parent, map_location=device, weights_only=False)
    members, inherited = training_members(membership, parent)
    if args.round != parent.get('round', 0)+1:
        raise ValueError('Expected a consecutive physical-model parent')
    if (args.out/'wm_training.json').exists():
        raise FileExistsError(args.out/'wm_training.json')
    replay = PhysicalReplay(None, 'train', device, episode_dirs=members)
    model = PerceptualDynamics(parent['width']).to(device)
    model.load_state_dict(parent['model'])
    fixed_units = {k: b.clone() for k, b in model.named_buffers() if k.endswith(('_mean', '_scale', '_offset'))}
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=1e-4)
    optimizer.load_state_dict(parent['optimizer'])
    for group in optimizer.param_groups:
        group['lr'] = .001
    rng = torch.Generator(device=device).manual_seed(47020+args.round)
    epoch, previous_elapsed, records = 0, 0., []
    checkpoint = args.out/'wm.pt'
    if checkpoint.exists():
        saved = torch.load(checkpoint, map_location=device, weights_only=False)
        if saved['members'] != members or saved['parent'] != str(args.parent) or saved['round'] != args.round:
            raise ValueError('WM resume parent or data membership changed')
        model.load_state_dict(saved['model'])
        optimizer.load_state_dict(saved['optimizer'])
        rng.set_state(saved['sampler_rng'].cpu())
        restore_rng(saved, device)
        epoch, previous_elapsed, records = saved['round_updates'], saved['train_wall_s'], saved['records']
    all_starts, contact = replay.starts(7)
    journal = args.out/'wm_applied_steps.txt'
    rollback = applied_count(journal)-epoch
    if not 0 <= rollback <= 200:
        raise ValueError('WM update ledger does not match the recovery point or remaining reserve')
    start = clock(device)
    for step in range(epoch+1, 1001):
        batch = replay.window(replay.draw_starts(7, 128, rng, True), 7)
        optimizer.zero_grad(set_to_none=True)
        loss = physical_loss(model, batch)
        loss.backward()
        grad = torch.nn.utils.clip_grad_norm_(model.parameters(), 5., error_if_nonfinite=True)
        optimizer.step()
        mark_applied(journal, step)
        if step == 1 or step % 25 == 0:
            elapsed = previous_elapsed+clock(device)-start
            records.append({'update': step, 'batch_loss': float(loss.detach()), 'preclip_grad_norm': float(grad),
                            'train_wall_s': elapsed})
            save_checkpoint(checkpoint, dict(schema=SCHEMA, parent=str(args.parent), width=model.width,
                round=args.round, round_updates=step, updates=parent['updates']+step,
                model=model.state_dict(), optimizer=optimizer.state_dict(), sampler_rng=rng.get_state(),
                members=members, mm01_physical_episodes=inherited, train_wall_s=elapsed, records=records,
                horizon=7, batch=128, learning_rate=.001, **global_rng(device)))
            if step == 1 or step % 100 == 0:
                print(json.dumps(records[-1]), flush=True)
    if any(not torch.equal(fixed_units[k], b) for k, b in model.named_buffers() if k in fixed_units):
        raise ValueError('Physical normalization units changed during continuation')
    summary = {'round': args.round, 'parent': str(args.parent), 'checkpoint': str(checkpoint),
        'initial_cumulative_updates': parent['updates'], 'round_retained_updates': 1000,
        'round_applied_updates': applied_count(journal), 'round_rollback_updates': rollback,
        'final_cumulative_updates': parent['updates']+1000, 'sampler_seed': 47020+args.round,
        'horizon': 7, 'batch': 128, 'learning_rate': .001, 'critic_updates': 0,
        'episodes': replay.summary(), 'fixed_units_restored': list(fixed_units),
        'legal_windows': len(all_starts), 'contact_start_windows': len(contact),
        'action_source': 'mm01 action_clipped; mm02 executed_action_clipped, checked against previous_action[1:]',
        'early_history': 'real nine-observation branch prefix; frame0 padding only on reset',
        'inherited_mm01_physical_episodes': inherited, 'normalization_coverage': saturation(model, replay, len(inherited)),
        'train_wall_s': records[-1]['train_wall_s'], 'peak_allocated_MiB': peak_mb(device), 'log': records}
    write_json(args.out/'wm_training.json', summary)


@torch.no_grad()
def exposures(actor, members, device):
    compact, encoded = [], []
    for directory in members:
        path = Path(directory)
        m = metadata(path)
        # The anchor's held exposure is a copy of an observation in the parent trajectory.
        # Only post-branch exposures add new camera training pairs.
        image_t = np.load(path/'image_t.npy', mmap_mode='r')
        start = float(np.load(path/'t.npy', mmap_mode='r')[0])
        first = (np.searchsorted(image_t, start+1e-7, side='right') if m.get('anchor_tick') is not None
                 and m.get('parent_episode') is not None else 0)
        rgb, dep, mask = [np.load(path/(k+'.npy'), mmap_mode='r') for k in ('rgb','depth','depth_valid')]
        for offset in range(first, len(image_t), 128):
            inputs = [torch.tensor(np.asarray(x[offset:offset+128]), device=device) for x in (rgb, dep, mask)]
            compact.append(camera_features(*inputs))
            encoded.append(actor.encode_visual(*inputs))
    if not compact:
        raise ValueError('No actual camera exposures in the selected members')
    return torch.cat(compact), torch.cat(encoded)


@torch.no_grad()
def bridge_errors(model, bridge, x, y):
    residuals = []
    for start in range(0, len(x), 1024):
        sl = slice(start, start+1024)
        residuals.append((bridge(model.v_units(x[sl]))-y[sl]).square().mean(-1))
    return {'exposures': len(x), 'rmse': float(torch.cat(residuals).mean().sqrt()),
            'held_mean_rmse': float((y-bridge.mean).square().mean().sqrt())}


def bridge_phase(args, membership, device):
    saved_wm = torch.load(args.parent, map_location=device, weights_only=False)
    if saved_wm['schema'] != SCHEMA or saved_wm['round'] != args.round or saved_wm['round_updates'] != 1000:
        raise ValueError('Bind only the completed physical-model round')
    if (args.out/'bridge_training.json').exists():
        raise FileExistsError(args.out/'bridge_training.json')
    actor, vocab, policy = load_actor(args.actor, device)
    if (policy['configuration'].get('stage') != 'bc' or policy['configuration'].get('branch') != 'model_trajectory'
            or policy['update'] != 2048 or policy['configuration'].get('round') != args.round):
        raise ValueError('The bridge must bind the current model branch after its 2,048 BC updates')
    actor.eval().requires_grad_(False)
    encoder = encoder_id(actor)
    model = PerceptualDynamics(saved_wm['width']).to(device)
    model.load_state_dict(saved_wm['model'])
    model.eval().requires_grad_(False)
    members, inherited = training_members(membership, saved_wm)
    if members != saved_wm['members']:
        raise ValueError('Current WM and visual transfer data do not match')
    x, y = exposures(actor, members, device)
    torch.manual_seed(57020+args.round)
    bridge = VisualBridge(y.shape[-1]).to(device)
    bridge.mean.copy_(y.mean(0))
    bridge.scale.copy_(y.std(0, correction=0).clamp_min(.02))
    optimizer = torch.optim.AdamW(bridge.parameters(), lr=.001)
    rng = torch.Generator(device=device).manual_seed(57020+args.round)
    checkpoint = args.out/'trajectory_bundle.pt'
    epoch, previous_elapsed, records = 0, 0., []
    if checkpoint.exists():
        saved = torch.load(checkpoint, map_location=device, weights_only=False)
        if (saved['encoder_id'] != encoder or saved['wm_path'] != str(args.parent)
                or saved['train_recovery'] != membership['train_recovery'] or saved['round'] != args.round):
            raise ValueError('Bridge parent, encoder or recovery members changed at resume')
        bridge.load_state_dict(saved['bridge'])
        optimizer.load_state_dict(saved['bridge_optimizer'])
        rng.set_state(saved['bridge_rng'].cpu())
        restore_rng(saved, device)
        epoch, previous_elapsed, records = saved['bridge_updates'], saved['train_wall_s'], saved['records']
    cfg = {'horizon': HORIZON, 'imagination_batch': 32, 'discount': .985, 'weight': .15,
           'camera_period_ticks': 5}
    journal = args.out/'bridge_applied_steps.txt'
    rollback = applied_count(journal)-epoch
    if not 0 <= rollback <= 120:
        raise ValueError('Bridge update ledger does not match the recovery point or remaining reserve')
    start = clock(device)
    for step in range(epoch+1, 601):
        ix = torch.randint(len(x), (256,), generator=rng, device=device)
        error = (bridge(model.v_units(x[ix]))-y[ix]) / bridge.scale
        loss = F.smooth_l1_loss(error, torch.zeros_like(error))
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        if not torch.isfinite(loss):
            raise FloatingPointError(f'Bridge nonfinite loss at update {step}')
        optimizer.step()
        mark_applied(journal, step)
        if step == 1 or step % 25 == 0:
            elapsed = previous_elapsed+clock(device)-start
            records.append({'update': step, 'batch_loss': float(loss.detach()), 'train_wall_s': elapsed})
            save_checkpoint(checkpoint, dict(schema='mm02_bound_trajectory_v1', round=args.round,
                width=model.width, actor_visual_dim=y.shape[-1], model=model.state_dict(),
                bridge=bridge.state_dict(), bridge_optimizer=optimizer.state_dict(),
                bridge_rng=rng.get_state(), bridge_updates=step, encoder_id=encoder,
                actor_path=str(args.actor), wm_path=str(args.parent), wm_updates=saved_wm['updates'],
                vocabulary=vocab.tokens,
                members=members, train_recovery=membership['train_recovery'], objective=cfg,
                records=records, train_wall_s=elapsed, **global_rng(device)))
    errors = {'train': bridge_errors(model, bridge, x, y)}
    for name in ('validation_demo', 'validation_onpolicy', 'validation_recovery'):
        paths = membership.get(name, [])
        if paths:
            if any(metadata(p)['split'] != 'validation' for p in paths):
                raise ValueError('Wrong held-out split for visual validation')
            # Some legal short prefixes contain no new post-anchor exposure.
            try:
                x_val, y_val = exposures(actor, paths, device)
            except ValueError as exc:
                if str(exc) != 'No actual camera exposures in the selected members':
                    raise
                errors[name] = {'exposures': 0}
            else:
                errors[name] = bridge_errors(model, bridge, x_val, y_val)
    write_json(args.out/'bridge_training.json', {'round': args.round, 'parent_wm': str(args.parent),
        'actor_after_2048_bc': str(args.actor), 'encoder_id': encoder, 'bundle': str(checkpoint),
        'initialization': 'fresh bridge per updated frozen encoder, normalized from actual training exposures',
        'training_members': members, 'old_physical_sources': inherited, 'seed': 57020+args.round,
        'bridge_retained_updates': 600, 'bridge_applied_updates': applied_count(journal),
        'bridge_rollback_updates': rollback, 'batch': 256, 'objective': cfg, 'learning_rate': .001,
        'peak_allocated_MiB': peak_mb(device), 'train_wall_s': records[-1]['train_wall_s'], 'errors': errors})


def legal_sample(replay, h, anchors):
    groups = []
    for episode in replay.episodes:
        ok = episode['valid']
        if len(ok)<h:
            continue
        legal = np.flatnonzero(np.lib.stride_tricks.sliding_window_view(ok, h).all(-1))
        if anchors:
            sample = legal[:1] if len(legal) and legal[0] == 0 else []
        else:
            count = min(len(legal), max(1, 384//len(replay.episodes)))
            sample = legal[np.linspace(0, len(legal)-1, count, dtype=int)] if count else []
        groups.extend(episode['start']+int(i) for i in sample)
    return torch.tensor(groups, device=replay.device, dtype=torch.long)


@torch.no_grad()
def prediction_metrics(pred, targets, h):
    dp = (pred['p'][:, -1] - targets['p'][:, h]).abs()
    delta = pred['o'][:, -1] - targets['o'][:, h]
    c = (pred['contact'][:, -1].sigmoid() - targets['contact'][:, h-1]).square()
    physical = torch.stack((delta[:, 0].abs().rad2deg(), delta[:, 1].abs(), 1000*delta[:, 2:].norm(dim=-1),
        dp[:, :12].mean(-1), dp[:, 35:39].mean(-1), dp[:, 16:22].mean(-1).rad2deg(),
        1000*dp[:, 22], c[:, :2].mean(-1), c[:, 2]), -1)
    fresh = targets['fresh'][:, 1:h+1]
    truth = targets['vision'][:, 1:h+1]
    visual = (pred['vision']-truth).square().mean(-1)
    hold = (targets['vision'][:, :1]-truth).square().mean(-1)
    return (physical.cpu(), torch.stack((visual[fresh].sum(), hold[fresh].sum(), fresh.sum(),
            visual[:, -1][fresh[:, -1]].sum(), hold[:, -1][fresh[:, -1]].sum(), fresh[:, -1].sum())).double().cpu())


def restored_targets(directories):
    """Compare saved recovery start, history and held image against the actual parent decision."""
    def arr(path, name):
        return np.load(path/(name+'.npy'), mmap_mode='r', allow_pickle=False)
    keys, worst, phases = set(), {}, Counter()
    complete, steps, repetitions, bad_source, bad_image, illegal_parent = 0, 0, 0, 0, 0, 0
    exposure_counts = Counter()
    for directory in directories:
        branch = Path(directory)
        m = metadata(branch)
        parent, tick = Path(m['parent_path']), int(m['anchor_tick'])
        key = m['anchor_key']
        repetitions += key in keys
        keys.add(key)
        phases[m['anchor_phase']] += 1
        history = np.maximum(0, np.arange(tick-9, tick))
        for name, actual in [('proprio', arr(parent,'proprio')[tick]), ('previous_action', arr(parent,'previous_action')[tick]),
                ('object_state', arr(parent,'object_state')[tick]), ('qpos', arr(parent,'qpos')[tick]),
                ('qvel', arr(parent,'qvel')[tick]), ('t', arr(parent,'t')[tick]),
                ('history_prefix_proprio', arr(parent,'proprio')[history]),
                ('history_prefix_previous_action', arr(parent,'previous_action')[history]),
                ('history_prefix_contact', np.r_[arr(parent,'contact')[tick-1]>.01,
                                                   arr(parent,'both_contact_fraction')[tick-1]])]:
            stored = arr(branch, name)
            value = stored if name.startswith('history_prefix') else stored[0]
            worst[name] = max(worst.get(name, 0.), float(np.max(np.abs(value-actual))))
        pidx, bidx = int(arr(parent,'image_index')[tick]), int(arr(branch,'image_index')[0])
        if pidx >= 0 and bidx >= 0:
            equal = all(np.array_equal(arr(parent, k)[pidx], arr(branch, k)[bidx])
                        for k in ('image_t','rgb','depth','depth_valid'))
            bad_image += not equal
        else:
            bad_image += pidx != bidx
        illegal_parent += not np.any(arr(parent,'execution_source')[:tick] == 0)
        bad_source += int(np.count_nonzero(arr(branch,'execution_source') != 1))
        valid = arr(branch, 'valid_transition')
        if len(valid) == HORIZON and valid.all():
            complete += 1
            t, times, ix = (arr(branch,k) for k in ('t','image_t','image_index'))
            exposure_counts[int(np.isclose(t[1:], times[ix[1:]], atol=1e-6, rtol=0).sum())] += 1
        steps += int(arr(branch,'substeps').sum())
    return {'branches': len(directories), 'unique_anchor_snapshots': len(keys), 'complete_h32': complete,
            'incomplete_kept_prefixes': len(directories)-complete, 'duplicate_anchor_snapshots': repetitions,
            'actual_physics_substeps': steps, 'anchor_stages': phases, 'actual_exposures_per_complete_h32': exposure_counts,
            'parent_start_and_history_max_abs_error': worst, 'held_image_or_exposure_mismatches': bad_image,
            'source_states_without_prior_student_action': illegal_parent, 'non_teacher_intervals': bad_source}


@torch.no_grad()
def validation(args, membership, device):
    package = torch.load(args.parent, map_location=device, weights_only=False)
    model, bridge = frozen_dynamics(package, device)
    actor, vocab, _ = load_actor(args.actor, device)
    if package['encoder_id'] != encoder_id(actor) or package['bridge_updates'] != 600:
        raise ValueError('Held-out rollout uses a different image/text encoder or unfinished bridge')
    out = {}
    metric_names = ['angle_mae_deg', 'hinge_rate_mae_rad_s', 'handle_error_mm', 'leg_mae_rad',
                    'wheel_rate_mae_rad_s', 'arm_mae_deg', 'jaw_mae_mm', 'finger_brier', 'dual_fraction_mse']
    for group in ('validation_onpolicy', 'validation_recovery', 'validation_demo'):
        paths = membership[group]
        if not paths:
            out[group] = {'episodes': [], 'horizons': {}}
            continue
        if any(metadata(p)['scene_id'] != 'va_pose' for p in paths):
            raise ValueError('Only va_pose is allowed for dynamics development validation')
        replay = PhysicalReplay(None, 'validation', device, episode_dirs=paths)
        out[group] = {'episodes': replay.summary(), 'horizons': {}}
        for h in (1,7,32):
            starts = legal_sample(replay, h, group=='validation_recovery')
            records = {name: [] for name in ('recorded_action_open_loop', 'student_imagined_closed_loop')}
            for rows in starts.split(96):
                if not len(rows):
                    continue
                b = replay.window(rows, h)
                obs = starting_observations(actor, vocab, replay, rows, b)
                predictions = (open_prediction(model, b, h), closed_prediction(actor, model, bridge, obs, h))
                for name, pred in zip(records, predictions):
                    records[name].append(prediction_metrics(pred, b, h))
            report = {'windows': len(starts)}
            for name, packets in records.items():
                if packets:
                    means = torch.cat([p for p, _ in packets]).mean(0).tolist()
                    v, hold, n, ve, he, ne = torch.stack([s for _, s in packets]).sum(0).tolist()
                    report[name] = {**dict(zip(metric_names, means)),
                        'exposures_in_windows': int(n), 'vision_rmse_at_exposures': (v/n)**.5 if n else None,
                        'held_start_rmse_same_exposures': (hold/n)**.5 if n else None,
                        'fresh_endpoints': int(ne), 'vision_rmse_fresh_endpoint': (ve/ne)**.5 if ne else None,
                        'held_start_rmse_same_endpoint': (he/ne)**.5 if ne else None}
            out[group]['horizons'][h] = report
    write_json(args.out/'wm_validation.json', {'round': args.round, 'bundle': str(args.parent),
        'frozen_evaluated_actor': str(args.actor), 'fit_on_validation': False,
        'open_loop': 'actual student commands for on-policy validation, physical teacher commands for recovery/demo',
        'closed_loop': 'student re-queried on predicted state, measured start sensors only; scored against recorded physical successors',
        'camera_baseline': 'same starting exposure held across each window; identical actual exposure times',
        'recovery_provenance': {group: restored_targets(membership[group])
                                for group in ('train_recovery', 'validation_recovery')}, 'strata': out})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['wm', 'bridge', 'validate'])
    parser.add_argument('--membership', type=Path, required=True)
    parser.add_argument('--parent', type=Path, required=True)
    parser.add_argument('--actor', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--round', type=int, required=True)
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    if args.stage != 'wm' and args.actor is None:
        parser.error('An actor checkpoint is needed for bridge binding or closed-loop validation')
    args.out.mkdir(exist_ok=True, parents=True)
    membership = json.loads(args.membership.read_text())
    device = torch.device(args.device)
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision('high')
    if device.type == 'cuda':
        torch.cuda.set_device(device if device.index is not None else 0)
        torch.cuda.reset_peak_memory_stats(device)
    {'wm': wm, 'bridge': bridge_phase, 'validate': validation}[args.stage](args, membership, device)


if __name__ == '__main__':
    main()
