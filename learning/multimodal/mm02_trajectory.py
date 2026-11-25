"""Differentiable student rollouts supervised by a real, separately restored teacher trajectory."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from .actor import POLICY_DT
from .wm_replay import PhysicalReplay
from .world_model import HORIZON, PHOTO_PERIOD_TICKS, PerceptualDynamics, VisualBridge


GROUP_WEIGHTS = {'position': 1., 'velocity': .6, 'imu': .3, 'object': 1.,
                 'contact': .3, 'vision': 1.}
ENCODERS = ('rgb_encoder.', 'depth_encoder.', 'visual_projection.', 'embedding.',
            'token_weight.', 'text_projection.')


def encoder_id(actor):
    digest = hashlib.sha256()
    for name, tensor in sorted(actor.state_dict().items()):
        if name.startswith(ENCODERS) or name == 'numeric_tokens':
            digest.update(name.encode())
            digest.update(tensor.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def frozen_dynamics(package, device):
    model = PerceptualDynamics(package['width']).to(device)
    model.load_state_dict(package['model'])
    bridge = VisualBridge(package['actor_visual_dim']).to(device)
    bridge.load_state_dict(package['bridge'])
    return model.eval().requires_grad_(False), bridge.eval().requires_grad_(False)


@torch.no_grad()
def starting_observations(actor, vocab, replay, starts, batch):
    """Read only observations available by each actual start, including its true camera age."""
    starts_np = starts.detach().cpu().numpy()
    device = replay.device
    encoded = torch.empty(len(starts), actor.visual_projection[-2].out_features, device=device)
    sensors = torch.empty(len(starts), 3, device=device)
    text_ids = []
    for ep in replay.episodes:
        meta = ep['meta']
        text_ids.append(vocab.encode(meta['task_text']))
        matches = np.flatnonzero((starts_np >= ep['start']) & (starts_np <= ep['start']+ep['count']))
        if not len(matches):
            continue
        def array(name):
            return np.load(ep['path'] / (name + '.npy'), mmap_mode='r', allow_pickle=False)
        t, image_t, image_index = array('t'), array('image_t'), array('image_index')
        rgb, depth, mask = array('rgb'), array('depth'), array('depth_valid')
        for rows in np.array_split(matches, max(1, math.ceil(len(matches)/128))):
            ticks = starts_np[rows] - ep['start']
            idx = image_index[ticks].astype(int)
            valid = idx >= 0
            elapsed = t[ticks]
            age = np.zeros(len(idx), np.float32)
            age[valid] = elapsed[valid] - image_t[idx[valid]]
            which = torch.as_tensor(rows, device=device)
            sensors[which] = torch.as_tensor(np.stack((age, valid, elapsed), -1),
                                              dtype=torch.float32, device=device)
            encoded[which] = 0.
            if valid.any():
                # Use the exact same visible exposure as the deployed student; no future RGB-D.
                image_args = [torch.tensor(np.asarray(x[idx[valid]]), device=device)
                              for x in (rgb, depth, mask)]
                encoded[which[torch.as_tensor(valid, device=device)]] = actor.encode_visual(*image_args)
    episode_tokens = torch.tensor(text_ids, device=device)
    text = actor.encode_text(episode_tokens)[replay.episode_index[starts]]
    return {'history': batch['history'], 'previous': batch['previous_history'],
            'low': batch['vision'][:, 0], 'measured': encoded, 'text': text, 'sensor': sensors}


def collect_states(model, states):
    return {'p': torch.stack([model.sensor(s) for s in states], 1),
            'o': torch.stack([s.obj for s in states], 1),
            'vision': torch.stack([s.vision for s in states], 1),
            'contact': torch.stack([s.contact_logits for s in states], 1)}


def closed_prediction(actor, model, bridge, obs, horizon):
    """Prediction receives only the start sensors. Future teacher data are outside this function."""
    hist, previous, sensor = obs['history'], obs['previous'], obs['sensor']
    low, measured, text = obs['low'], obs['measured'], obs['text']
    state = model.initial(hist, previous, low)
    bridge_start = bridge(model.v_units(low))
    visual = measured
    age = torch.where(sensor[:, 1].bool(), sensor[:, 0], sensor[:, 2])
    age_ticks = (age / POLICY_DT).round().long() % PHOTO_PERIOD_TICKS
    states = []
    for _ in range(horizon):
        action = actor.act_features(visual, text, hist, previous, sensor)
        state = model.step(state, action, previous[:, -1])
        states.append(state)
        hist = torch.cat((hist[:, 1:], model.sensor(state)[:, None]), 1)
        previous = torch.cat((previous[:, 1:], action[:, None]), 1)
        age_ticks = (age_ticks + 1) % PHOTO_PERIOD_TICKS
        fresh = (age_ticks == 0)[:, None]
        estimated = measured + bridge(model.v_units(state.vision)) - bridge_start
        visual = torch.where(fresh, estimated, visual)
        valid = torch.where(fresh, 1., sensor[:, 1:2])
        sensor = torch.cat((valid * age_ticks[:, None] * POLICY_DT,
                            valid, sensor[:, 2:3] + POLICY_DT), 1)
    return collect_states(model, states)


def open_prediction(model, batch, horizon):
    state = model.initial(batch['history'], batch['previous_history'], batch['vision'][:, 0])
    states = []
    for step in range(horizon):
        state = model.step(state, batch['a'][:, step], batch['prev'][:, step])
        states.append(state)
    return collect_states(model, states)


def trajectory_terms(model, prediction, target, discount=.985):
    h = prediction['p'].shape[1]
    p, o, vision = (target[name][:, 1:h+1] for name in ('p', 'o', 'vision'))
    def huber(x, y, scale):
        residual = (x - y) / scale
        return F.smooth_l1_loss(residual, torch.zeros_like(residual), reduction='none').mean(-1)
    terms = {
        'position': huber(prediction['p'][..., :23], p[..., :23], .25*model.p_scale[:23]),
        'velocity': huber(prediction['p'][..., 23:46], p[..., 23:46], model.p_scale[23:46]),
        'imu': huber(prediction['p'][..., 46:], p[..., 46:], model.p_scale[46:]),
        'object': huber(prediction['o'], o, model.o_scale),
        'contact': F.binary_cross_entropy_with_logits(prediction['contact'], target['contact'][:, :h],
                                                       reduction='none').mean(-1)}
    weights = prediction['p'].new_tensor([discount**k for k in range(h)])
    result = {key: ((values * weights).sum(-1) / weights.sum()).mean() for key, values in terms.items()}
    fresh = target['fresh'][:, 1:h+1]
    visual_error = huber(prediction['vision'], vision, model.v_scale)
    result['vision'] = (fresh * visual_error).sum() / fresh.sum().clamp_min(1)
    return result


class RecoveryObjective:
    """Uniform independent sampler over unique complete, current-round recovery anchors."""
    def __init__(self, bundle_path, device, vocab, seed):
        self.device, self.vocab = torch.device(device), vocab
        package = torch.load(bundle_path, map_location=self.device, weights_only=False)
        if package['schema'] != 'mm02_bound_trajectory_v1':
            raise ValueError('Expected a round-specific MM-02 WM/bridge binding')
        if package['bridge_updates'] != 600 or package['vocabulary'] != vocab.tokens:
            raise ValueError('Incomplete bridge or a different task-text vocabulary')
        self.model, self.bridge = frozen_dynamics(package, self.device)
        self.encoder = package['encoder_id']
        self.objective = package['objective']
        self.round = package['round']
        self.rng = torch.Generator(device=self.device).manual_seed(seed)
        self.drawn = 0
        self.anchor_keys, complete, seen = [], [], set()
        for directory in package['train_recovery']:
            path = Path(directory)
            meta = json.loads((path/'metadata.json').read_text())
            if meta['split'] != 'train' or meta['scene_id'] not in ('tr_nominal', 'tr_offset', 'tr_load'):
                raise ValueError(f'{directory}: non-training recovery supplied to H32')
            if meta['round'] != self.round or meta['source'] != 'recovery':
                raise ValueError(f'{directory}: only this round’s physical recovery is eligible')
            executed_by = np.load(path/'execution_source.npy', allow_pickle=False)
            if np.any(executed_by != 1):
                raise ValueError(f'{directory}: incomplete teacher control of recovery')
            key = (meta['parent_episode'], int(meta['anchor_tick']))
            if key in seen:
                raise ValueError(f'Duplicate teacher recovery anchor {key}')
            seen.add(key)
            valid = np.load(path/'valid_transition.npy', allow_pickle=False)
            is_complete = len(valid) == HORIZON and bool(valid.all())
            if is_complete != bool(meta['horizon_complete']):
                raise ValueError(f'{directory}: recovery completion conflicts with actual intervals')
            if is_complete:
                complete.append(path)
                self.anchor_keys.append(key)
        self.replay = (PhysicalReplay(None, 'train', self.device, episode_dirs=complete)
                       if complete else None)
        self.uses = torch.zeros(len(complete), dtype=torch.long, device=self.device)
        self.within_batch_repeats = torch.zeros((), dtype=torch.long, device=self.device)
        self.obs = None
        if self.replay:
            self.starts = torch.tensor([e['start'] for e in self.replay.episodes], device=self.device)
            self.targets = self.replay.window(self.starts, HORIZON)

    def __len__(self):
        return len(self.anchor_keys)

    def verify_actor(self, actor):
        if encoder_id(actor) != self.encoder:
            raise ValueError('Frozen bridge and active actor have different encoders')
        if any(p.requires_grad for name, p in actor.named_parameters() if name.startswith(ENCODERS)):
            raise ValueError('Freeze RGB-D and text encoders before the paired H32 block')
        if self.replay and self.obs is None:
            self.obs = starting_observations(actor, self.vocab, self.replay, self.starts, self.targets)

    def state_dict(self):
        return {'rng': self.rng.get_state(), 'drawn': self.drawn, 'round': self.round,
                'encoder': self.encoder, 'anchors': self.anchor_keys,
                'draws_per_anchor': self.uses.cpu(), 'within_batch_repeats': int(self.within_batch_repeats)}

    def sampling_summary(self):
        return {'complete_distinct_physical_anchors': len(self), 'training_batch_anchor_draws': self.drawn,
                'distinct_anchors_drawn': int((self.uses>0).sum()),
                'repeat_draws_within_batches': int(self.within_batch_repeats),
                'draws_min_max': [int(self.uses.min()), int(self.uses.max())] if len(self) else []}

    def load_state_dict(self, saved):
        if (saved['round'] != self.round or saved['encoder'] != self.encoder
                or saved['anchors'] != self.anchor_keys):
            raise ValueError('H32 anchor sampler identity differs at resume')
        self.rng.set_state(saved['rng'].cpu())
        self.drawn = saved['drawn']
        self.uses.copy_(saved['draws_per_anchor'])
        self.within_batch_repeats.fill_(saved['within_batch_repeats'])

    def sample(self):
        return torch.randint(len(self), (self.objective['imagination_batch'],),
                             device=self.device, generator=self.rng)

    def loss_for(self, actor, rows):
        if self.obs is None:
            self.verify_actor(actor)
        obs = {k: value[rows] for k, value in self.obs.items()}
        pred = closed_prediction(actor, self.model, self.bridge, obs, self.objective['horizon'])
        # Teacher actions, true future observations and judge states never enter closed_prediction.
        target = {k: self.targets[k][rows] for k in ('p', 'o', 'vision', 'contact', 'fresh')}
        terms = trajectory_terms(self.model, pred, target, self.objective['discount'])
        weighted = self.objective['weight'] * sum(GROUP_WEIGHTS[k]*v for k, v in terms.items())
        return weighted, terms

    def __call__(self, actor):
        rows = self.sample()
        loss, terms = self.loss_for(actor, rows)
        self.drawn += len(rows)
        self.uses.scatter_add_(0, rows, torch.ones_like(rows))
        ordered = rows.sort().values
        self.within_batch_repeats += (ordered[1:] == ordered[:-1]).sum()
        return loss, {'h32_'+k: v.detach() for k, v in terms.items()}

    @torch.enable_grad()
    def diagnose(self, actor):
        if not len(self):
            return {'complete_anchors': 0}
        saved_state = self.rng.get_state()
        rows = self.sample()
        self.rng.set_state(saved_state)
        loss, terms = self.loss_for(actor, rows)
        parameters = [p for p in actor.parameters() if p.requires_grad]
        group_norm = {}
        for name, value in terms.items():
            grads = torch.autograd.grad(value, parameters, retain_graph=True, allow_unused=True)
            group_norm[name] = float(torch.stack([g.detach().square().sum() for g in grads if g is not None]).sum().sqrt())
        report = {'complete_anchors': len(self), 'same_first_batch_indices': rows.cpu().tolist(),
                  'first_anchor_keys': [self.anchor_keys[i] for i in rows.cpu().tolist()],
                  'unweighted_group_losses': {k: float(v.detach()) for k, v in terms.items()},
                  'unweighted_group_actor_gradient_L2': group_norm, 'weight': self.objective['weight'],
                  'group_weights': GROUP_WEIGHTS, 'weighted_loss': float(loss.detach())}
        bias = actor.head[-1].bias
        grad, = torch.autograd.grad(loss, (bias,))
        report['weighted_action_bias_gradient_23'] = grad.cpu().tolist()
        # A single frozen-batch directional check in the first round, without optimizer updates.
        if self.round == 1:
            del loss, terms
            precision = torch.get_float32_matmul_precision()
            original = bias.detach().clone()
            try:
                torch.set_float32_matmul_precision('highest')
                base_loss = self.loss_for(actor, rows)[0]
                high_grad, = torch.autograd.grad(base_loss, (bias,))
                direction = high_grad.detach() / high_grad.detach().norm().clamp_min(1e-16)
                derivative = float(high_grad @ direction)
                differences = []
                with torch.no_grad():
                    for eps in (.008, .002, .0005):
                        bias.copy_(original + eps*direction)
                        plus = float(self.loss_for(actor, rows)[0])
                        bias.copy_(original - eps*direction)
                        minus = float(self.loss_for(actor, rows)[0])
                        differences.append({'epsilon': eps, 'centered': (plus-minus)/(2*eps)})
                report['frozen_directional_derivative'] = {'direction': 'final 23-channel output bias gradient',
                    'autograd': derivative, 'fp32_full_matmul': True, 'centered': differences}
            finally:
                with torch.no_grad():
                    bias.copy_(original)
                torch.set_float32_matmul_precision(precision)
        return report
