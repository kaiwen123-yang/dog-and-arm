"""Causal RGB-D, text and proprioceptive policy for the 23-channel ActionMap."""
from collections import deque
import math
from pathlib import Path
import re

import numpy as np
import torch
from torch import nn


HISTORY = 10
TEXT_LENGTH = 24
VISUAL_DIM = 48
TEXT_DIM = 32
PROPRIO_DIM = 52
ACTION_DIM = 23
POLICY_DT = 0.02


def words(text):
    return re.findall(r"\d+(?:\.\d+)?|[a-z]+|[\u3400-\u9fff]", text.lower())


def command_angle_rad(text):
    numbers = [float(word) for word in words(text) if word[0].isdigit()]
    if len(numbers) != 1:
        raise ValueError(f"Expected one numeric opening angle in {text!r}")
    return math.radians(numbers[0])


class Vocabulary:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.indices = {token: i for i, token in enumerate(self.tokens)}

    @classmethod
    def fit(cls, instructions):
        tokens = sorted({word for instruction in instructions for word in words(instruction)})
        return cls(["<pad>", "<unk>", *tokens])

    def encode(self, text):
        tokens = [self.indices.get(word, 1) for word in words(text)]
        if len(tokens) > TEXT_LENGTH:
            raise ValueError(f"Instruction has {len(tokens)} tokens, maximum is {TEXT_LENGTH}")
        return tokens + [0] * (TEXT_LENGTH - len(tokens))


def stem(channels):
    return nn.Sequential(nn.Conv2d(channels, 16, 5, stride=2, padding=2), nn.SiLU(),
                         nn.Conv2d(16, 24, 3, stride=2, padding=1), nn.SiLU(),
                         nn.Conv2d(24, 32, 3, stride=2, padding=1), nn.SiLU(),
                         nn.AdaptiveAvgPool2d((4, 4)), nn.Flatten())


class MultimodalActor(nn.Module):
    def __init__(self, vocabulary):
        super().__init__()
        self.rgb_encoder = stem(3)
        self.depth_encoder = stem(2)
        self.visual_projection = nn.Sequential(nn.Linear(2 * 32 * 4 * 4, 128), nn.LayerNorm(128),
                                               nn.SiLU(), nn.Linear(128, VISUAL_DIM), nn.Tanh())
        self.embedding = nn.Embedding(len(vocabulary.tokens), TEXT_DIM, padding_idx=0)
        self.token_weight = nn.Linear(TEXT_DIM, 1)
        self.text_projection = nn.Sequential(nn.Linear(TEXT_DIM + 1, TEXT_DIM), nn.Tanh())
        numeric = [float(t) / 90.0 if t[:1].isdigit() else 0.0 for t in vocabulary.tokens]
        self.register_buffer("numeric_tokens", torch.tensor(numeric))
        self.history_model = nn.Sequential(nn.Linear(HISTORY * (PROPRIO_DIM + ACTION_DIM), 192),
                                           nn.LayerNorm(192), nn.SiLU(), nn.Linear(192, 96), nn.SiLU())
        # The clock originates at the actual reset and advances with sensor time, including stalls.
        self.register_buffer("clock_rates", torch.tensor([0.07, 0.15, 0.3, 0.6, 1.2, 2.4]))
        features = VISUAL_DIM + TEXT_DIM + 96 + PROPRIO_DIM + ACTION_DIM + 15
        self.head = nn.Sequential(nn.Linear(features, 256), nn.LayerNorm(256), nn.SiLU(),
                                  nn.Linear(256, 192), nn.LayerNorm(192), nn.SiLU(), nn.Linear(192, ACTION_DIM))
        nn.init.normal_(self.head[-1].weight, std=0.002)
        nn.init.zeros_(self.head[-1].bias)
        for name, size, initial in (("proprio_mean", PROPRIO_DIM, 0), ("proprio_std", PROPRIO_DIM, 1),
                                    ("action_mean", ACTION_DIM, 0), ("action_std", ACTION_DIM, 1),
                                    ("servo_mean", ACTION_DIM, 0), ("servo_slope", ACTION_DIM, 0),
                                    ("residual_std", ACTION_DIM, 1)):
            self.register_buffer(name, torch.full((size,), float(initial)))

    @staticmethod
    def servo_measurement(proprio):
        # Position servos on legs/arm/jaw and velocity servos on wheels. No door or root pose.
        return torch.cat((proprio[..., :12], proprio[..., 23+12:23+16], proprio[..., 16:23]), dim=-1)

    @torch.no_grad()
    def fit_scalers(self, proprio, action):
        self.proprio_mean.copy_(proprio.mean(0))
        floor = torch.tensor([0.01] * 22 + [0.002] + [0.06] * 22 + [0.004] + [0.02] * 3 + [0.03] * 3,
                             device=proprio.device)
        self.proprio_std.copy_(torch.maximum(proprio.std(0, unbiased=False), floor))
        self.action_mean.copy_(action.mean(0))
        self.action_std.copy_(action.std(0, unbiased=False).clamp_min(0.018))
        servo = self.servo_measurement(proprio)
        self.servo_mean.copy_(servo.mean(0))
        centered_servo = servo - self.servo_mean
        slope = (centered_servo * (action - self.action_mean)).mean(0) / (centered_servo.square().mean(0) + 1e-6)
        # Fit a channel-wise skip from measured joint state to mean commanded state on training data.
        # Clamping limits extrapolation for channels with nearly constant teacher actions.
        self.servo_slope.copy_(slope.clamp(-22, 22))
        residual = action - self.base_action(proprio)
        self.residual_std.copy_(residual.std(0, unbiased=False).clamp_min(0.012))

    def base_action(self, proprio):
        baseline = self.action_mean + self.servo_slope * (self.servo_measurement(proprio) - self.servo_mean)
        return baseline.clamp(-1.0, 1.0)

    def encode_visual(self, rgb, depth, depth_valid):
        rgb = rgb.permute(0, 3, 1, 2).float() / 255.0 - 0.5
        valid = depth_valid.bool() & torch.isfinite(depth) & (depth > 0)
        depth = torch.where(valid, depth, 0.0).clamp(0, 5).log1p() / math.log(6)
        depth = torch.stack((depth, valid.to(depth.dtype)), dim=1)
        return self.visual_projection(torch.cat((self.rgb_encoder(rgb), self.depth_encoder(depth)), dim=-1))

    def encode_text(self, tokens):
        embeddings = self.embedding(tokens)
        weights = self.token_weight(embeddings).squeeze(-1).masked_fill(tokens == 0, -1e4).softmax(-1)
        bag = (weights[..., None] * embeddings).sum(1)
        angle = self.numeric_tokens[tokens].sum(-1, keepdim=True)
        return self.text_projection(torch.cat((bag, angle), dim=-1))

    def act_features_raw(self, visual, text_embedding, proprio_history, previous_history, sensor):
        prop = ((proprio_history - self.proprio_mean) / self.proprio_std).clamp(-10, 10)
        previous = ((previous_history - self.action_mean) / self.action_std).clamp(-10, 10)
        sequence = torch.cat((prop, previous), dim=-1)
        past = self.history_model(sequence.flatten(1))
        elapsed = sensor[:, 2:3]
        phase = elapsed * self.clock_rates
        timing = torch.cat(((sensor[:, 0:1] / 0.1).clamp(0, 3), sensor[:, 1:2], elapsed / 90.,
                            phase.sin(), phase.cos()), dim=-1)
        features = torch.cat((visual * sensor[:, 1:2], text_embedding, past, sequence[:, -1], timing), dim=-1)
        return self.base_action(proprio_history[:, -1]) + self.residual_std * self.head(features)

    def act_features(self, visual, text_embedding, proprio_history, previous_history, sensor):
        return self.act_features_raw(visual, text_embedding, proprio_history, previous_history, sensor).clamp(-1, 1)

    def forward(self, batch):
        return self.act_features(self.encode_visual(batch["rgb"], batch["depth"], batch["depth_valid"]),
                                 self.encode_text(batch["tokens"]), batch["proprio_history"],
                                 batch["previous_history"], batch["sensor"])

    def freeze_encoders(self):
        for module in (self.rgb_encoder, self.depth_encoder, self.visual_projection, self.embedding,
                       self.token_weight, self.text_projection):
            module.requires_grad_(False)


def load_actor(checkpoint, device="cpu"):
    payload = torch.load(Path(checkpoint), map_location=device, weights_only=False)
    if payload["schema"] != "M1Piper-Multimodal-v1-actor-v1":
        raise ValueError(f"Unknown actor schema {payload['schema']}")
    vocab = Vocabulary(payload["vocabulary"])
    actor = MultimodalActor(vocab).to(device)
    actor.load_state_dict(payload["actor"], strict=True)
    return actor.eval(), vocab, payload


class OnlinePolicy:
    def __init__(self, actor, vocabulary, device):
        self.actor = actor.eval()
        self.vocabulary = vocabulary
        self.device = torch.device(device)
        self.proprio_history = deque(maxlen=HISTORY)
        self.previous_history = deque(maxlen=HISTORY)

    @classmethod
    def from_checkpoint(cls, checkpoint, device="cpu"):
        actor, vocab, _ = load_actor(checkpoint, device)
        return cls(actor, vocab, device)

    @torch.inference_mode()
    def reset(self, task_text):
        tokens = torch.tensor([self.vocabulary.encode(task_text)], device=self.device)
        self.text = self.actor.encode_text(tokens)
        self.proprio_history.clear()
        self.previous_history.clear()
        self.tick = 0
        self.visual = None
        self.last_image_time = None

    @torch.inference_mode()
    def step(self, rgb, depth_m, depth_valid, proprio, prev_action, image_age_s=0.0, image_valid=True, *, return_raw=False):
        """Issue one decision; return_raw selects the policy head request before actuator clipping."""
        if not image_valid:
            image_age_s = 0.0
        image_time = self.tick * POLICY_DT - image_age_s if image_valid else None
        changed = (image_time is None) != (self.last_image_time is None)
        if image_time is not None and self.last_image_time is not None:
            changed = abs(image_time - self.last_image_time) > 1e-6
        if self.visual is None or changed:
            if image_valid:
                self.visual = self.actor.encode_visual(*[torch.as_tensor(v, device=self.device)[None]
                                                          for v in (rgb, depth_m, depth_valid)])
            else:
                self.visual = torch.zeros((1, VISUAL_DIM), device=self.device)
            self.last_image_time = image_time
        if not self.proprio_history:
            initial = HISTORY
        else:
            initial = 1
        for _ in range(initial):
            self.proprio_history.append(np.asarray(proprio, dtype=np.float32).copy())
            self.previous_history.append(np.asarray(prev_action, dtype=np.float32).copy())
        sensor = torch.tensor([[image_age_s, float(image_valid), self.tick * POLICY_DT]],
                              dtype=torch.float32, device=self.device)
        def history(values):
            return torch.as_tensor(np.stack(values), device=self.device)[None]
        raw = self.actor.act_features_raw(self.visual, self.text, history(self.proprio_history),
                                          history(self.previous_history), sensor)
        self.tick += 1
        return (raw if return_raw else raw.clamp(-1, 1))[0].cpu().numpy()
