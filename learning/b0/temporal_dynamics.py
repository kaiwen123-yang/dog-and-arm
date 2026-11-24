"""Two registered GenCoord time resolutions for a 20 ms held command."""
from supermimic.models import Dynamics

from .contact_model import ContactRepresentation
from .model import tensor


class MicroRepresentation(ContactRepresentation):
    def __init__(self, model, device):
        super().__init__(model, device)
        self.dt = .002
        self.substep_coeff = 1.

    def apply_prediction(self, aux_state, curr_rep_state, prediction, dt):
        return super().apply_prediction(aux_state, curr_rep_state, prediction * .1, dt)


class TenStepDynamics(Dynamics):
    def inner_step(self, rep_state, action, aux_state, sim_ctx):
        return super().forward(rep_state, action, aux_state, sim_ctx)

    def forward(self, rep_state, action, aux_state, sim_ctx):
        for _ in range(10):
            aux_state, rep_state = self.inner_step(rep_state, action, aux_state, sim_ctx)
        return aux_state, rep_state


def make_dynamics(model, rep, mapping, hidden, temporal_id, device):
    if temporal_id == 'T2':
        dynamics, integration = TenStepDynamics, MicroRepresentation(model, device)
    elif temporal_id == 'C20':
        dynamics, integration = Dynamics, rep
    else:
        raise ValueError(f'Unknown time resolution {temporal_id}')
    return dynamics(integration, 23, 5, tensor(mapping.scale, device),
                    tensor(mapping.offset, device), tuple(hidden)).to(device)
