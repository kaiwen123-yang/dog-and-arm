"""A single fitted scalar maps reference-root translation through the given arm motion's Jacobian."""
import argparse
import contextlib
import json
from pathlib import Path
import subprocess
import sys

import mujoco as mj
import numpy as np

from learning.b0.physics import ActionMap, build, settings
from scripts.b0.eval_contact_segments import evaluate_segment
from scripts.b0.recovery_backend_probe import DEFAULT_SOURCE

NAMES = ('pull_60_train', 'push_25_train')


from learning.b0.stance_arm import ReferenceArmMap


def reference_map(path):
    model = build(settings('mobile' if path.name.startswith('pull') else 'push',1))
    return ReferenceArmMap(model, np.load(path/'qpos.npy',mmap_mode='r'))


def fit(args):
    import torch
    from learning.b0.contact_policy import DoorMotions, build_actor
    from learning.b0.model import RobotRepresentation
    from scripts.b0.recovery_backend_fit import CONTACT_PHASES, clock_signals, features
    m = build(settings('mobile',1))
    rep = RobotRepresentation(m,'cpu')
    ck = torch.load(args.checkpoint,map_location='cpu',weights_only=False)
    actor,_ = build_actor(rep,ck['cfg'],m,'cpu')
    actor.load_state_dict(ck['actor'],strict=True)
    actor.eval()
    bank = DoorMotions([args.references/n for n in NAMES],rep,'cpu')
    groups = []
    for name in NAMES:
        path,native = args.references/name,args.native_teacher/name
        n=min(int(np.load(p/'valid_full_interval.npy').sum()) for p in (path,native))
        wp,wt,wR=clock_signals(path,n)
        np_,nt,nR=clock_signals(native,n)
        dx=np.linalg.norm(wt-nt,axis=1)
        dr=np.rad2deg(np.arccos(np.clip(((wR*nR).sum((1,2))-1)/2,-1,1)))
        frames=np.flatnonzero((wp==np_)&np.isin(wp,CONTACT_PHASES)&(dx<=.002)&(dr<=1.))
        geom=reference_map(path)
        _,pred,y=features(native,frames,bank,rep,actor)
        measured_root=np.load(native/'qpos.npy',mmap_mode='r')[frames,:3]
        direction=geom.direction(frames,measured_root)
        residual=(y-pred).numpy()*geom.scale
        groups.append((name,direction,residual))
    ab=sum((a*b).mean() for _,a,b in groups)
    aa=sum((a*a).mean() for _,a,b in groups)
    coeff=float(np.clip(ab/aa,0,1))
    spec=dict(source=str(args.checkpoint), references=str(args.references), native_teacher=str(args.native_teacher),
              variant='privileged_reference_translation_arm_map', coefficient=coeff,
              unconstrained_coefficient=float(ab/aa), objective='equal weight per side over the same-clock, same-phase, <=2mm and <=1deg physical teacher label rows; coefficient in [0,1]; no score/case used for training',
              inputs='current measured world root XYZ minus fixed reference; precomputed reference spatial Jacobian. No engine identifier, observed contact, future simulation, IK teacher or online action labels.',
              parameterization='Use reference minus actual displacement; damped 6D arm Jacobian, orientation weight 0.12m, damping 0.01, per-joint clip +/-0.05 rad, smooth gain for stowed reference arm. All source Actor parameters remain frozen.',
              H32_updates=0, deploy='scripts.b0.recovery_backend_stance eval', rows={})
    for name,a,b in groups:
        spec['rows'][name]=dict(count=len(a),before_rmse_rad=float(np.sqrt((b*b).mean())),
                                after_rmse_rad=float(np.sqrt(((coeff*a-b)**2).mean())))
    out=Path('results/b0')/args.run
    out.mkdir(parents=True,exist_ok=False)
    (out/'fit.json').write_text(json.dumps(spec,indent=2,allow_nan=False)+'\n')
    ck['stance_arm_head']=spec
    torch.save(ck,out/'checkpoint_000000.pt')
    print(json.dumps(spec))


@contextlib.contextmanager
def actor_client(checkpoint, paths, device):
    if mj.__version__ != '3.3.0':
        from learning.b0.contact_policy import load_policy
        yield load_policy(checkpoint,paths,device)
        return
    worker = Path(__file__).with_name('eval_contact_segments.py')
    process = subprocess.Popen(['bash','scripts/b0/env.sh','python','-u',str(worker),'--actor-worker',
                                '--checkpoint',str(checkpoint),'--device','cpu'],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    def write(payload):
        process.stdin.write(json.dumps(payload,allow_nan=False)+'\n')
        process.stdin.flush()
    write(dict(paths=[str(p) for p in paths]))
    def infer(path,frame,q,v,a):
        write(dict(path=str(path),frame=frame,q=q.tolist(),v=v.tolist(),a=a.tolist()))
        return np.array(json.loads(process.stdout.readline()))
    try:
        yield infer
    finally:
        process.stdin.close()
        if process.wait():
            raise RuntimeError('Actor worker failed')


def evaluate(args):
    if args.engine=='native33' and mj.__version__!='3.3.0' or args.engine!='native33' and mj.__version__!='3.16.0':
        raise ValueError('Use the corresponding MuJoCo interpreter')
    # The portable JSON (readable by the 3.3 environment) and Actor checkpoint
    # are emitted together in one fit directory, never taken from separate runs.
    spec=json.loads((args.checkpoint.parent/'fit.json').read_text())
    if spec['variant']!='privileged_reference_translation_arm_map' or spec['references']!=str(args.references):
        raise ValueError('Wrong fitted candidate or reference bank')
    paths=[args.references/n for n in NAMES]
    device='cuda:0' if args.engine=='warp316' else 'cpu'
    backend='warp' if args.engine=='warp316' else 'native'
    out=Path('results/b0')/args.run
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    with actor_client(args.checkpoint,paths,device) as frozen:
        for path,side in zip(paths,('pull','push')):
            geom=reference_map(path)
            def policy(episode,frame,hq,hv,ha):
                raw=frozen(episode,frame,hq,hv,ha).copy()
                raw[16:22]+=spec['coefficient']*geom.direction(frame,hq[-1,:3])/geom.scale
                return raw
            for case in args.cases:
                folder=Path(side)/'full'/('nominal' if case==1 and args.cases==[1] else f'C{case:02}')
                r=evaluate_segment(policy,path,'full',{'p6_case':case},backend,out/folder,device=device,
                                   raw_dir=Path('results/raw_large/b0')/args.run/folder,video=args.video,
                                   action_source='frozen reference residual Actor plus fitted privileged stance arm head')
                rows.append({k:r[k] for k in ('side','perturbation','passed','physics_steps','final_door_deg','first_failure')})
                print(json.dumps(rows[-1]),flush=True)
    (out/'evaluation.json').write_text(json.dumps(dict(checkpoint=str(args.checkpoint),head=spec,engine=args.engine,
        selected_cases=args.cases,results=rows),indent=2,allow_nan=False)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('fit','eval'))
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--references',type=Path,default=DEFAULT_SOURCE)
    p.add_argument('--native-teacher',type=Path,default=Path('results/raw_large/b0/full_native_margin_r1'))
    p.add_argument('--engine',choices=('native33','cpu316','warp316'),default='cpu316')
    p.add_argument('--cases',type=int,nargs='+',default=[1])
    p.add_argument('--run',required=True)
    p.add_argument('--video',action='store_true')
    args=p.parse_args()
    if Path(args.run).name!=args.run or any(c<1 or c>20 for c in args.cases):
        p.error('Choose a fresh run name and development case numbers 1 through 20')
    (fit if args.mode=='fit' else evaluate)(args)


if __name__=='__main__':
    main()
