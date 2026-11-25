"""Frozen u10000 query reconstruction, micro-geometry controls and original reward check."""
import argparse
import os
os.environ.setdefault('TORCH_COMPILE_DISABLE','1')
from pathlib import Path

import mujoco as mj
import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td
from supermimic.utils.tracking_reward import tracking_reward
from learning.b0.contact_events import FrozenDoorReference
from learning.b0.contact_model import ContactRepresentation, contact_state, contact_context
from learning.b0.contact_policy import DoorMotions, build_actor, actor_goal_schema, sensor
from learning.b0.contact_reward import reward_terms, reward_actions
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import make_model, build
from scripts.b0.pregrasp_geometry import case_at, OUT, RAW, OLD, REF, read, write

CKPT=Path('results/raw_large/b0/official_flow_continuation_20261125/checkpoint_010000.pt')
DEVICE='cuda:0'


def variants(hq):
    yield 'base',hq.copy()
    for axis,i in (('x',0),('y',1)):
        for sign in (1,-1):
            q=hq.copy()
            q[:,i]+=.05*sign
            yield axis+('+' if sign>0 else '-'),q
    q=hq.copy()
    a=np.deg2rad(.5)/2
    delta=np.array([np.cos(a),0.,0.,np.sin(a)])
    for i in range(len(q)):
        mj.mju_mulQuat(q[i,3:7],delta,hq[i,3:7])
    yield 'yaw+',q
    q=hq.copy()
    q[:,24]+=.001
    yield 'J2+',q


def scalar(t):
    return float(t.detach().item())


@torch.inference_mode()
def run(recover_first=False):
    if (OUT/'input_alias.json').exists():
        raise FileExistsError(OUT/'input_alias.json')
    weights=torch.load(CKPT,map_location=DEVICE,weights_only=False)
    cfg=weights['cfg']
    common=make_model()
    policy_rep=RobotRepresentation(common,DEVICE)
    contact_rep=ContactRepresentation(common,DEVICE)
    contact_rep.reward_coordinates=cfg['action_rate_coordinates']
    actor,_=build_actor(policy_rep,cfg,common,DEVICE)
    actor.load_state_dict(weights['actor'],strict=True)
    actor.eval()
    bank=DoorMotions([REF/'pull_60_train',REF/'push_25_train'],policy_rep,DEVICE,
                     actor_schema=actor_goal_schema(cfg),reference_tail=cfg['reference_tail'])
    rows=[]
    checks=[]
    for anchor in read(OUT/'states.json')['states']:
        frame,side=anchor['frame'],anchor['side']
        case,raw,_,ref,_=case_at(10000,'warp',side)
        model=build(case['actual_config'])
        assert model.joint('piper_joint2').qposadr.item()==24
        d=mj.MjData(model)
        tcp=model.site('p4_grasp').id
        frozen=FrozenDoorReference.from_episode(ref,model)
        endpoint=frozen.endpoint_pose['pregrasp'][0]
        q,v,acl,raw_act=(np.load(raw/(n+'.npy'),mmap_mode='r') for n in ('qpos','qvel','clipped_action','raw_action'))
        hq=q[frame-9:frame+1]
        vh=tensor(v[frame-9:frame+1],DEVICE)
        previous=tensor(acl[frame-10:frame],DEVICE)
        ctx=contact_context(model,side,DEVICE)[None]
        t=torch.tensor([bank.starts[ref.name]+frame],device=DEVICE)
        data={}
        base=None
        first_anchor = recover_first and side=="pull" and frame==588
        for label,h in variants(hq):
            qh=tensor(h,DEVICE)
            s=full_state(qh,vh)
            hist=sensor(policy_rep,s,previous)[None]
            wm,goal=bank.goals(policy_rep,t,qh[-1:,:7],qh[-1:,31])
            rep=contact_rep.represent(contact_state(qh[-1:],vh[-1:]))
            critic_obs=torch.cat((rep,wm,ctx),dim=-1)
            obs=build_actor_obs_td({'motion':goal},hist)
            reuse_archived = first_anchor and label in ('base','x+','x-','y+','y-')
            action=tensor(raw_act[frame:frame+1].copy(),DEVICE) if reuse_archived else actor.raw(obs)
            if reuse_archived and label!='base':
                action = action if torch.equal(hist,base['raw_history']) and torch.equal(goal,base['raw_goal']) else None
            values=dict(raw_history=hist,normalized_history=actor.obs_normalizer(hist),
                        raw_goal=goal,normalized_goal=actor.goal_normalizers['motion'](goal),
                        critic_input=critic_obs)
            if action is not None:
                values.update(command_raw=action,command_clipped=action.clamp(-1,1))
            if base is None:
                base={k:v.clone() for k,v in values.items()}
            diffs={k:scalar((v-base[k]).abs().max()) for k,v in values.items()}
            d.qpos[:]=h[-1]
            mj.mj_kinematics(model,d)
            diff=(d.site_xpos[tcp]-endpoint)
            row=dict(side=side,frame=frame,variant=label,max_abs_delta=diffs,
                     tcp_minus_endpoint_world_m=diff.tolist(),tcp_endpoint_distance_m=float(np.linalg.norm(diff)),
                     auxiliary_loss=None if reuse_archived else scalar(actor.auxiliary_loss().mean()),
                     action_source=("archived formal baseline identity" if label=="base" else "identical reconstructed input; retained archived action" if action is not None else "unavailable") if reuse_archived else "direct frozen query")
            if label=='base':
                row['max_abs_raw_command_vs_archived']=float(np.max(np.abs(raw_act[frame]-action.cpu().numpy()[0])))
                assert row['max_abs_raw_command_vs_archived'] < 2e-5
            if label in ('x+','x-','y+','y-'):
                print(side,frame,label,diffs,flush=True)
            elif label!='base':
                assert diffs['raw_history'] or diffs['raw_goal']
            for k,val in values.items():
                data[label+'_'+k]=val.cpu().numpy()
            rows.append(row)
        # Same measured successor and true previous action in both scalar computations.
        q1,v1=tensor(q[frame+1:frame+2].copy(),DEVICE),tensor(v[frame+1:frame+2].copy(),DEVICE)
        aux=q1[:,:7]
        rep=contact_rep.represent(contact_state(q1,v1))
        acts=tensor(acl[frame:frame+1].copy(),DEVICE)
        last=previous[-1:]
        target=bank.body_state(t+1)
        terms=reward_terms(contact_rep,rep,aux,acts,last,target,coordinates=cfg['action_rate_coordinates'])
        unscaled=reward_actions(contact_rep,acts,last,cfg['action_rate_coordinates'])
        original=tracking_reward(aux,*contact_rep.world_frame_bodies(aux,rep),contact_rep.joint_state(rep),
                                 *unscaled,*target,contact_rep._soft_joint_pos_limits,contact_rep.dt)
        checks.append(dict(side=side,frame=frame,reward_successor_frame=frame+1,
                           terms={k:scalar(v) for k,v in terms.items()},official_reward=scalar(original),
                           signed_terms_sum=scalar(sum(terms.values())),residual=scalar(sum(terms.values())-original)))
        assert abs(checks[-1]['residual'])<1e-6
        np.savez_compressed(RAW/f'alias_{side}_{frame}.npz',**data)
    assert len(rows)==7*len(checks)<=28
    write('input_alias.json',dict(checkpoint=str(CKPT),direct_query_count_current_pass=len(rows)-5 if recover_first else len(rows),
        reconstructed_input_variants=len(rows),physics_calls=0,
        first_anchor_recovery=bool(recover_first),
        history='Full archived q/v/previous command from last ten absolute boundaries; current frame uses previous command. All perturbations applied to the entire q history, velocities/commands/reference/door fixed.',
        outputs='Cumulative infinity norms relative to same-anchor baseline, same frozen weights and normalizers. Critic receives concat(75,570,5). Raw arrays per anchor under raw_large/pregrasp directory.',
        reachability='Synthetic counterfactual input and FK. Opposite signed TCP residuals imply opposite geometric displacement for fixed absolute endpoint in that coordinate, not opposite proven optimal motor commands or physically sampled mirror states.',
        rows=rows))
    write('original_objective_terms.json',dict(
        pinned_supermimic='abc124c1bd5976341034668af3d12c087f2f1f55',
        pinned_mjlab_research='dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd',
        parent='79fd3cf876c126e74d862e34e2638495705098e7', checkpoint=str(CKPT),
        sources={'goal':'vendor/b0/supermimic/src/supermimic/representations.py:compute_wm_goal; learning/b0/contact_policy.py:DoorMotions.goals',
                 'sensor':'learning/b0/contact_policy.py:sensor; learning/b0/model.py:RobotRepresentation',
                 'reward':'vendor/b0/supermimic/src/supermimic/utils/tracking_reward.py:tracking_reward,_reanchor_targets; learning/b0/contact_reward.py:reward_actions,reward_terms',
                 'successor':'learning/b0/contact_training.py:DoorImagination._update_goal',
                 'termination':'vendor/b0/supermimic/src/supermimic/envs/world_model_env.py:_compute_term_prob',
                 'bootstrap':'vendor/b0/supermimic/src/supermimic/learners/policy_learner.py:ActorCriticPolicyLearner._bootstrap',
                 'configuration':'learning/b0/contact_training.py:ContactRun and parent interface.json'},
        current_state_dimensions=dict(history=[10,77],actor_goal=540,critic_state=75,critic_goal=570,ctx=5),
        reanchor='Body pose target uses predicted XY and relative yaw; reference anchor Z and roll/pitch retained. Anchor position and orientation terms score the original absolute target.',
        six_kernel_weights_widths=dict(anchor_position=[.5,.3],anchor_orientation=[.5,.4],
            body_position=[1.,.3],body_orientation=[1.,.4],body_linear_velocity=[1.,1.],body_angular_velocity=[1.,3.14]),
        action_rate='-dt * 0.1 * squared norm of effort-space current minus previous (canonical-home)/unit',
        joint_limit='-dt * 2 * sum of linear excess beyond soft joint position limits',
        termination='sigmoid((max(abs(root_z-ref_z)/0.1, abs(gravity_z-ref_gravity_z)/0.12)-1)/0.05); soft survival multiplier (1-p)',
        return_formula='sum_t gamma^t survive_before_t reward_t, plus gamma^32 survive_32 min(critic_observation_value, max_step_reward/(1-gamma)); gamma=.99. Auxiliary latent BC separate, motion=1 velocity=0.',
        event='Original pregrasp threshold 0.003m, 0.02rad, 0.15s; 0.3m Gaussian width has different role.',
        fixed_measured_successor_checks=checks))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recover-first',action='store_true',
        help='Recorded interrupted execution: avoid redundant first-anchor queries before the independent numerical readback.')
    run(parser.parse_args().recover_first)
