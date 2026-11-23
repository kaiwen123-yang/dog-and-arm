"""Append the six stance-map inputs to a frozen 540/570/571-input Actor package."""
import argparse
import json
from pathlib import Path
import os

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import (ARM_MAP_BASES, DoorMotions, actor_goal_schema,
                                        build_actor, sensor)
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import make_model
from learning.b0.stance_arm import ReferenceArmMap

NAMES = ('pull_60_train','push_25_train')


def migrate(state, expanded):
    new = expanded.state_dict()
    fields = {'encoders.motion.0.weight':0., 'goal_normalizers.motion._mean':0.,
              'goal_normalizers.motion._std':.05, 'goal_normalizers.motion._var':.05**2}
    if new.keys() != state.keys():
        raise ValueError('Unexpected parameter keys')
    for key,item in state.items():
        if item.shape == new[key].shape:
            new[key] = item
        else:
            if (key not in fields or item.shape[:-1] != new[key].shape[:-1]
                    or item.shape[-1]+6 != new[key].shape[-1]):
                raise ValueError(f'Unexpected input migration at {key}')
            new[key].fill_(fields[key])
            new[key][..., :-6].copy_(item)
    expanded.load_state_dict(new,strict=True)


def verify(args, old, new, cfg, rep, model):
    """Check deployed action, measured root, and the predicted-root partial derivative."""
    paths=[args.references/n for n in NAMES]
    banks=[DoorMotions(paths,rep,'cpu',actor_schema=s) for s in
           (ARM_MAP_BASES[cfg['actor_goal_schema']],cfg['actor_goal_schema'])]
    report={}
    for p in paths:
        idx=np.arange(80, int(np.load(p/'valid_full_interval.npy').sum()), 91)
        q=np.load(p/'qpos.npy',mmap_mode='r')
        v=np.load(p/'qvel.npy',mmap_mode='r')
        a=np.load(p/'last_action.npy',mmap_mode='r')
        hist=np.maximum(idx[:,None]+np.arange(-9,1),0)
        hq=tensor(q[hist].copy(),'cpu')
        hv=tensor(v[hist].copy(),'cpu')
        ha=tensor(a[hist].copy(),'cpu')
        offset=np.array([.001,-.002,.0005])
        hq[:,:,:3]+=tensor(offset,'cpu')
        histories=sensor(rep,full_state(hq,hv),ha)
        frames=torch.tensor(idx)+banks[0].starts[p.name]
        aux=hq[:,-1,:7].clone().requires_grad_(True)
        angle=hq[:,-1,31]
        _,base=banks[0].goals(rep,frames,aux,angle)
        _,adapt=banks[1].goals(rep,frames,aux,angle)
        ref=ReferenceArmMap(model,q)
        delta=ref.direction(idx,aux.detach().numpy()[:,:3])
        with torch.no_grad():
            x=old.raw(build_actor_obs_td({'motion':base},histories))
            y=new.raw(build_actor_obs_td({'motion':adapt},histories))
            x[:,16:22]+=tensor(delta,'cpu')*cfg['stance_arm_gain']/old.reference_scale[:6]
            action_diff=float((x-y).abs().max())
        # Compute the six partials on the same aux variable passed to the
        # differentiable imagination path. Include the clip's true derivative.
        analytic=[]
        for c in range(6):
            deriv=torch.autograd.grad(adapt[:,-6+c].sum(),aux,retain_graph=True)[0]
            analytic.append(deriv[:,:3].numpy())
        analytic=np.stack(analytic,axis=1)
        root=aux.detach().numpy()[:,:3].astype('f8')
        eps=1e-6
        fd=np.stack([(ref.direction(idx,root+b*eps)-ref.direction(idx,root-b*eps))/(2*eps)
                     for b in np.eye(3)],axis=-1)
        err=float(abs(analytic-fd).max())
        report[p.name]=dict(frames=len(idx),base_columns_unchanged=bool(torch.equal(base,adapt[:,:-6])),
                            max_action_difference=action_diff,max_arm_map_derivative_difference_rad_per_m=err,
                            max_abs_root_derivative_rad_per_m=float(abs(analytic).max()))
        # The standalone reference subtraction is float64, whereas H32 and its
        # physics observations use float32, including the supplied bank of roots.
        if not torch.equal(base,adapt[:,:-6]) or action_diff>2e-5 or err>5e-4 or not np.isfinite(analytic).all():
            raise RuntimeError(report[p.name])
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--fit',type=Path,required=True)
    parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--run',required=True)
    args=parser.parse_args()
    if Path(args.run).name!=args.run:
        parser.error('Use a fresh run name')
    src=torch.load(args.source,map_location='cpu',weights_only=False)
    fit=json.loads(args.fit.read_text())
    if (fit['variant'] != 'privileged_reference_translation_arm_map'
            or fit['references'] != str(args.references) or src['seed'] != 0
            or not 0 <= fit['coefficient'] <= 1):
        raise ValueError('Expected the seed0 fitted scalar and its declared common reference')
    coef=fit['coefficient']
    cfg=dict(src['cfg'])
    model=make_model()
    rep=RobotRepresentation(model,'cpu')
    old,_=build_actor(rep,cfg,model,'cpu')
    old.load_state_dict(src['actor'],strict=True)
    old.eval()
    base=actor_goal_schema(cfg)
    inverse={v:k for k,v in ARM_MAP_BASES.items()}
    cfg.update(actor_goal_schema=inverse[base],stance_arm_gain=coef)
    new,_=build_actor(rep,cfg,model,'cpu')
    migrate(src['actor'],new)
    new.eval()
    audit=verify(args,old,new,cfg,rep,model)
    widths=[a.encoders['motion'][0].in_features for a in (old,new)]
    out=Path('results/b0')/args.run
    out.mkdir(parents=True,exist_ok=False)
    record=dict(source=str(args.source),fit=str(args.fit),base=base,schema=cfg['actor_goal_schema'],
                width_before=widths[0],width_after=widths[1],unchanged_columns=widths[0],
                appended='Six reference-Jacobian arm displacements (rad); measured or imagined current root, same map and fixed reference',
                encoder_new_weights=0,new_normalizer_mean=0,new_normalizer_std_rad=.05,coefficient=coef,
                audit=audit,additional_bc_or_h32_updates=0)
    src.update(cfg=cfg,actor=new.state_dict(),stance_arm_fit=record)
    torch.save(src,out/'checkpoint_000000.pt')
    (out/'package.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print(json.dumps(record,allow_nan=False))


if __name__=='__main__':
    main()
