"""Predict the maximum 2 ms door/robot resultant in a single 20 ms action."""
import torch
from torch import nn


class PeakDoorForce(nn.Module):
    """Current geometry and held servo errors only; no future physics input."""

    def __init__(self, mapping, device):
        super().__init__()
        self.register_buffer('scale', torch.as_tensor(mapping.scale, device=device, dtype=torch.float32))
        self.register_buffer('offset', torch.as_tensor(mapping.offset, device=device, dtype=torch.float32))
        self.register_buffer('pos_columns', torch.as_tensor(mapping.q[16:22]-7, device=device))
        self.net = nn.Sequential(nn.Linear(35, 128), nn.SiLU(), nn.Linear(128, 128),
                                 nn.SiLU(), nn.Linear(128, 1), nn.Softplus()).to(device)

    def forward(self, rep, action, context):
        side = context[..., :1]
        rod = torch.where(side.bool(), rep[..., 66:69], rep[..., 63:66])
        pos, vel = rep[..., 10:34], rep[..., 34:58]
        arm = pos.index_select(-1, self.pos_columns)
        arm_v = vel.index_select(-1, self.pos_columns)
        goal = action*self.scale+self.offset
        fingers = pos[..., -2:]
        inputs = torch.cat((side, rod*100, rep[..., 69:75], arm, arm_v,
                            (goal[..., 16:22]-arm)*50, fingers*100,
                            vel[..., -2:]*10, (goal[..., 22:23]-fingers[..., :1]+fingers[..., 1:])*200,
                            rep[..., 58:60]), dim=-1)
        return self.net(inputs).squeeze(-1)
