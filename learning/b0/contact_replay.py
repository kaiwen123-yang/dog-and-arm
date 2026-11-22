"""Episode-local fixed-duration windows from measured 20 ms contact transitions."""
from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import torch
from tensordict import TensorDict

from .contact_model import contact_context, contact_state
from .model import tensor
from p6_scene import build


MODES = ('free', 'first_contact', 'two_finger', 'loss_or_slip', 'release', 'other_contact')


@dataclass
class ContactEpisode:
    path: Path
    group: str
    split: str
    side: str
    state: torch.Tensor
    action: torch.Tensor
    context: torch.Tensor
    valid: np.ndarray
    modes: np.ndarray

    @classmethod
    def read(cls, folder, device):
        folder = Path(folder)
        meta = json.loads((folder / 'metadata.json').read_text())
        cfg = json.loads((folder / 'config.json').read_text())
        if not (meta['finished'] and meta['held_action_replay'] and meta['policy_dt'] == .020):
            raise ValueError(f'{folder}: expected a finished held-action episode at 50 Hz')
        if meta['wm_split'] not in ('train', 'validation'):
            raise ValueError(f'{folder}: missing episode split')
        def arr(name):
            return np.load(folder / (name + '.npy'), allow_pickle=False)
        q, v, action = arr('qpos'), arr('qvel'), arr('action_clipped')
        valid, bounds = arr('valid_full_interval'), arr('physics_step')
        done = arr('terminated') | arr('truncated')
        if (len(q) != len(action) + 1 or len(v) != len(q) or not done[-1] or done[:-1].any()
                or not np.array_equal(valid, np.diff(bounds) == 10)
                or not np.isfinite(q).all() or not np.isfinite(v).all() or not np.isfinite(action).all()):
            raise ValueError(f'{folder}: invalid boundaries, terminal flags or nonfinite data')
        force = arr('substeps/finger_load_N')
        phase = np.array(meta['phases'])[arr('substeps/phase')]
        active = force > cfg['contact_threshold_n']
        first = np.flatnonzero(active.any(1))
        grasping = np.isin(phase, ('hold', 'open'))
        release = np.isin(phase, ('release', 'retreat_arm'))
        # Drift relative to the target rod uses the same local hand/rod metric
        # as P6 only when reconstructable. Contact loss here is the measured
        # interruption of dual finger force during the required-grip phase.
        modes = np.full(len(action), 'free', dtype='<U16')
        for k, (i, j) in enumerate(zip(bounds[:-1], bounds[1:])):
            if len(first) and i <= first[0] < j:
                modes[k] = 'first_contact'
            elif release[i:j].any():
                modes[k] = 'release'
            elif (grasping[i:j] & ~active[i:j].all(1)).any():
                modes[k] = 'loss_or_slip'
            elif active[i:j].all():
                modes[k] = 'two_finger'
            elif active[i:j].any():
                modes[k] = 'other_contact'
        m = build(cfg)
        return cls(folder, meta['group_id'], meta['wm_split'], meta['task'],
                   contact_state(tensor(q, device), tensor(v, device)),
                   tensor(action, device), contact_context(m, meta['task'], device), valid, modes)

    def starts(self, steps):
        if len(self.valid) < steps:
            return np.empty(0, dtype=int)
        return np.flatnonzero(np.lib.stride_tricks.sliding_window_view(self.valid, steps).all(-1))


class ContactWindows:
    """Draw measured sequences without padding/tail wrapping or validation leakage."""
    def __init__(self, episodes, steps):
        if any(e.split != 'train' for e in episodes):
            raise ValueError('A validation episode was offered to training')
        self.steps = steps
        device = episodes[0].state.device
        self.offset = torch.arange(steps + 1, device=device)
        valid = []
        states, actions, ctx = [], [], []
        base = 0
        for ep in episodes:
            valid.extend(ep.starts(steps) + base)
            states.append(ep.state)
            # O1 scores the first L-1 actions in an L-state window, inclusive
            # of the measured terminal successor. The appended unused action
            # makes that terminal state indexable; it is never integrated.
            actions.append(torch.cat((ep.action, torch.zeros_like(ep.action[-1:])), 0))
            ctx.append(ep.context.expand(len(ep.state), -1))
            base += len(ep.state)
        if not valid:
            raise ValueError(f'No valid {steps}-step training windows')
        self.starts = torch.as_tensor(np.array(valid), device=device, dtype=torch.long)
        self.state = torch.cat(states)
        self.action = torch.cat(actions)
        self.context = torch.cat(ctx)

    def sample(self, size):
        picks = torch.randint(len(self.starts), (size,), device=self.state.device)
        ix = self.starts[picks, None] + self.offset
        return TensorDict(dict(state=self.state[ix], action=self.action[ix], sim_ctx=self.context[ix]),
                          batch_size=list(ix.shape))
