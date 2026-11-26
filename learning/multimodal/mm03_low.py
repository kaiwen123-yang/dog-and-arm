"""Learned L16 and the shared causal body-velocity estimator (no native engine)."""
from pathlib import Path

import torch
from torch import nn


class LowPolicy(nn.Module):
    schema = "MM03-L16-local-v1"

    def __init__(self):
        super().__init__()
        self.register_buffer("feature_mean", torch.zeros(150))
        self.register_buffer("feature_std", torch.ones(150))
        self.register_buffer("leg_increment_scale", torch.full((12,), .004))
        self.register_buffer("leg_scale", torch.full((12,), .05))
        self.register_buffer("stationary_mode", torch.tensor(0, dtype=torch.uint8))
        self.register_buffer("stationary_bound", torch.ones(12))
        self.bounded_stationary = False
        self.register_buffer("wheel_loss_scale", torch.full((4,), .1))
        self.register_buffer("velocity_units", torch.tensor([.07, .10]))
        self.estimator = nn.Sequential(nn.Linear(150, 64), nn.SiLU(), nn.Linear(64, 32), nn.SiLU(), nn.Linear(32, 2))
        self.control = nn.Sequential(nn.Linear(154, 96), nn.SiLU(), nn.Linear(96, 64), nn.SiLU(), nn.Linear(64, 20))
        self.stationary = nn.Sequential(nn.Linear(154, 32), nn.SiLU(), nn.Linear(32, 12))
        nn.init.normal_(self.control[-1].weight, std=.005)
        nn.init.zeros_(self.control[-1].bias)
        nn.init.zeros_(self.stationary[-1].weight)
        nn.init.zeros_(self.stationary[-1].bias)

    @staticmethod
    def features(history, previous):
        """Both ten-frame histories end at now; previous[t] is the last applied action."""
        return torch.cat((history[..., -1, :], history.mean(-2), previous[..., -1, :], previous.mean(-2)), -1)

    def calibrate(self, x, labels):
        with torch.no_grad():
            self.feature_mean.copy_(x.mean(0))
            self.feature_std.copy_(x.std(0, unbiased=False).clamp_min(.01))
            leg_change = (labels[:, :12]-x[:, 104:116]).abs()
            self.leg_increment_scale.copy_(torch.quantile(leg_change, .995, dim=0).clamp(.0005, .05))
            self.leg_scale.copy_(labels[:, :12].std(0, unbiased=False).clamp_min(.02))
            self.wheel_loss_scale.copy_(torch.quantile(labels[:, 12:].abs(), .9, dim=0).clamp_min(.04))

    def estimate(self, history, previous):
        x = self.features(history, previous)
        return self.estimator(((x-self.feature_mean)/self.feature_std).clamp(-8., 8.))*self.velocity_units

    def from_features(self, x, request, velocity_override=None):
        z = ((x-self.feature_mean)/self.feature_std).clamp(-8., 8.)
        estimate = self.estimator(z)*self.velocity_units
        vel = estimate if velocity_override is None else velocity_override
        rates = request/self.velocity_units
        inputs = torch.cat((z, rates, vel/self.velocity_units), dim=-1)
        coefficients = self.control(inputs)
        # Reuse the previous *actual* leg target as a causal integral state.
        # Head increments and both wheel gains are learned from executed trials.
        # The homogeneous wheel output encodes the registered zero-speed convention.
        prior = x[..., 104:120]
        gate = (rates.abs().sum(-1, keepdim=True) + 8*prior[..., 12:16].abs().mean(-1, keepdim=True)).clamp(max=1.)
        moving = gate*coefficients[..., :12]*self.leg_increment_scale
        feedback = self.stationary(inputs)
        if self.bounded_stationary:
            # At rest, successive outputs are convex combinations of the last
            # actual target and a learned absolute position in the training range.
            absolute = self.stationary_bound*torch.tanh(feedback)
            leg = .96*prior[..., :12] + .04*absolute + moving
        else:
            # Block0 and block1 keep their exact original arithmetic.
            leg = prior[..., :12] + moving
            leg = leg + .04*self.leg_scale*feedback
        wheels = rates[..., :1]*coefficients[..., 12:16] + rates[..., 1:]*coefficients[..., 16:20]
        return torch.cat((leg, wheels), -1).clamp(-1., 1.), estimate

    def forward(self, history, previous, request, velocity_override=None):
        return self.from_features(self.features(history, previous), request, velocity_override)[0]

    @torch.no_grad()
    def enable_bounded_stationary(self, teacher_targets):
        self.stationary_bound.copy_(teacher_targets[:, :12].abs().amax(0).clamp_max(1.))
        self.stationary_mode.fill_(1)
        self.bounded_stationary = True
        # The former final layer represented per-step increments. A zero
        # absolute head starts at the canonical neutral pose in normalized units.
        self.stationary[-1].weight.zero_()
        self.stationary[-1].bias.zero_()

    def _load_from_state_dict(self, state_dict, prefix, local_metadata, strict,
                              missing_keys, unexpected_keys, error_msgs):
        # Older standalone and embedded H9 packages predate these two buffers.
        # Restore their residual mode, and keep strict checks on all other fields.
        mode_key, bound_key = prefix+"stationary_mode", prefix+"stationary_bound"
        if mode_key not in state_dict and bound_key not in state_dict:
            state_dict[mode_key] = torch.zeros_like(self.stationary_mode)
            state_dict[bound_key] = torch.ones_like(self.stationary_bound)
        super()._load_from_state_dict(state_dict, prefix, local_metadata, strict,
                                      missing_keys, unexpected_keys, error_msgs)
        self.bounded_stationary = bool(self.stationary_mode.item())

    def inherit(self, state):
        """Lift the original 20-output L16 into its zero-initialized correction."""
        if "stationary.0.weight" in state:
            self.load_state_dict(state, strict=True)
            return False
        new_buffers = {"leg_scale", "stationary_mode", "stationary_bound"}
        expected = {k for k in self.state_dict() if k not in new_buffers and not k.startswith("stationary.")}
        if set(state) != expected or state["control.4.weight"].shape != (20, 64):
            raise ValueError("Unrecognized L16 parent architecture")
        self.load_state_dict(state, strict=False)
        # The same legacy package lifts to identical tensors in deployment,
        # H9, H9-WM and the subsequent optimizer, even in different processes.
        g = torch.Generator().manual_seed(26112603)
        with torch.no_grad():
            first = self.stationary[0]
            bound = first.in_features**-.5
            for value in (first.weight, first.bias):
                initial = torch.empty(value.shape, dtype=value.dtype, device="cpu").uniform_(-bound, bound, generator=g)
                value.copy_(initial)
            self.stationary[-1].weight.zero_()
            self.stationary[-1].bias.zero_()
        return True

    @classmethod
    def load(cls, path, device="cpu"):
        package = torch.load(Path(path), map_location=device, weights_only=False)
        if package["schema"] != cls.schema:
            raise ValueError(f"Unexpected low checkpoint schema {package['schema']}")
        with torch.random.fork_rng(devices=[]):
            model = cls().to(device)
        model.inherit(package["model"])
        return model.eval()
