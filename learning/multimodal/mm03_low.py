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
        self.register_buffer("wheel_loss_scale", torch.full((4,), .1))
        self.register_buffer("velocity_units", torch.tensor([.07, .10]))
        self.estimator = nn.Sequential(nn.Linear(150, 64), nn.SiLU(), nn.Linear(64, 32), nn.SiLU(), nn.Linear(32, 2))
        self.control = nn.Sequential(nn.Linear(154, 96), nn.SiLU(), nn.Linear(96, 64), nn.SiLU(), nn.Linear(64, 20))
        nn.init.normal_(self.control[-1].weight, std=.005)
        nn.init.zeros_(self.control[-1].bias)

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
            self.wheel_loss_scale.copy_(torch.quantile(labels[:, 12:].abs(), .9, dim=0).clamp_min(.04))

    def estimate(self, history, previous):
        x = self.features(history, previous)
        return self.estimator(((x-self.feature_mean)/self.feature_std).clamp(-8., 8.))*self.velocity_units

    def from_features(self, x, request, velocity_override=None):
        z = ((x-self.feature_mean)/self.feature_std).clamp(-8., 8.)
        estimate = self.estimator(z)*self.velocity_units
        vel = estimate if velocity_override is None else velocity_override
        rates = request/self.velocity_units
        coefficients = self.control(torch.cat((z, rates, vel/self.velocity_units), dim=-1))
        # Reuse the previous *actual* leg target as a causal integral state.
        # Head increments and both wheel gains are learned from executed trials.
        # The homogeneous wheel output encodes the registered zero-speed convention.
        prior = x[..., 104:120]
        gate = (rates.abs().sum(-1, keepdim=True) + 8*prior[..., 12:16].abs().mean(-1, keepdim=True)).clamp(max=1.)
        leg = prior[..., :12] + gate*coefficients[..., :12]*self.leg_increment_scale
        wheels = rates[..., :1]*coefficients[..., 12:16] + rates[..., 1:]*coefficients[..., 16:20]
        return torch.cat((leg, wheels), -1).clamp(-1., 1.), estimate

    def forward(self, history, previous, request, velocity_override=None):
        return self.from_features(self.features(history, previous), request, velocity_override)[0]

    @classmethod
    def load(cls, path, device="cpu"):
        package = torch.load(Path(path), map_location=device, weights_only=False)
        if package["schema"] != cls.schema:
            raise ValueError(f"Unexpected low checkpoint schema {package['schema']}")
        model = cls().to(device)
        model.load_state_dict(package["model"], strict=True)
        return model.eval()
