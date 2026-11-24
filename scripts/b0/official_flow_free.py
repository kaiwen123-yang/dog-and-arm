"""Apply the existing frozen B0-03 Warp judge to the new online Actor."""
import argparse
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import torch

from learning.b0.contact_policy import build_actor
from learning.b0.evaluate import ErrorMeasures, PROTOCOL, write_case_summary
from learning.b0.model import RobotRepresentation
from learning.b0.physics import make_model
from learning.b0.reference import load_episode
from learning.b0.research_env import ResearchPlant
from learning.b0.training import FreeRun, MotionBank
from scripts.b0.eval_warp import trial_batch
from scripts.b0.official_flow import OUT, RAW
from scripts.b0.dynamics_h32_pilot import write


class FreeActorEvaluation:
    sensor = FreeRun.sensor
    actor_obs = FreeRun.actor_obs
    policy_factory = FreeRun.policy_factory

    def __init__(self,u,source):
        self.device='cuda:0'
        self.raw=RAW/'free'/f'u{u:06}'
        self.checkpoint=str(RAW/f'checkpoint_{u:06}.pt')
        weights=torch.load(self.checkpoint,map_location=self.device,weights_only=True)
        self.seed=weights['seed']
        self.model=make_model()
        self.rep=RobotRepresentation(self.model,self.device)
        self.refs={name:load_episode(source/name) for name in ('support','moving_arm','park')}
        self.motion=MotionBank(self.refs,self.rep.fk,self.raw/'motion',self.device)
        self.starts=torch.nn.functional.pad(self.motion.motion_ends[:-1],(1,0))
        self.actor,_=build_actor(self.rep,weights['cfg'],self.model,self.device)
        self.actor.load_state_dict(weights['actor'])
        self.actor.eval()


@torch.no_grad()
def evaluate(u,source):
    run=FreeActorEvaluation(u,source)
    cases=PROTOCOL['cases']
    plant=ResearchPlant(run.model,len(cases),run.device)
    out=OUT/'free'/f'u{u:06}'
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    diffs={}
    measures=ErrorMeasures(run.model)
    for ref in run.refs:
        trials,delta=trial_batch(run,plant,ref,cases,out,measures)
        rows.extend(trials)
        diffs[ref]=delta
    write_case_summary(rows,out,run.refs,cases)
    write(out/'evaluation.json',dict(protocol=PROTOCOL['version'],checkpoint=run.checkpoint,
        backend='Warp',dt=run.model.opt.timestep,reference=str(source),cases=len(rows),
        seed=run.seed,initial_action_max_batch_vs_single=diffs,raw=str(run.raw)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('update',type=int)
    p.add_argument('--references',type=Path,required=True)
    args=p.parse_args()
    evaluate(args.update,args.references)
