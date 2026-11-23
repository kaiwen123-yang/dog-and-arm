"""Local frozen-WM and real 3.3.0 action responses on measured grasped states."""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import mujoco as mj
import numpy as np
from learning.b0.physics import ActionMap, make_model
from p6_scene import build


def measure_native(root):
    if mj.__version__ != '3.3.0':
        raise RuntimeError('Use the original 3.3.0 runtime for finite differences')
    rows = []
    for side in ('pull','push'):
        path = root / (side + '_5_validation')
        meta = json.loads((path/'metadata.json').read_text())
        model = build(json.loads((path/'config.json').read_text()))
        data = mj.MjData(model)
        mapping = ActionMap(model)
        actions = np.load(path/'action_clipped.npy')
        phases = np.load(path/'phase.npy')
        hold = np.flatnonzero(phases==meta['phases'].index('hold'))
        start = int(hold[len(hold)//2])
        q = np.load(path/'qpos.npy')
        v = np.load(path/'qvel.npy')
        data.qpos[:], data.qvel[:] = q[start-10], v[start-10]
        mj.mj_forward(model,data)
        def step(d, action):
            target = (mapping.offset+action*mapping.scale)*mapping.finger_factor
            for _ in range(10):
                d.ctrl[mapping.actuator_ids] = target + d.qfrc_bias[mapping.dof]*mapping.bias_gain
                mj.mj_step(model,d)
        for command in actions[start-10:start]:
            step(data,command)
        baseline = q[start, -1]
        for act_index, delta_phys in ((20,.001),(22,.00025)):
            delta = delta_phys/mapping.scale[act_index]
            outputs = []
            for sign in (-1, 0, 1):
                branch = copy.copy(data)
                path_actions = actions[start:start+7].copy()
                path_actions[0,act_index] += sign*delta
                if np.abs(path_actions).max()>1.+1e-12:
                    raise ValueError('finite difference crosses a clamp')
                for command in path_actions:
                    step(branch,command)
                mj.mj_kinematics(model,branch)
                outputs.append(np.r_[branch.qpos[-1], branch.site('p4_grasp').xpos].tolist())
            rows.append(dict(side=side,episode=path.name,action_index=act_index,action_name=mapping.names[act_index],
                             command_delta_physical=delta_phys,command_delta_normalized=delta,reference_start=start,
                             physical_prefix_substeps=100,q_start=data.qpos.tolist(),v_start=data.qvel.tolist(),
                             prefix_terminal_qpos_max_dev=float(np.abs(data.qpos-q[start]).max()),
                             source_door_q_rad=float(baseline),actions=actions[start:start+7].tolist(),
                             physical_minus_center_plus=outputs))
    return rows


def compare_model(path, checkpoint):
    import torch
    from supermimic.models import Dynamics
    from learning.b0.contact_model import ContactRepresentation, contact_state, contact_context, CONTEXT_NAMES
    from learning.b0.model import tensor
    model=make_model()
    rep=ContactRepresentation(model,'cpu')
    mapping=ActionMap(model)
    ckpt=torch.load(checkpoint,map_location='cpu',weights_only=False)
    hidden = ckpt['hidden'] if 'hidden' in ckpt else ckpt['cfg']['wm_hidden']
    dyn=Dynamics(rep,23,len(CONTEXT_NAMES),tensor(mapping.scale,'cpu'),tensor(mapping.offset,'cpu'),tuple(hidden))
    dyn.load_state_dict(ckpt['dyn'])
    dyn.eval().requires_grad_(False)
    rows=[]
    for row in json.loads(path.read_text()):
        q=tensor([row['q_start']],'cpu')
        v=tensor([row['v_start']],'cpu')
        state=contact_state(q,v)
        action=tensor(row['actions'],'cpu').requires_grad_()
        r, aux=rep.represent(state), state[:,:7]
        ctx=contact_context(model,row['side'],'cpu')[None]
        for a in action:
            aux,r=dyn(r,a[None],aux,ctx)
        out=torch.cat((r[:,58:59],rep.tcp_pose(aux,r[...,10:34])[0]),-1)[0]
        gradients=[torch.autograd.grad(x,action,retain_graph=True)[0][0,row['action_index']].item() for x in out]
        minus,center,plus=np.array(row['physical_minus_center_plus'])
        slope=(plus-minus)/(2*row['command_delta_normalized'])
        rows.append(dict(side=row['side'],episode=row['episode'],start=row['reference_start'],action=row['action_name'],
                         delta_physical=row['command_delta_physical'],delta_normalized=row['command_delta_normalized'],
                         outputs=['door_rad','tcp_x_m','tcp_y_m','tcp_z_m'],
                         true_gradient_per_normalized_action=slope.tolist(),
                         wm_gradient_per_normalized_action=gradients,
                         native_nonlinearity_plus_minus=abs(plus+minus-2*center).tolist(),
                         native_minus_center_plus=row['physical_minus_center_plus'],
                         wm_endpoint=out.detach().tolist(),
                         prefix_terminal_qpos_max_dev=row['prefix_terminal_qpos_max_dev']))
    return dict(checkpoint=str(checkpoint),horizon=7,initialization_prefix_substeps=100,
                derivative='central native same solver state, delta on first command only; WM autograd on that state',cases=rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native-data',type=Path)
    p.add_argument('--native-record',type=Path)
    p.add_argument('--checkpoint',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists():
        p.error('Choose a new output')
    result=measure_native(a.native_data) if a.native_data else compare_model(a.native_record,a.checkpoint)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    main()
