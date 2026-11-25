"""Causal RGB-D, contact and proprioception dynamics for a passive single door."""
from typing import NamedTuple

import torch
from torch import nn
from torch.nn import functional as F
from supermimic.representations import GenCoordRepresentation

from learning.b0.contact_clock import ContactClock


CLOCK = ContactClock(.002)
GRID = 6
VISION_DIM = 5 * GRID * GRID
HORIZON = 32
PHOTO_PERIOD_TICKS = 5
FINGER_THRESHOLD_N = .01


def camera_features(rgb, depth, valid):
    """Compact, differentiable physical observation. Invalid depth contributes zero."""
    valid = valid & torch.isfinite(depth) & (depth > 0)
    depth = torch.where(valid, depth, 0.)
    channels = torch.cat((rgb.movedim(-1, 1).float() / 255.,
                          (depth / (1. + depth))[:, None], valid[:, None].float()), 1)
    return F.adaptive_avg_pool2d(channels, (GRID, GRID)).flatten(1)


def mlp(n_in, n_out, width):
    return nn.Sequential(nn.Linear(n_in, width), nn.LayerNorm(width), nn.SiLU(),
                         nn.Linear(width, width), nn.SiLU(), nn.Linear(width, n_out))


class Belief(NamedTuple):
    aux: torch.Tensor
    robot: torch.Tensor
    obj: torch.Tensor
    vision: torch.Tensor
    contact_logits: torch.Tensor


class PerceptualDynamics(nn.Module):
    """Integrate 23 encoders and gyro using the project's pinned GenCoord clock.

    Yaw and translation are arbitrary coordinate gauges; the network never sees
    them. The selected rod is estimated in the moving TCP frame in each scene.
    """

    def __init__(self, width=192):
        super().__init__()
        self.width = width
        self.integrator = GenCoordRepresentation(23, torch.zeros(23))
        self.integrator.substep_coeff = CLOCK.substep_coeff
        for name, size in (('p', 52), ('o', 5), ('v', VISION_DIM)):
            self.register_buffer(name + '_mean', torch.zeros(size))
            self.register_buffer(name + '_scale', torch.ones(size))
        self.register_buffer('action_offset', torch.zeros(23))
        self.register_buffer('action_scale', torch.ones(23))
        self.perceive = mlp(52 * 2 + 23 + VISION_DIM, 8, width)
        self.motion = mlp(52 + 5 + VISION_DIM + 3 + 23 * 2, 26 + 4 + VISION_DIM + 3, width)
        nn.init.normal_(self.motion[-1].weight, std=.003)
        nn.init.zeros_(self.motion[-1].bias)

    @torch.no_grad()
    def fit_units(self, p, o, v, offset, scale):
        floors = {
            'p': [.025]*12 + [.15]*4 + [.035]*6 + [.004] +
                 [.10]*12 + [.4]*4 + [.12]*6 + [.015] + [.015]*3 + [.06]*3,
            'o': [.12, .035, .075, .075, .075],
            'v': [.035]*VISION_DIM,
        }
        for name, values in (('p', p), ('o', o), ('v', v)):
            getattr(self, name + '_mean').copy_(values.mean(0))
            getattr(self, name + '_scale').copy_(
                values.std(0, correction=0).maximum(values.new_tensor(floors[name])))
        self.action_offset.copy_(offset)
        self.action_scale.copy_(scale)

    def p_units(self, p):
        return ((p - self.p_mean) / self.p_scale).clamp(-12, 12)

    def v_units(self, v):
        return ((v - self.v_mean) / self.v_scale).clamp(-10, 10)

    def o_units(self, o):
        return ((o - self.o_mean) / self.o_scale).clamp(-12, 12)

    def initial(self, history, previous, vision):
        p = history[:, -1]
        features = torch.cat((self.p_units(p), self.p_units(history[:, 0]),
                              previous[:, -1], self.v_units(vision)), -1)
        estimate = self.perceive(features)
        obj = self.o_mean + self.o_scale * estimate[:, :5]
        gravity = F.normalize(p[:, 46:49], dim=-1)
        zero = torch.zeros_like(gravity)
        down = torch.cat((zero[:, :2], zero[:, :1] - 1.), -1)
        # The shortest rotation from the measured body-down vector to world down.
        quat = torch.cat((1 + (gravity * down).sum(-1, keepdim=True),
                          torch.linalg.cross(gravity, down)), -1)
        fallback = F.pad(torch.ones_like(zero[:, :1]), (1, 2))
        quat = F.normalize(torch.where(quat.norm(dim=-1, keepdim=True) > 1e-6,
                                       quat, fallback), dim=-1)
        aux = torch.cat((zero, quat), -1)
        robot = torch.cat((zero[:, :1], gravity, zero, p[:, 49:52], p[:, :46]), -1)
        return Belief(aux, robot, obj, vision, estimate[:, 5:])

    @staticmethod
    def sensor(state):
        return torch.cat((state.robot[:, 10:], state.robot[:, 1:4], state.robot[:, 7:10]), -1)

    def step(self, state, action, previous):
        p = self.sensor(state)
        features = torch.cat((self.p_units(p), self.o_units(state.obj),
                              self.v_units(state.vision), state.contact_logits.sigmoid(),
                              action, previous), -1)
        output = self.motion(features)
        velocity, hinge_rod, visual, contact = torch.split(output, (26, 4, VISION_DIM, 3), -1)
        q, dq, gyro = p[:, :23], p[:, 23:46], p[:, 49:52]
        target = self.action_offset + action * self.action_scale
        # Wheels are velocity servos, all other entries are position servos.
        # Residuals learn the response of the integrated, finite-gain physical plant.
        demand = torch.cat((8 * (target[:, :12] - q[:, :12]), target[:, 12:16],
                            8 * (target[:, 16:] - q[:, 16:])), -1)
        vscale = self.p_scale[23:46]
        next_dq = .60 * dq + .40 * demand.clamp(-10*vscale, 10*vscale)
        next_dq = next_dq + vscale * velocity[:, :23]
        next_gyro = .8 * gyro + self.p_scale[49:52] * velocity[:, 23:]
        dv = torch.cat((torch.zeros_like(gyro), next_gyro - gyro, next_dq - dq), -1)
        aux, robot = self.integrator.apply_prediction(state.aux, state.robot, dv, CLOCK.policy_dt)
        angle, speed, rod = state.obj[:, :1], state.obj[:, 1:2], state.obj[:, 2:]
        next_speed = .8 * speed + self.o_scale[1] * hinge_rod[:, :1]
        next_angle = angle + CLOCK.policy_dt * (speed + CLOCK.substep_coeff * (next_speed - speed))
        next_rod = rod + CLOCK.policy_dt * hinge_rod[:, 1:] * self.o_scale[2:] * 3
        obj = torch.cat((next_angle, next_speed, next_rod), -1)
        next_vision = state.vision + .10 * self.v_scale * visual
        return Belief(aux, robot, obj, next_vision, contact)

    def task_reward(self, state, goal):
        """A task-angle/rod/contact surrogate; independent full physics determines success."""
        error = state.obj[:, 0] - goal
        angle_score = (1 + (error / .15).square()).reciprocal()
        approach = (1 + (state.obj[:, 2:] / .15).square().sum(-1)).reciprocal()
        dual = state.contact_logits[:, 2].sigmoid()
        unfinished = 1. - (-.5 * (error / .06).square()).exp()
        return angle_score + unfinished * (.15 * approach + .12 * dual) + (1.-unfinished)*.08*(1.-dual)


class VisualBridge(nn.Module):
    """Training-only mapping from predicted physical camera features to actor features."""

    def __init__(self, actor_dim=48):
        super().__init__()
        self.net = mlp(VISION_DIM, actor_dim, 192)
        self.register_buffer('mean', torch.zeros(actor_dim))
        self.register_buffer('scale', torch.ones(actor_dim))

    def forward(self, normalized_camera):
        return self.mean + self.scale * self.net(normalized_camera)


def make_policy_objective(checkpoint, device):
    package = torch.load(checkpoint, map_location=device, weights_only=False)
    model = PerceptualDynamics(package['width']).to(device)
    model.load_state_dict(package['model'])
    bridge = VisualBridge(package['actor_visual_dim']).to(device)
    bridge.load_state_dict(package['bridge'])
    model.eval().requires_grad_(False)
    bridge.eval().requires_grad_(False)
    objective = package['objective']

    def loss(actor, batch):
        n = min(objective['imagination_batch'], len(batch['rgb']))
        b = {k: batch[k][:n] for k in ('rgb', 'depth', 'depth_valid', 'tokens', 'proprio_history',
                                       'previous_history', 'sensor', 'command_angle_rad')}
        hist, previous, sensor = b['proprio_history'], b['previous_history'], b['sensor']
        with torch.no_grad():
            measured = actor.encode_visual(b['rgb'], b['depth'], b['depth_valid'])
            text = actor.encode_text(b['tokens'])
            low = camera_features(b['rgb'], b['depth'], b['depth_valid'])
            state = model.initial(hist, previous, low)
            bridge_start = bridge(model.v_units(low))
        visual = measured
        goal = b['command_angle_rad'].reshape(-1)
        age_ticks = (sensor[:, 0] / CLOCK.policy_dt).round().long().clamp_min(0)
        total = measured.new_zeros(())
        denom = 0.
        for k in range(objective['horizon']):
            action = actor.act_features(visual, text, hist, previous, sensor)
            state = model.step(state, action, previous[:, -1])
            w = objective['discount'] ** k
            total = total + w * model.task_reward(state, goal).mean()
            denom += w
            hist = torch.cat((hist[:, 1:], model.sensor(state)[:, None]), 1)
            previous = torch.cat((previous[:, 1:], action[:, None]), 1)
            age_ticks = (age_ticks + 1) % PHOTO_PERIOD_TICKS
            fresh = (age_ticks == 0)[:, None]
            estimated = measured + bridge(model.v_units(state.vision)) - bridge_start
            visual = torch.where(fresh, estimated, visual)
            sensor = torch.cat((age_ticks[:, None] * CLOCK.policy_dt,
                                torch.where(fresh, 1., sensor[:, 1:2]),
                                sensor[:, 2:3] + CLOCK.policy_dt), -1)
        reward = total / denom
        return -objective['weight'] * reward, {
            'h32_reward': reward.detach(),
            'estimated_actor_feature_change_rms': (visual - measured).square().mean().sqrt().detach(),
        }

    return loss
