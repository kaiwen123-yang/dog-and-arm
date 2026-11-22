"""Closed-loop contact segment evaluation with a frozen Actor and read-only physical events."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from learning.b0.physics import ActionMap, build, settings
from scripts.b0.register_contact_dev import SEGMENTS, prefix_history, valid_initial

ZERO = dict(dx_m=0., dy_m=0., dyaw_deg=0.)


class WarpSingleWorld:
    """Each interval is integrated by Warp. CPU reads the solved snapshot only."""
    def __init__(self, model, device):
        import mujoco_warp as mjw
        import torch
        from learning.b0.research_env import ResearchPlant
        self.m, self.torch, self.mjw, self.device = model, torch, mjw, device
        self.plant = ResearchPlant(model,1,device)
        self.max_nefc = self.max_nacon = self.overflow_bits = 0

    def tensor(self,x):
        return self.torch.as_tensor(x,dtype=self.torch.float32,device=self.device)

    def reset(self,data):
        self.plant.reset(self.tensor(data.qpos[None]), self.tensor(data.qvel[None]))
        self.max_nefc = self.max_nacon = self.overflow_bits = 0

    def step(self,data,servo):
        p = self.plant
        p.data.ctrl[:,p.actuator_ids] = self.tensor(servo)[None] + p.data.qfrc_bias[:,p.dof] * p.bias_gain
        p.sim.step()
        source = p.sim.wp_data
        self.mjw.get_data_into(data,self.m,source,world_id=0)
        bits = int(p.contact_audit.overflow_bits[0])
        self.overflow_bits |= bits
        self.max_nefc = max(self.max_nefc, data.nefc)
        self.max_nacon = max(self.max_nacon, data.ncon)
        if (bits & p.contact_audit.buffer_mask) or data.nefc > source.njmax or data.ncon > source.naconmax:
            raise RuntimeError(f'Warp constraint/contact capacity exceeded, flags={bits}')

    def capacity(self):
        d=self.plant.sim.wp_data
        return dict(nconmax=int(d.naconmax),njmax=int(d.njmax),observed_peak_nefc=self.max_nefc,
                    observed_peak_ncon=self.max_nacon,overflow_bits=int(self.overflow_bits),
                    buffer_overflow_bits=int(self.overflow_bits & self.plant.contact_audit.buffer_mask))


def save_video(model,qpos,steps,destination):
    import imageio.v2 as imageio
    scratch = mj.MjData(model)
    with mj.Renderer(model,height=288,width=512) as renderer:
        with imageio.get_writer(destination,fps=25,codec='libx264',quality=7,ffmpeg_log_level='error') as writer:
            for i,(q,step) in enumerate(zip(qpos,steps)):
                if step % 20 != 0 and i != len(steps)-1:
                    continue
                scratch.qpos[:] = q
                mj.mj_forward(model,scratch)
                renderer.update_scene(scratch,camera='p6_overview')
                writer.append_data(renderer.render())


def evaluate_segment(policy_fn, episode_path, segment, perturbation, backend, output=None, *,
                     model=None, integrator=None, device='cuda:0', raw_dir=None, video=False, action_source='frozen Actor raw output then clamp'):
    path=Path(episode_path)
    meta=json.loads((path/'metadata.json').read_text())
    side = meta['task']
    goal, phases=SEGMENTS[segment]
    if meta['target_angle_deg']!=goal or not meta['success'] or meta['wm_split']!='train':
        raise ValueError(f'expected successful training reference for {segment}: {path}')
    cfg=settings('mobile' if side=='pull' else 'push',1)
    cfg['target_angle_deg']=goal
    model = build(cfg) if model is None else model
    if backend not in ('warp','native'):
        raise ValueError(f'unknown backend {backend}')
    if backend == 'warp' and integrator is None:
        integrator=WarpSingleWorld(model,device)
    ref=FrozenDoorReference.from_episode(path,model)
    start=ref.phase_bounds[phases[0]][0] // 10 * 10
    end=ref.phase_bounds[phases[-1]][1]
    # The recorded segment has an exact terminal substep. No extension into
    # later phases or repeated final frame can supply extra holding time.
    max_step=end
    judge=ContactEvents(model,cfg,side,ref,phases=phases,hold_seconds=3.,start_step=start)
    mapping=ActionMap(model)
    d, (hq,hv,ha,previous), metrics=prefix_history(model,cfg,path,side,start,perturbation,integrator=integrator)
    result=dict(episode=meta['episode_id'],side=side,segment=segment,backend=backend,mujoco=mj.__version__,action_source=action_source,
                start_substep=start,reference_phase_end_substep=end,reference_last_substep=max_step,
                prefix_physics_steps=100,perturbation=perturbation,initial_geometry=metrics,
                passed=False,first_failure=None,events=[],policy_calls=0,physics_steps=0)
    if not valid_initial(metrics,segment,cfg):
        result['first_failure']=dict(reason='initial_contact_reconstruction',phase=phases[0])
    qlog=[d.qpos.copy()]
    vlog=[d.qvel.copy()]
    ticks=[0]
    raw_log, clipped_log=[],[]
    while result['first_failure'] is None and not judge.passed and start+judge.step < max_step:
        current_q, current_v=d.qpos.copy(),d.qvel.copy()
        hq=np.concatenate((hq[1:],current_q[None]))
        hv=np.concatenate((hv[1:],current_v[None]))
        ha=np.concatenate((ha[1:],previous[None]))
        frame=(start+judge.step)//10
        raw=np.asarray(policy_fn(path,frame,hq,hv,ha),dtype=np.float64)
        if raw.shape!=(23,) or not np.isfinite(raw).all():
            result['first_failure']=dict(reason='invalid_policy_action',phase=judge.phase)
            break
        previous=np.clip(raw,-1.,1.)
        servo=(mapping.offset+mapping.scale*previous)*mapping.finger_factor
        raw_log.append(raw.copy())
        clipped_log.append(previous.copy())
        for _ in range(min(10,max_step-start-judge.step)):
            q0,v0=d.qpos.copy(),d.qvel.copy()
            if integrator is None:
                d.ctrl[mapping.actuator_ids]=servo+d.qfrc_bias[mapping.dof]*mapping.bias_gain
                mj.mj_step(model,d)
            else:
                integrator.step(d,servo)
            failure=judge.observe(d,None,q0,v0)
            if failure or judge.passed:
                result['first_failure']=failure
                break
        qlog.append(d.qpos.copy())
        vlog.append(d.qvel.copy())
        ticks.append(judge.step)
    if not judge.passed and result['first_failure'] is None:
        result['first_failure']=dict(reason='reference_exhausted',phase=judge.phase,physics_steps=judge.step)
    result.update(passed=judge.passed,events=judge.events,physics_steps=judge.step,policy_calls=len(raw_log),
                  final_door_deg=float(np.rad2deg(d.qpos[judge.hinge_q])),
                  final_partial_substeps=judge.step%10)
    if integrator is not None:
        result['warp_capacity']=integrator.capacity()
    if raw_dir is not None:
        raw_dir=Path(raw_dir)
        raw_dir.mkdir(parents=True,exist_ok=False)
        for name,values in dict(qpos=qlog,qvel=vlog,physics_step=ticks,raw_action=raw_log,clipped_action=clipped_log).items():
            np.save(raw_dir/(name+'.npy'),np.asarray(values),allow_pickle=False)
        result['raw_directory']=str(raw_dir)
    if output is not None:
        output=Path(output)
        output.mkdir(parents=True,exist_ok=False)
        if video:
            save_video(model,qlog,ticks,output/'episode.mp4')
        dump(output/'result.json',result)
    return result


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False,ensure_ascii=False)+'\n')


def actor_worker(args):
    # torch and compiled/library progress may print to stdout. Keep protocol
    # independent of library prints on both initialisation and inference.
    import contextlib
    stream=sys.stdout
    with contextlib.redirect_stdout(sys.stderr):
        from learning.b0.contact_policy import load_policy
        request=json.loads(input())
        policy=load_policy(args.checkpoint,[Path(p) for p in request['paths']],args.device)
        for line in sys.stdin:
            req=json.loads(line)
            action=policy(Path(req['path']),req['frame'],np.array(req['q']),np.array(req['v']),np.array(req['a']))
            print(json.dumps(np.asarray(action).tolist(),allow_nan=False),file=stream,flush=True)


def main(args):
    manifest=json.loads(args.manifest.read_text())
    trial_groups=[(key,group) for key,group in manifest['cases'].items()
                  if (not args.side or key.split('/')[0] in args.side)
                  and (not args.segment or key.split('/')[1] in args.segment)]
    if not trial_groups:
        raise ValueError('no selected cases')
    directory=args.references or Path(manifest['source'])
    paths=list(dict.fromkeys(directory / g['episode'] for _,g in trial_groups))
    output=ROOT/'results/b0'/args.run
    if Path(args.run).name!=args.run:
        raise ValueError('use a new run name')
    output.mkdir(parents=True,exist_ok=False)
    process=None
    if mj.__version__=='3.3.0':
        if args.backend=='warp':
            raise ValueError('use the pinned B0 interpreter for Warp')
        process=subprocess.Popen(['bash',str(ROOT/'scripts/b0/env.sh'),'python','-u',__file__,'--actor-worker',
                                 '--checkpoint',str(args.checkpoint),'--device',args.device],
                                 text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,bufsize=1)
        process.stdin.write(json.dumps(dict(paths=list(map(str,paths))))+'\n')
        process.stdin.flush()
        def policy(path,frame,hq,hv,ha):
            process.stdin.write(json.dumps(dict(path=str(path),frame=frame,q=hq.tolist(),v=hv.tolist(),a=ha.tolist()),allow_nan=False)+'\n')
            process.stdin.flush()
            return np.array(json.loads(process.stdout.readline()))
    else:
        from learning.b0.contact_policy import load_policy
        policy=load_policy(args.checkpoint,paths,args.device)
    rows=[]
    try:
        model=integrator=None
        current_side=None
        for key,group in trial_groups:
            side,segment=key.split('/')
            if current_side!=side:
                cfg=settings('mobile' if side=='pull' else 'push',1)
                model=build(cfg)
                integrator=WarpSingleWorld(model,args.device) if args.backend=='warp' else None
                current_side=side
            cases=[group['nominal']]+(group['accepted'] if args.dev else [])
            for case in cases:
                folder=Path(side)/segment/case['id']
                r=evaluate_segment(policy,directory/group['episode'],segment,case['perturbation'],args.backend,
                                   output/folder,model=model,integrator=integrator,device=args.device,
                                   raw_dir=ROOT/'results/raw_large/b0'/args.run/folder,video=args.video and case['id']=='nominal')
                row=dict(side=side,segment=segment,case=case['id'],passed=r['passed'],physics_steps=r['physics_steps'],
                         policy_calls=r['policy_calls'],final_door_deg=r['final_door_deg'],
                         failure=r['first_failure']['reason'] if r['first_failure'] else None)
                rows.append(row)
                print(json.dumps(row,allow_nan=False),flush=True)
                if case['id']=='nominal' and not r['passed']:
                    break
    finally:
        if process:
            process.stdin.close()
            if process.wait():
                raise RuntimeError('isolated policy process failed')
    with (output/'cases.csv').open('x') as f:
        writer=csv.DictWriter(f,list(rows[0]),lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    dump(output/'evaluation.json',dict(checkpoint=str(args.checkpoint),backend=args.backend,mujoco=mj.__version__,
                                      manifest=str(args.manifest),requested_dev=args.dev,source=str(directory),
                                      passed=sum(r['passed'] for r in rows),evaluated=len(rows),
                                      failures=[r for r in rows if not r['passed']]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run')
    parser.add_argument('--checkpoint',type=Path,required=True)
    parser.add_argument('--backend',choices=('native','warp'),default='native')
    parser.add_argument('--device',default='cuda:0')
    parser.add_argument('--references',type=Path)
    parser.add_argument('--manifest',type=Path,default=ROOT/'config/b0/contact_dev_v1.json')
    parser.add_argument('--dev',action='store_true',help='after passing nominal, evaluate the registered twenty')
    parser.add_argument('--video',action='store_true',help='record every nominal trial from its first input to terminal state')
    parser.add_argument('--side',nargs='+',choices=('pull','push'))
    parser.add_argument('--segment',nargs='+',choices=SEGMENTS)
    parser.add_argument('--actor-worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.actor_worker:
        actor_worker(args)
    elif args.run:
        main(args)
    else:
        parser.error('--run required')
