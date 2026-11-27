"""Causal training windows and separately held-out physical sequences for MM-01."""
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_clock import ContactClock
from .world_model import FINGER_THRESHOLD_N, VISION_DIM, camera_features


class PhysicalReplay:
    def __init__(self, root, split, device, *, only=None, episode_dirs=None, direct_storage=False):
        self.device, self.split = torch.device(device), split
        self.episodes, self.windows = [], {}
        blocks = {k: [] for k in ('p', 'prev', 'vision', 'o', 'a', 'contact', 'prev_contact', 'fresh')}
        self.base, self.end = [], []
        self.prefix_p, self.prefix_prev, self.episode_index = [], [], []
        offset = 0
        paths = (sorted(Path(root).rglob('metadata.json')) if episode_dirs is None
                 else [Path(directory) / 'metadata.json' for directory in episode_dirs])
        if isinstance(only, str):
            only = {only}
        episodes = []
        for path in paths:
            if not (path.parent / 'object_state.npy').is_file():
                continue
            meta = json.loads(path.read_text())
            if episode_dirs is not None and meta['split'] != split:
                raise ValueError(f'{path}: expected {split} replay, received {meta["split"]}')
            if meta['split'] != split or (only and meta['episode_id'] not in only):
                continue
            episodes.append((path,meta))

        if direct_storage:
            # Count from the recorded mask, including each nonempty episode's final boundary.
            sizes=(len(np.load(path.parent/'valid_transition.npy',allow_pickle=False,mmap_mode='r'))
                   for path,_ in episodes)
            capacity=sum(n+1 for n in sizes if n)
            self.parts={}
        for path,meta in episodes:
            def arr(name):
                return np.load(path.parent / (name + '.npy'), allow_pickle=False, mmap_mode='r')

            def as_tensor(x):
                return torch.tensor(np.asarray(x), device=self.device)

            # This small, persistent mask outlives the episode's mapped arrays.
            valid = np.array(arr('valid_transition'), dtype=bool, copy=True)
            n = len(valid)
            if not n:
                continue
            t, idx, image_t = arr('t'), np.asarray(arr('image_index'), dtype=int), arr('image_t')
            visible = idx >= 0
            latest = np.searchsorted(image_t, t + 1e-7, side='right') - 1
            if (len(t) != n+1 or len(idx) != len(t) or
                    not np.allclose(np.diff(t)[valid], ContactClock.policy_dt, rtol=0, atol=2e-6) or
                    np.any(idx < -1) or np.any(idx[visible] != latest[visible])):
                raise ValueError(f'{path}: invalid 20 ms intervals or future camera frame')
            rgb, depth, mask = arr('rgb'), arr('depth'), arr('depth_valid')
            # Index zero is an explicit missing RGB-D observation.
            camera = [torch.zeros(1, VISION_DIM, device=self.device)]
            for begin in range(0, len(rgb), 128):
                sl = slice(begin, begin+128)
                camera.append(camera_features(as_tensor(rgb[sl]), as_tensor(depth[sl]), as_tensor(mask[sl])))
            vision = torch.cat(camera)
            p, o, prev = (as_tensor(arr(k)).float() for k in ('proprio', 'object_state', 'previous_action'))
            action_key = ('executed_action_clipped' if (path.parent / 'executed_action_clipped.npy').is_file()
                          else 'action_clipped')
            if meta.get('schema', '').startswith('mm02') and action_key != 'executed_action_clipped':
                raise ValueError(f'{path}: missing explicitly recorded executed action')
            a, contact = (as_tensor(arr(k)).float() for k in (action_key, 'contact'))
            if (p.shape != (n+1, 52) or o.shape != (n+1, 5) or a.shape != (n, 23)
                    or prev.shape != (n+1, 23) or contact.shape != (n, 2)):
                raise ValueError(f'{path}: incompatible physical observation or supervision shapes')
            start = offset
            offset += n+1
            self.base.extend([start]*(n+1))
            self.end.extend([offset-1]*(n+1))
            self.episode_index.extend([len(self.episodes)]*(n+1))
            if not torch.allclose(prev[1:], a, atol=1e-6, rtol=0):
                raise ValueError(f'{path}: observation history differs from executed commands')
            if meta.get('parent_episode') is not None and meta.get('anchor_tick') is not None:
                prefix_p = as_tensor(arr('history_prefix_proprio')).float()
                prefix_prev = as_tensor(arr('history_prefix_previous_action')).float()
                prev_contact = as_tensor(arr('history_prefix_contact')).float().reshape(1, 3)
                if prefix_p.shape != (9, 52) or prefix_prev.shape != (9, 23):
                    raise ValueError(f'{path}: recovery needs the preceding nine actual observation/action pairs')
            else:
                prefix_p, prefix_prev = p[:1].expand(9, -1), prev[:1].expand(9, -1)
                prev_contact = p.new_zeros(1, 3)
            # An expanded slice otherwise keeps the entire source episode alive until the final stack.
            self.prefix_p.append(prefix_p.clone() if direct_storage else prefix_p)
            self.prefix_prev.append(prefix_prev.clone() if direct_storage else prefix_prev)
            self.episodes.append(dict(id=meta['episode_id'], scene=meta['scene_id'], source=meta['source'],
                                      start=start, valid=valid, count=n, path=path.parent, meta=meta))
            dual = as_tensor(arr('both_contact_fraction')).float().reshape(n, 1)
            contact = torch.cat(((contact > FINGER_THRESHOLD_N).float(), dual), -1)
            vals = dict(p=p, prev=prev, vision=vision[as_tensor(idx+1)], o=o,
                        a=torch.cat((a, torch.zeros_like(a[:1]))),
                        contact=torch.cat((contact, torch.zeros_like(contact[:1]))),
                        prev_contact=torch.cat((prev_contact, contact)),
                        fresh=as_tensor(visible & np.isclose(t, image_t[np.maximum(0, idx)],
                                                           atol=1e-6, rtol=0)) if len(image_t)
                              else as_tensor(np.zeros(n+1, dtype=bool)))
            for key, value in vals.items():
                if direct_storage:
                    if key not in self.parts:
                        self.parts[key]=value.new_empty((capacity,*value.shape[1:]))
                    if value.dtype!=self.parts[key].dtype or value.shape[0]!=offset-start:
                        raise ValueError(f'{path}: inconsistent replay field {key}')
                    self.parts[key][start:offset].copy_(value)
                else:
                    blocks[key].append(value)
        if not self.episodes:
            raise ValueError(f'No completed {split} physical episodes available under {root}')
        identities = [ep['id'] for ep in self.episodes]
        if len(set(identities)) != len(identities) or (only and set(identities) != set(only)):
            raise ValueError(f'Duplicate or missing {split} episode identities')
        if direct_storage:
            if offset!=capacity:
                raise ValueError('Replay membership changed while loading decision boundaries')
        else:
            self.parts = {k: torch.cat(v) for k, v in blocks.items()}
        self.base = torch.tensor(self.base, device=self.device)
        self.end = torch.tensor(self.end, device=self.device)
        self.prefix_p = torch.stack(self.prefix_p)
        self.prefix_prev = torch.stack(self.prefix_prev)
        self.episode_index = torch.tensor(self.episode_index, device=self.device)

    def summary(self):
        return [dict(episode_id=e['id'], scene=e['scene'], source=e['source'],
                     transitions=e['count'], valid=int(e['valid'].sum())) for e in self.episodes]

    def starts(self, steps):
        if steps not in self.windows:
            valid = []
            for ep in self.episodes:
                if len(ep['valid']) >= steps:
                    ok = np.lib.stride_tricks.sliding_window_view(ep['valid'], steps).all(axis=-1)
                    valid.extend(ep['start'] + np.flatnonzero(ok))
            ix = torch.tensor(valid, device=self.device, dtype=torch.long)
            if not len(ix):
                raise ValueError(f'No {self.split} windows of {steps} physical transitions')
            contact = self.parts['contact'][ix, :2].bool().any(-1)
            self.windows[steps] = (ix, ix[contact])
        return self.windows[steps]

    def draw_starts(self, horizon, batch, rng, stratified):
        all_starts, contact = self.starts(horizon)
        def pick(pool, size):
            return pool[torch.randint(len(pool), (size,), device=self.device, generator=rng)]
        n_contact = batch // 3 if stratified and len(contact) else 0
        return torch.cat((pick(all_starts, batch - n_contact), pick(contact, n_contact))) if n_contact else pick(all_starts, batch)

    def window(self, starts, horizon):
        index = starts[:, None] + torch.arange(horizon + 1, device=self.device)
        requested = starts[:, None] + torch.arange(-9, 1, device=self.device)
        base = self.base[starts, None]
        history = torch.maximum(requested, base)
        prefix = (requested - base + 9).clamp(0, 8)
        episode = self.episode_index[starts, None]
        use_prefix = (requested < base)[..., None]
        return {**{k: v[index] for k, v in self.parts.items()},
                'history': torch.where(use_prefix, self.prefix_p[episode, prefix], self.parts['p'][history]),
                'previous_history': torch.where(use_prefix, self.prefix_prev[episode, prefix], self.parts['prev'][history])}
