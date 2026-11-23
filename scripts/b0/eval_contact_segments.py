"""Closed-loop contact segment evaluation with a frozen Actor and read-only physical events."""
import argparse
import csv
import json
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


FULL_DOOR_PHASES = ('approach_base', 'settle', 'pregrasp', 'approach_arm', 'grasp', 'open',
                    'hold', 'release', 'retreat_arm', 'post_release_hold', 'stow', 'retreat_base', 'final')


def continuous_initial(model, cfg, integrator):
    data = mj.MjData(model)
    mj.mj_resetDataKeyframe(model, data, model.key('home').id)
    case, yaw = cfg['perturbation'], cfg['base_yaw_rad']
    parking = np.asarray(cfg['base_xyz_m'][:2]) - cfg['travel_m'] * np.array([np.cos(yaw),np.sin(yaw)])
    initial_yaw = yaw + np.deg2rad(case.get('yaw',0))
    data.qpos[:2] = parking + [case.get('dx',0),case.get('dy',0)]
    data.qpos[3:7] = [np.cos(initial_yaw/2),0,0,np.sin(initial_yaw/2)]
    data.qpos[model.joint('door_single_hinge').qposadr.item()] = np.deg2rad(case.get('door',0))
    mj.mj_forward(model, data)
    if integrator is not None:
        integrator.reset(data)
    # No actions preceded reset. Repeat only the true first observation while the
    # rolling history fills, as in the frozen B0-03 full-start evaluation.
    previous = np.zeros(23)
    history = [np.repeat(x[None],10,axis=0) for x in (data.qpos,data.qvel,previous)]
    metrics = dict(case=cfg['case'],parking_xy_m=parking.tolist(),applied_perturbation=case,
                   history_initialization='repeat initial measured state and zero previous command',
                   initial_qpos=data.qpos.tolist(),initial_qvel=data.qvel.tolist())
    return data, (*history, previous), metrics


def evaluate_segment(policy_fn, episode_path, segment, perturbation, backend, output=None, *,
                     model=None, integrator=None, device='cuda:0', raw_dir=None, video=False, action_source='frozen Actor raw output then clamp'):
    path=Path(episode_path)
    meta=json.loads((path/'metadata.json').read_text())
    side = meta['task']
    full = segment == 'full'
    stage = 'mobile' if side=='pull' else 'push'
    case = int(perturbation['p6_case']) if full else 1
    cfg = settings(stage,case)
    goal, phases = (cfg['target_angle_deg'],FULL_DOOR_PHASES) if full else SEGMENTS[segment]
    if full and (not meta.get('full_task') or tuple(meta['phases']) != FULL_DOOR_PHASES):
        raise ValueError(f'Incomplete continuous door reference {path}')
    if meta['target_angle_deg']!=goal or not meta['success'] or meta['wm_split']!='train':
        raise ValueError(f'expected successful training reference for {segment}: {path}')
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
    judge=ContactEvents(model,cfg,side,ref,phases=phases,hold_seconds=.5 if full else 3.,start_step=start)
    mapping=ActionMap(model)
    if full:
        if start != 0:
            raise ValueError('Continuous evaluation must start at the original frame zero')
        d, (hq,hv,ha,previous), metrics = continuous_initial(model,cfg,integrator)
    else:
        d, (hq,hv,ha,previous), metrics = prefix_history(model,cfg,path,side,start,perturbation,integrator=integrator)
    result=dict(episode=meta['episode_id'],side=side,segment=segment,backend=backend,mujoco=mj.__version__,action_source=action_source,
                start_substep=start,reference_phase_end_substep=end,reference_last_substep=max_step,
                prefix_physics_steps=0 if full else 100,perturbation=perturbation,initial_geometry=metrics,
                passed=False,first_failure=None,events=[],policy_calls=0,physics_steps=0)
    if full:
        result['actual_config'] = cfg
    if not full and not valid_initial(metrics,segment,cfg):
        result['first_failure']=dict(reason='initial_contact_reconstruction',phase=phases[0])
    qlog=[d.qpos.copy()]
    vlog=[d.qvel.copy()]
    ticks=[0]
    raw_log, clipped_log=[],[]
    audit=[]
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
            if full and raw_dir is not None:
                obs = judge.latest
                audit.append([judge.step,FULL_DOOR_PHASES.index(obs['phase']),obs['door_deg'],
                              *obs['finger_n'],obs['net_door_force_n'],obs['tcp_handle_error_m'],
                              obs['width_m'],obs['station_error_m'],obs['tilt_deg'],obs['speed_m_s'],
                              obs['yaw_rate_deg_s'],obs['continuous_ready_steps']])
            if failure or judge.passed:
                result['first_failure']=failure
                break
        qlog.append(d.qpos.copy())
        vlog.append(d.qvel.copy())
        ticks.append(judge.step)
    if not judge.passed and result['first_failure'] is None:
        readiness = {}
        if judge.latest and judge.latest['phase'] == judge.phase:
            readiness = dict(current=judge.latest['continuous_ready_steps'], required=judge.latest['required_ready_steps'],
                             best=judge.peak_ready_steps[judge.phase], last_not_ready=judge.last_not_ready.get(judge.phase))
        result['first_failure']=dict(reason='reference_exhausted',phase=judge.phase,physics_steps=judge.step,readiness=readiness)
    result.update(passed=judge.passed,events=judge.events,physics_steps=judge.step,policy_calls=len(raw_log),
                  final_door_deg=float(np.rad2deg(d.qpos[judge.hinge_q])),
                  final_partial_substeps=judge.step%10, longest_ready_steps=judge.peak_ready_steps,
                  last_physical_observation=judge.latest)
    if integrator is not None:
        result['warp_capacity']=integrator.capacity()
    if raw_dir is not None:
        raw_dir=Path(raw_dir)
        raw_dir.mkdir(parents=True,exist_ok=False)
        for name,values in dict(qpos=qlog,qvel=vlog,physics_step=ticks,raw_action=raw_log,clipped_action=clipped_log).items():
            np.save(raw_dir/(name+'.npy'),np.asarray(values),allow_pickle=False)
        if full:
            np.save(raw_dir/'physical_events_2ms.npy',np.asarray(audit),allow_pickle=False)
            result['physical_event_columns'] = ['step','phase_id','door_deg','finger1_n','finger2_n',
                'resultant_n','tcp_handle_error_m','jaw_width_m','station_error_m','tilt_deg',
                'speed_m_s','yaw_rate_deg_s','continuous_ready_steps']
            result['phases'] = FULL_DOOR_PHASES
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


def check_legacy_actor(output, directory, raw_root, policy):
    """Old interrupted runs predate run_spec.json; replay a saved Actor input before reusing them."""
    for record in sorted(output.glob('*/*/*/result.json')):
        result = json.loads(record.read_text())
        if result['policy_calls'] < 12:
            continue
        case_dir = raw_root / record.parent.relative_to(output)
        q, v, a, raw = (np.load(case_dir/(n+'.npy'), mmap_mode='r')
                        for n in ('qpos','qvel','clipped_action','raw_action'))
        for frame in (10, len(raw)-1):
            predicted = policy(directory/result['episode'],result['start_substep']//10+frame,
                               q[frame-9:frame+1],v[frame-9:frame+1],a[frame-10:frame])
            if not np.allclose(predicted,raw[frame],rtol=2e-5,atol=2e-5):
                raise ValueError(f'Legacy Actor output mismatch at {record}, frame {frame}')
        return str(record.relative_to(output))
    raise ValueError('No complete legacy trajectory with two reproducible Actor inputs')


def run_warp_cases(job):
    """A single independent Warp worker keeps the frozen joint reference bank across its cases."""
    from learning.b0.contact_policy import load_policy
    checkpoint, paths, device, episode, cases, output, raw_root, side = job
    policy = load_policy(checkpoint, paths, device)
    for case in cases:
        folder = Path(side) / 'full' / case['id']
        result = evaluate_segment(policy, episode, 'full', case['perturbation'], 'warp',
                                  output / folder, device=device, raw_dir=raw_root / folder)
        print(f"{side} {case['id']} passed={result['passed']} steps={result['physics_steps']}", flush=True)


def parallel_full_dev(args, paths, group, directory, cases, output, raw_root, side):
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    pending = []
    for case in cases:
        folder = Path(side) / 'full' / case['id']
        if args.resume and (output / folder / 'result.json').is_file():
            continue
        if args.resume:
            preserve_partial(folder, output, raw_root)
        pending.append(case)
    workers = min(args.dev_workers, len(pending))
    if workers:
        jobs = [(args.checkpoint, paths, args.device, directory / group['episode'], pending[i::workers],
                 output, raw_root, side) for i in range(workers)]
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as pool:
            list(pool.map(run_warp_cases, jobs))


def preserve_partial(folder, output, raw_root):
    from time import time_ns
    for root in (raw_root, output):
        partial = root / folder
        if partial.exists():
            saved = root / 'interrupted' / str(time_ns()) / folder
            saved.parent.mkdir(parents=True, exist_ok=True)
            partial.rename(saved)
            print(f'Retained incomplete case at {saved}', file=sys.stderr, flush=True)


def main(args):
    if args.dev_workers < 1 or (args.dev_workers > 1 and not (args.full_task and args.dev and args.backend == 'warp')):
        raise ValueError('Parallel development workers require a complete Warp task and --dev')
    selected = getattr(args, 'full_cases', None)
    if selected and (not args.full_task or not args.dev or len(selected) != len(set(selected))):
        raise ValueError('--full-cases requires --full-task --dev and unique development IDs')
    if args.full_task:
        from p6_scene import CASES
        if selected and any(i not in CASES for i in selected):
            raise ValueError('Unknown full-task development case')
        if not args.side or not args.references or args.segment:
            raise ValueError('Choose a full-task side and its fixed training reference directory')
        args.manifest = ROOT/'scripts/p6_scene.py'
        cases = {}
        for side in args.side:
            goal = 60 if side == 'pull' else 25
            cases[side+'/full'] = dict(episode=f'{side}_{goal}_train',
                nominal=dict(id='nominal',perturbation={'p6_case':1}),
                accepted=[dict(id=f'C{i:02d}',perturbation={'p6_case':i}) for i in (selected or sorted(CASES))])
        manifest = dict(cases=cases,source=str(args.references))
    else:
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
    plan=dict(checkpoint=str(args.checkpoint), backend=args.backend, mujoco=mj.__version__,
              source=str(directory), manifest=str(args.manifest), groups=[k for k,_ in trial_groups],
              requested_dev=args.dev, video=args.video)
    if selected:
        plan['diagnostic_cases'] = selected
        plan['score_selected_after_nominal_failure'] = True
    spec_path=output/'run_spec.json'
    raw_root=ROOT/'results/raw_large/b0'/args.run
    legacy=False
    if args.resume:
        if not output.is_dir() or (output/'evaluation.json').exists():
            raise ValueError('--resume expects an interrupted evaluation directory')
        if spec_path.is_file():
            if json.loads(spec_path.read_text())['plan']!=plan:
                raise ValueError('Resume requires the same checkpoint, evaluation and output settings')
        else:
            legacy=True
    else:
        output.mkdir(parents=True,exist_ok=False)
        dump(spec_path,dict(plan=plan))
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
        if legacy:
            checked=check_legacy_actor(output,directory,raw_root,policy)
            dump(spec_path,dict(plan=plan,legacy_identity_check=checked))
        model=integrator=None
        current_side=None
        accepted_nominals=set()
        for development in ([False,True] if args.dev else [False]):
            for key,group in trial_groups:
                if development and not selected and key not in accepted_nominals:
                    continue
                side,segment=key.split('/')
                if current_side!=side and not args.full_task:
                    cfg=settings('mobile' if side=='pull' else 'push',1)
                    model=build(cfg)
                    integrator=WarpSingleWorld(model,args.device) if args.backend=='warp' else None
                    current_side=side
                cases=group['accepted'] if development else [group['nominal']]
                parallel = development and args.dev_workers > 1
                if parallel:
                    parallel_full_dev(args, paths, group, directory, cases, output, raw_root, side)
                for case in cases:
                    folder=Path(side)/segment/case['id']
                    record=output/folder/'result.json'
                    if (args.resume or parallel) and record.is_file():
                        r=json.loads(record.read_text())
                        if (r['backend']!=args.backend or r['mujoco']!=mj.__version__
                                or r['episode']!=group['episode'] or r['segment']!=segment
                                or r['perturbation']!=case['perturbation']):
                            raise ValueError(f'{record} disagrees with the frozen case')
                    else:
                        if args.resume:
                            preserve_partial(folder, output, raw_root)
                        r=evaluate_segment(policy,directory/group['episode'],segment,case['perturbation'],args.backend,
                                           output/folder,model=model,integrator=integrator,device=args.device,
                                           raw_dir=raw_root/folder,video=args.video and not development)
                    row=dict(side=side,segment=segment,case=case['id'],passed=r['passed'],physics_steps=r['physics_steps'],
                             policy_calls=r['policy_calls'],final_door_deg=r['final_door_deg'],
                             failure=r['first_failure']['reason'] if r['first_failure'] else None)
                    rows.append(row)
                    print(json.dumps(row,allow_nan=False),flush=True)
                    if not development and r['passed']:
                        accepted_nominals.add(key)
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
    parser.add_argument('--resume',action='store_true',help='Continue unfinished cases in the same run')
    parser.add_argument('--full-cases', nargs='+', type=int, help='Explicit C IDs for a diagnostic subset, scored even after nominal failure')
    parser.add_argument('--dev-workers', type=int, default=1, help='parallel independent full-task Warp development cases after a passed nominal')
    parser.add_argument('--dev',action='store_true',help='after passing nominal, evaluate the registered twenty')
    parser.add_argument('--video',action='store_true',help='record every nominal trial from its first input to terminal state')
    parser.add_argument('--full-task', action='store_true', help='closed loop from original P6 start; nominal, then C01–C20 when requested')
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
