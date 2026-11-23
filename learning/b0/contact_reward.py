"""Action units for pinned SuperMimic tracking, plus its signed components for physical scoring."""
import torch
from mjlab.utils.lab_api.math import matrix_from_quat
from supermimic.utils.helpers import rotation_error_magnitude
from supermimic.utils.tracking_reward import _reanchor_targets


def reward_actions(rep, action, previous_action, coordinates, previous_valid=True):
    if coordinates == 'fixed_effort':
        action = (action - rep.reward_home) / rep.reward_unit
        previous_action = (previous_action - rep.reward_home) / rep.reward_unit
    elif coordinates != 'canonical':
        raise ValueError(f'Unknown action-rate coordinates {coordinates}')
    # A real canonical zero command is valid. Only the reset signal means no history.
    if previous_valid is not True:
        valid = torch.as_tensor(previous_valid, device=action.device, dtype=torch.bool)
        previous_action = torch.where(valid[..., None], previous_action, 0.)
    return action, previous_action


def reward_terms(rep, successor_rep, successor_aux, action, previous_action, target_bodies,
                 *, coordinates, previous_valid=True, dt=None):
    """Signed, dt-weighted summands of abc124c tracking_reward, on the measured successor."""
    dt = rep.dt if dt is None else dt
    pos, rot, lin, ang = rep.world_frame_bodies(successor_aux, successor_rep)
    target_pos, target_quat, target_lin, target_ang = target_bodies
    relative_pos, relative_rot = _reanchor_targets(
        target_pos, target_quat, successor_aux[..., :3], successor_aux[..., 3:7])
    def squared(x):
        return x.square().sum(-1)
    def kernel(error, weight, width):
        return dt * weight * torch.exp(-error / width**2)
    act, prev = reward_actions(rep, action, previous_action, coordinates, previous_valid)
    joint_pos, _ = rep.joint_state(successor_rep).chunk(2, -1)
    lo, hi = rep._soft_joint_pos_limits.unbind(-1)
    return dict(
        anchor_position=kernel(squared(pos[..., 0, :] - target_pos[..., 0, :]), .5, .3),
        anchor_orientation=kernel(rotation_error_magnitude(
            rot[..., 0, :, :], matrix_from_quat(target_quat[..., 0, :])).square(), .5, .4),
        body_position=kernel(squared(pos - relative_pos).mean(-1), 1., .3),
        body_orientation=kernel(rotation_error_magnitude(rot, relative_rot).square().mean(-1), 1., .4),
        body_linear_velocity=kernel(squared(lin - target_lin).mean(-1), 1., 1.),
        body_angular_velocity=kernel(squared(ang - target_ang).mean(-1), 1., 3.14),
        action_rate=-dt * .1 * squared(act - prev),
        joint_limit=-dt * 2. * ((lo - joint_pos).clamp_min(0) + (joint_pos - hi).clamp_min(0)).sum(-1),
    )
