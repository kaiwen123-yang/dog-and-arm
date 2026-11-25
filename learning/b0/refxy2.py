"""Current-query body-frame XY tail and its fixed-scale normalization contract."""
import torch
from supermimic.models import _CudaGraphNormalization

MODES = {"refxy2_measured": "measured", "refxy2_zero": "zero"}


def append_refxy2(goal, reference_root, aux, mode):
    if mode == "zero":
        return torch.cat((goal, torch.zeros_like(aux[..., :2])), dim=-1)
    if mode != "measured":
        raise ValueError(mode)
    dx, dy = (reference_root[..., :2] - aux[..., :2]).unbind(-1)
    w, x, y, z = aux[..., 3:7].unbind(-1)
    yaw = torch.atan2(2 * (w*z + x*y), 1 - 2 * (y*y + z*z))
    c, s = yaw.cos(), yaw.sin()
    tail = torch.stack((c*dx + s*dy, c*dy - s*dx), dim=-1) / 0.05
    return torch.cat((goal, tail), dim=-1)


class RefXY2Normalization(_CudaGraphNormalization):
    def forward(self, goal):
        return torch.cat((super().forward(goal[..., :540]), goal[..., 540:]), dim=-1)

    def update(self, goal):
        super().update(goal[..., :540])
