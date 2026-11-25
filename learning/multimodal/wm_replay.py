"""Causal training windows and separately held-out physical sequences for MM-01."""
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_clock import ContactClock
from .world_model import FINGER_THRESHOLD_N, VISION_DIM, camera_features


class PhysicalReplay:
    def __init__(self, root, split, device, *, only=None):
        self.device, self.split = torch.device(device), split
        self.episodes, self.windows = [], {}
        blocks = {k: [] for k in ('p', 'prev', 'vision', 'o', 'a', 'contact', 'prev_contact', 'fresh')}
        self.base, self.end = [], []
        offset = 0
        paths = sorted(Path(root).rglob('metadata.json'))
        if isinstance(only, str):
            only = {only}
        for path in paths:
            if not (path.parent / 'object_state.npy').is_file():
                continue
            meta = json.loads(path.read_text())
            if meta['split'] != split or (only and meta['episode_id'] not in only):
                continue

            def arr(name):
                return np.load(path.parent / (name + '.npy'), allow_pickle=False, mmap_mode='r')

            def as_tensor(x):
                return torch.tensor(np.asarray(x), device=self.device)

            valid = np.asarray(arr('valid_transition'), dtype=bool)
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
            a, contact = (as_tensor(arr(k)).float() for k in ('action_clipped', 'contact'))
            if (p.shape != (n+1, 52) or o.shape != (n+1, 5) or a.shape != (n, 23)
                    or prev.shape != (n+1, 23) or contact.shape != (n, 2)):
                raise ValueError(f'{path}: incompatible physical observation or supervision shapes')
            start = offset
            offset += n+1
            self.base.extend([start]*(n+1))
            self.end.extend([offset-1]*(n+1))
            self.episodes.append(dict(id=meta['episode_id'], scene=meta['scene_id'], source=meta['source'],
                                      start=start, valid=valid, count=n, path=path.parent))
            dual = as_tensor(arr('both_contact_fraction')).float().reshape(n, 1)
            contact = torch.cat(((contact > FINGER_THRESHOLD_N).float(), dual), -1)
            vals = dict(p=p, prev=prev, vision=vision[as_tensor(idx+1)], o=o,
                        a=torch.cat((a, torch.zeros_like(a[:1]))),
                        contact=torch.cat((contact, torch.zeros_like(contact[:1]))),
                        prev_contact=torch.cat((torch.zeros_like(contact[:1]), contact)),
                        fresh=as_tensor(visible & np.r_[True, idx[1:] != idx[:-1]]))
            for key, value in vals.items():
                blocks[key].append(value)
        if not self.episodes:
            raise ValueError(f'No completed {split} physical episodes available under {root}')
        identities = [ep['id'] for ep in self.episodes]
        if len(set(identities)) != len(identities) or (only and set(identities) != set(only)):
            raise ValueError(f'Duplicate or missing {split} episode identities')
        self.parts = {k: torch.cat(v) for k, v in blocks.items()}
        self.base = torch.tensor(self.base, device=self.device)
        self.end = torch.tensor(self.end, device=self.device)

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
        history = torch.maximum(starts[:, None] + torch.arange(-9, 1, device=self.device),
                                self.base[starts, None])
        return {**{k: v[index] for k, v in self.parts.items()},
                'history': self.parts['p'][history], 'previous_history': self.parts['prev'][history]}
