"""Compare the real contact wrench and the learner's reward for two entry actions."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.models import Dynamics

from learning.b0.contact_events import FrozenDoorReference
from learning.b0.contact_model import ContactRepresentation, contact_context, contact_state
from learning.b0.contact_policy import DoorMotions, load_policy
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, ContactMeter, build, settings
from scripts.b0.eval_contact_segments import WarpSingleWorld, ZERO
from scripts.b0.register_contact_dev import prefix_history


@torch.no_grad()
def compare(args):
    device = 'cuda:0'
    paths = [args.references / f'{side}_0_train_grip' for side in ('pull','push')]
    policies = [load_policy(ckpt, paths, device) for ckpt in (args.initial, args.updated)]
    weights = torch.load(args.updated, map_location='cpu', weights_only=False)
    model = build(settings('mobile', 1))
    rep = ContactRepresentation(model, device)
    bank = DoorMotions(paths, rep, device)
    mapping = ActionMap(model)
    dyn = Dynamics(rep, 23, 5, tensor(mapping.scale,device), tensor(mapping.offset,device),
                   tuple(weights['cfg']['wm_hidden'])).to(device)
    dyn.load_state_dict(weights['dyn'])
    dyn.eval()
    rows = []
    for side, path in zip(('pull','push'), paths):
        cfg = settings('mobile' if side == 'pull' else 'push', 1)
        m = build(cfg)
        clock = FrozenDoorReference.from_episode(path, m).phase_bounds['hold'][0] // 10
        warp = WarpSingleWorld(m, device)
        meter = ContactMeter(m, 'preview_floor','front' if side == 'pull' else 'back')
        ctx = contact_context(m, side, device)[None]
        for fraction in (0., .25, .5, .75, 1.):
            d, (hq, hv, ha, prev), admission = prefix_history(m, cfg, path, side, clock*10, ZERO, integrator=warp)
            hq, hv, ha = [np.concatenate((hist[1:], last[None])) for hist,last in
                          zip((hq,hv,ha),(d.qpos.copy(),d.qvel.copy(),prev))]
            commands = [np.clip(policy(path,clock,hq,hv,ha),-1,1) for policy in policies]
            applied = (1-fraction)*commands[0] + fraction*commands[1]
            a = tensor(applied[None],device)
            state = contact_state(tensor(d.qpos[None],device),tensor(d.qvel[None],device))
            predicted_aux, predicted_rep = dyn(rep.represent(state), a, state[:,:7], ctx)
            servo = (mapping.offset+mapping.scale*applied)*mapping.finger_factor
            force = []
            for _ in range(10):
                warp.step(d,servo)
                force.append(float(np.linalg.norm(meter.measure(d).door_force)))
            successor = contact_state(tensor(d.qpos[None],device),tensor(d.qvel[None],device))
            real_rep = rep.represent(successor)
            frame = torch.tensor([bank.starts[path.name]+clock+1],device=device)
            target = bank.body_state(frame)
            rewards = []
            for features, aux in ((real_rep,successor[:,:7]),(predicted_rep,predicted_aux)):
                value = rep.compute_wm_reward_from_reference(features,aux,rep.joint_state(features),
                                                               a,tensor(prev[None],device),*target)
                rewards.append(float(value))
            rows.append(dict(side=side,reference_frame=clock,updated_action_fraction=fraction,
                             prefix_valid_dual_contact=admission['both'],net_force_each_2ms_n=force,
                             first_over_6n_substep=next((i+1 for i,v in enumerate(force) if v>cfg['grip_net_force_limit_n']),None),
                             peak_net_force_n=max(force),real_post_tracking_reward=rewards[0],
                             predicted_post_tracking_reward=rewards[1],
                             tcp_prediction_error_mm=1000*float(torch.linalg.vector_norm(
                                 rep.tcp_pose(successor[:,:7],real_rep[:,10:34])[0]
                                 -rep.tcp_pose(predicted_aux,predicted_rep[:,10:34])[0])),
                             capacity=warp.capacity()))
    return dict(initial=str(args.initial),updated=str(args.updated),world_model=str(args.updated),
                design='Same real 100-substep reconstructed initial history. Convex combinations of clipped Actor first actions. All ten substeps integrated even if the physical evaluation would have terminated. Original successor tracking reward in both model and measured physics.',
                step_reward_ceiling=.1,rows=rows)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial',type=Path,required=True)
    parser.add_argument('--updated',type=Path,required=True)
    parser.add_argument('--references',type=Path,default=Path('results/raw_large/b0/contact_held_r1'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Select a new output file')
    result=compare(args)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
