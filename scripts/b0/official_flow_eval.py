"""Evaluate a frozen official-flow node with the original judges and validation windows."""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
from supermimic.learners.wm_learner import WorldModelLearner

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg
from learning.b0.physics import ActionMap, make_model
from learning.b0.temporal_dynamics import make_dynamics
from scripts.b0 import dynamics_h32_pilot as io
from scripts.b0.joint_validation import Validation
from scripts.b0.official_flow import CONTINUATION, NEW_SEGMENT, PARENT_RAW, OUT, RAW


def evaluate(u, backend, kind):
    checkpoint = RAW/f"checkpoint_{u:06}.pt"
    folder = 'physics'
    if kind == 'parent-ready':
        if not NEW_SEGMENT or u != 4991:
            raise ValueError('Only the registered u4991 parent can be replayed')
        checkpoint = PARENT_RAW/f"checkpoint_{u:06}.pt"
        folder = 'diagnostic_replay'
        kind = 'full'
    prefix = f"u{u:06}_{backend}"
    for protocol in (("full",) if kind == 'full' else ('v1','hold_margin_v2')):
        run = f"{prefix}_{protocol}"
        dest = OUT/folder/run
        if (dest/'evaluation.json').exists():
            if protocol=='full':
                export_complete_videos(dest,checkpoint,backend)
            continue
        runner = 'scripts/project_env.sh' if backend == 'native' else 'scripts/b0/env.sh'
        cmd = ['bash',runner,'python','-u','scripts/b0/eval_contact_segments.py',
               '--checkpoint',str(checkpoint),'--backend',backend,'--run',run,
               '--round',str(OUT.relative_to('results/b0')/folder),
               str(RAW.relative_to('results/raw_large/b0')/folder),'--paper-score']
        if CONTINUATION:
            cmd += ['--record-servo','--warning-log',str(OUT/'backend'/'node_warnings.jsonl')]
        if protocol=='full':
            cmd += ['--full-task','--side','pull','push','--references','results/raw_large/b0/full_warp_hold_park_r1']
        else:
            cmd += ['--manifest',f'config/b0/contact_dev_{protocol}.json','--formal-contact']
        if dest.exists():
            cmd += ['--resume']
        if protocol!='full':
            subprocess.run(cmd,check=True)
            continue
        # A successful side has a complete raw trace as soon as its case receipt
        # appears. Export it while the independent evaluator continues its next side.
        with subprocess.Popen(cmd) as scoring:
            while scoring.poll() is None:
                export_complete_videos(dest,checkpoint,backend)
                time.sleep(2)
            if scoring.returncode:
                raise subprocess.CalledProcessError(scoring.returncode,cmd)
        export_complete_videos(dest,checkpoint,backend)


def export_complete_videos(dest,checkpoint,backend):
    from scripts.b0.eval_contact_segments import FULL_DOOR_PHASES, save_video, build
    for record in dest.glob('*/full/nominal/result.json'):
        case=io.read(record)
        if not case['passed'] or (record.parent/'video_manifest.json').is_file():
            continue
        raw=Path(case['raw_directory'])
        q,steps=(np.load(raw/(k+'.npy')) for k in ('qpos','physics_step'))
        events=[e['phase'] for e in case['events']]
        if (tuple(events)!=FULL_DOOR_PHASES or steps[0]!=0 or case['prefix_physics_steps']!=0
                or not np.all((np.diff(steps)>0)&(np.diff(steps)<=10))
                or len(steps)!=case['policy_calls']+1):
            raise ValueError('The complete video requires a continuous original trial and every phase event')
        side=case['side']
        video=record.parent/f'full_{side}_nominal.mp4'
        if not video.exists() or not (record.parent/'video_manifest.json').exists():
            save_video(build(case['actual_config']),q,steps,video)
        io.write(record.parent/'video_manifest.json',dict(video=video.name,side=side,
            checkpoint=str(checkpoint),seed=0,backend=backend,physics_dt=.002,
            frames=sum(t%20==0 or i==len(steps)-1 for i,t in enumerate(steps.tolist())),
            fps=25,playback=1,simulated_seconds=float(steps[-1])*.002,verdict=str(record),
            trace=str(raw),action_source=case['action_source']))


def diagnostic(u):
    target=OUT/'validation'/f'u{u:06}'
    if (target/'scores.json').is_file():
        return
    package=torch.load(RAW/f'checkpoint_{u:06}.pt',weights_only=False,map_location='cpu')
    cfg=package['cfg']
    model=make_model()
    model.opt.timestep=cfg['physics_dt']
    rep=ContactRepresentation(model,io.DEVICE)
    dyn=make_dynamics(model,rep,ActionMap(model),cfg['wm_hidden'],'C20',io.DEVICE)
    dyn.load_state_dict(package['dyn'])
    learner=WorldModelLearner(dyn,rep,ContactWorldModelCfg(),io.DEVICE)
    # Historical held-out evaluator only. Both lengths use the same variable-length loss.
    source_cfg=io.resolved('config/b0/standard_dynamics_v1.yaml')
    probe=SimpleNamespace(cfg=source_cfg,model=model,rep=rep,dyn=dyn,learners={1:learner,7:learner})
    Validation(probe).score(probe,target)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('update',type=int)
    parser.add_argument('kind',choices=['formal','full','wm','parent-ready'])
    parser.add_argument('--backend',choices=['warp','native'],default='warp')
    args=parser.parse_args()
    lock=RAW/f'.eval-{args.update}-{args.kind}-{args.backend}.lock'
    with lock.open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        if args.kind=='wm':
            diagnostic(args.update)
        else:
            evaluate(args.update,args.backend,args.kind)
