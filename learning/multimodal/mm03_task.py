"""MM03 shared causal actor backbone, direct23 and command+learned-low-level heads."""
import torch
from torch import nn
import torch.nn.functional as F

from .actor import ACTION_DIM, MultimodalActor, Vocabulary
from .mm03_low import LowPolicy

SCHEMA = "MM03-task-actor-v1"


class TaskActor(MultimodalActor):
    """High output is [vx (m/s), wz (rad/s), seven normalized arm/jaw commands]."""

    def __init__(self, vocab, mode, affine_mode):
        super().__init__(vocab, affine_mode)
        self.mode = mode
        self.low = LowPolicy().requires_grad_(False).eval()
        size = 23 if mode == "D23" else 9
        if mode not in ("D23", "H9"):
            raise ValueError(f"Unsupported task architecture: {mode}")
        if size == 9:
            self.head[-1] = nn.Linear(self.head[-1].in_features, 9)
        self.estimated_velocity_head = nn.Linear(2, size, bias=False)
        nn.init.zeros_(self.estimated_velocity_head.weight)
        self.register_buffer("request_scale", torch.tensor([.07, .08]))

    def bind_frozen_low(self, state):
        # LowPolicy owns both legacy lifts and the bounded-stationary version flag.
        # It rejects partially missing current buffers and unknown parameter layouts.
        self.low.inherit(state)
        self.low.requires_grad_(False).eval()

    def restore_task_state(self, state):
        low_state = {name[4:]:tensor for name,tensor in state.items() if name.startswith("low.")}
        self.bind_frozen_low(low_state)
        canonical = {name:tensor for name,tensor in state.items() if not name.startswith("low.")}
        canonical.update({"low."+name:tensor for name,tensor in self.low.state_dict().items()})
        self.load_state_dict(canonical,strict=True)

    def high_features(self, visual, language, hist, previous, sensor):
        prop = ((hist - self.proprio_mean) / self.proprio_std).clamp(-10, 10)
        act = ((previous - self.action_mean) / self.action_std).clamp(-10, 10)
        seq = torch.cat((prop, act), -1)
        t = sensor[:, 2:3]
        theta = t * self.clock_rates
        timing = torch.cat(((sensor[:, :1] / .1).clamp(0, 3), sensor[:, 1:2], t / 90.,
                            theta.sin(), theta.cos()), -1)
        z = torch.cat((visual * sensor[:, 1:2], language, self.history_model(seq.flatten(1)),
                       seq[:, -1], timing), -1)
        est = self.low.estimate(hist, previous)
        y = self.head(z) + self.estimated_velocity_head((est / self.request_scale).clamp(-8, 8))
        base = self.base_action(hist[:, -1])
        if self.mode == "D23":
            return base + self.residual_std * y, est
        high = torch.cat((y[:, :2].tanh() * self.request_scale,
                          base[:, 16:] + self.residual_std[16:] * y[:, 2:]), -1)
        return high, est

    def infer_features(self, visual, language, hist, previous, sensor):
        high, est = self.high_features(visual, language, hist, previous, sensor)
        if self.mode == "D23":
            return high, high, est
        low = self.low(hist, previous, high[:, :2])
        return torch.cat((low, high[:, 2:]), -1), high, est

    def act_features_raw(self, visual, language, hist, previous, sensor):
        return self.infer_features(visual, language, hist, previous, sensor)[0]

    def high_batch(self, batch):
        return self.high_features(self.encode_visual(batch["rgb"], batch["depth"], batch["depth_valid"]),
                                  self.encode_text(batch["tokens"]), batch["proprio_history"],
                                  batch["previous_history"], batch["sensor"])[0]

    def bc_loss(self, batch, common_only=False):
        from scripts.multimodal.train_actor import bc_objective
        high = self.high_batch(batch)
        if self.mode == "D23":
            if not common_only:
                return bc_objective(self, high.clamp(-1, 1), batch["action"])
            residual = (high.clamp(-1,1)-batch["action"])/self.residual_std
            errs = F.smooth_l1_loss(residual,torch.zeros_like(residual),reduction="none",beta=.5)
            mask = batch["command_valid"].to(errs.dtype)
            compatible = errs[:, :12].mean(1)+errs[:,12:16].mean(1)
            # Cost sensitivity gives both approaches only supervision which their
            # own interface can use. Legacy records still teach the shared arm/jaw.
            return (errs[:,16:22].mean()+errs[:,22].mean()+
                    (compatible*mask).sum()/mask.sum().clamp_min(1))/(2+2*(mask.sum()>0))
        residual = (high[:, 2:].clamp(-1, 1) - batch["action"][:, 16:]) / self.residual_std[16:]
        arm_error = F.smooth_l1_loss(residual, torch.zeros_like(residual), reduction="none", beta=.5)
        cmd_res = (high[:, :2] - batch["command"]) / self.request_scale
        cmd_err = F.smooth_l1_loss(cmd_res, torch.zeros_like(cmd_res), reduction="none", beta=.5).mean(1)
        mask = batch["command_valid"].to(cmd_err.dtype)
        return (arm_error[:, :6].mean() + arm_error[:, 6].mean() +
                (mask * cmd_err).sum() / mask.sum().clamp_min(1)) / (2 + (mask.sum() > 0))


def load_task_actor(path, device="cpu"):
    data = torch.load(path, map_location=device, weights_only=False)
    if data["schema"] != SCHEMA:
        raise ValueError(f"Unsupported task checkpoint in {path}")
    vocab = Vocabulary(data["vocabulary"])
    actor = TaskActor(vocab, data["architecture"], data["affine_mode"]).to(device)
    actor.restore_task_state(data["actor"])
    return actor.eval(), vocab, data


def migrate(parent_actor, parent, vocab, low_path, mode, device):
    """Retain all shape-compatible trunk and Adam moments, including H9 arm output rows."""
    actor = TaskActor(vocab, mode, parent["affine_mode"]).to(device)
    state = actor.state_dict()
    old = parent_actor.state_dict()
    for name, value in old.items():
        if mode == "H9" and name in ("head.6.weight", "head.6.bias"):
            state[name][2:].copy_(value[16:])
            state[name][:2].zero_()
        else:
            state[name].copy_(value)
    actor.load_state_dict(state)
    actor.bind_frozen_low(LowPolicy.load(low_path,device).state_dict())
    return actor


def optimizer_for(actor):
    named = [(n, p) for n, p in actor.named_parameters() if not n.startswith("low.")]
    groups = [([n for n, _ in named if n != "servo_slope"],
               [p for n, p in named if n != "servo_slope"])]
    if isinstance(actor.servo_slope, nn.Parameter):
        groups.append((["servo_slope"], [actor.servo_slope]))
    optimizer = torch.optim.AdamW([dict(params=ps, lr=.0001, weight_decay=0. if ns == ["servo_slope"] else 1e-5)
                                   for ns, ps in groups])
    return optimizer, [ns for ns, _ in groups]


def migrate_optimizer(actor, parent):
    optimizer, groups = optimizer_for(actor)
    old_opt = parent["optimizer"]
    old = {n: pid for group, names in zip(old_opt["param_groups"], parent["optimizer_names"], strict=True)
           for n, pid in zip(names, group["params"], strict=True)}
    payload = optimizer.state_dict()
    named = dict(actor.named_parameters())
    retained, partially, created = [], [], []
    for group, ns in zip(payload["param_groups"], groups, strict=True):
        src_group = old_opt["param_groups"][1 if ns == ["servo_slope"] else 0]
        group.update({k: v for k, v in src_group.items() if k not in ("params", "param_names")})
        for n, pid in zip(ns, group["params"], strict=True):
            if n not in old:
                created.append(n)
                continue
            src = old_opt["state"][old[n]]
            if src["exp_avg"].shape == named[n].shape:
                payload["state"][pid] = src
                retained.append(n)
            elif actor.mode == "H9" and n in ("head.6.weight", "head.6.bias"):
                # Per-tensor Adam has a single age. Fully initialize this changed tensor's
                # moments and step together, while preserving its inherited seven weight rows.
                partially.append(n)
            else:
                raise ValueError(f"Unexpected optimizer shape for {n}")
    optimizer.load_state_dict(payload)
    return optimizer, groups, dict(restored=retained, changed_head_fresh_adam=partially, new_names=created)
