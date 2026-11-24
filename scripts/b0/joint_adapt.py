"""Single source-registered WM adaptation with continuous optimizer and RNG state."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import argparse
import csv
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
from supermimic.learners import wm_learner
from learning.b0.contact_sources import SourceWindows,response_episodes
from learning.b0.contact_training import OnlineContactReplay
from scripts.b0 import dynamics_h32_pilot as pilot
from scripts.b0.dynamics_h32_probe import observed_draws,rng_state,restore_rng
from scripts.b0.joint_collection import OUT,RAW
from scripts.b0.joint_validation import Validation

SMALL=OUT/"adapt"
BIG=RAW/"adapt"
REG=OUT/"registration.json"
ORDER=[7]*8+[1]*2

def register():
    if REG.exists():raise FileExistsError(REG)
    info=pilot.read(pilot.OUT/"offline_scores/rebase_001000/six_metrics.json")
    e0={k.split("_h32")[0]:v for k,v in info["values"].items() if "_h32" in k}
    grad=[float(r["preclip_norm"]) for r in csv.DictReader((OUT/"replay/experiment/updates.csv").open())]
    assert len(grad)==10
    pilot.write(REG,dict(method="SuperMimic-M1Piper-standard-v1",code_base="528a9d7",seed=0,physics="warp_250us_servo2ms_continuous_v1",
        dt=.00025,servo=.002,policy=.02,c=.50625,wm=info["checkpoint"],actor_critic=str(pilot.SHARED/"first.pt"),
        previous_actual_draw_replay=30,first_stage_max=500,cumulative_max=1000,
        batch_sequence=ORDER,batch_size=256,joint_H7=dict(online=192,native=32,Warp=32),joint_H1=dict(online=192,native=0,Warp=64),
        source_experiment="Original joint allocation; append only nonduplicate fine training boundary branches to response H1",
        boundary_train_registration=str(OUT/"physics/boundary_train_registration.json"),
        boundary_train_raw=str(RAW/"physics/boundary/training/repeat0"),
        train_chunks="alternate the two actual u0 training cohorts in successive ten-batch blocks: shared then continuous fresh",
        dev="all eligible H1/H7 of one independent validation-trajectory cohort, frozen actor and buffers, seed 112402",
        primary_online="both horizon losses and terminal J2 position/velocity RMSE on all fixed legal starts strictly lower than step zero",
        exact_e0=e0,limits={k:max(v*1.25,v+2) for k,v in e0.items()},
        long_denominators={k.split("_h32")[0]:v for k,v in info.items() if k.endswith("_scored")},
        qualification="score every 10 actual WM updates, qualify on two consecutive passing post-block endpoints, save the 0/10/20 states and advance at second endpoint",
        grad_baseline=grad,grad_p95=float(np.percentile(grad,95)),
        grad_trigger="two consecutive blocks with p95 above 10x baseline and worsening independent H7 loss",
        optim="original shared Adam and Muon, fresh at start; 2e-4, original 1.0 grad clip, continuous through qualification and H32",
        adjustment_limit=1,official_physics="2ms Warp and native MuJoCo 3.3.0, 6N",
        frozen_h32_seed_chain_untouched=["control/u10 pending=2","experiment/u10 pending=2"]))

def extend_response(run,reg):
    recipe=dict(registration=reg["boundary_train_registration"],raw=reg["boundary_train_raw"])
    ep=response_episodes(recipe,run.model,run.device)
    assert len(ep)==14 and all(e.split=="train" and len(e.starts(1))==1 and not len(e.starts(7)) for e in ep)
    old=run.registered_wm.pools["response",1]
    boundary_min=len(old.episodes)
    run.registered_wm.pools["response",1]=SourceWindows(old.episodes+ep,1)
    return boundary_min

def get_train(run):
    s=torch.load(RAW/"collection/train/state.pt",weights_only=False,map_location=run.device)
    assert len(s["chunks"])==2
    subsets=[]
    for chunk in s["chunks"]:
        replay=OnlineContactReplay(1,run.device,run.replay.draw)
        replay.chunks.append(chunk)
        subsets.append(replay)
    return s,subsets

def ck(n):return BIG/f"wm_{n:06}.pt"

def save(run,n):
    pilot.atomic_torch(dict(dyn=run.dyn.state_dict(),optimizers=[o.state_dict() for o in run.learners[7].optimizers],
        rng=rng_state(),batches=n,physics_dt=run.model.opt.timestep,c=run.rep.substep_coeff),ck(n))

def train(start,stop,adjust):
    reg=pilot.read(REG)
    SMALL.mkdir(parents=True,exist_ok=True)
    BIG.mkdir(parents=True,exist_ok=True)
    if ck(stop).exists() or (SMALL/"qualified.json").exists():raise FileExistsError("Completed node or qualification")
    if stop>reg["first_stage_max"] and not (SMALL/"extension.json").exists():raise ValueError("Extension evidence missing")
    discarded=pilot.read(SMALL/"execution_accounting.json")["discarded_optimizer_steps"] if (SMALL/"execution_accounting.json").exists() else 0
    limit=1000 if (SMALL/"extension.json").exists() else 500
    assert 0<=start<stop and stop+discarded<=limit and start%10==stop%10==0
    run=pilot.build("experiment")
    boundary=extend_response(run,reg)
    s,subsets=get_train(run)
    val=Validation(run)
    opts=run.learners[7].optimizers
    if start==0:
        restore_rng(s["rng"])
        baseline=val.score(run,SMALL/"node_000000")
        for k,x in reg["exact_e0"].items():
            assert abs(x-baseline[k])<.002,(k,x,baseline[k])
        save(run,0)
    else:
        base=torch.load(ck(start),weights_only=False,map_location=run.device)
        run.dyn.load_state_dict(base["dyn"])
        for o,st in zip(opts,base["optimizers"],strict=True):o.load_state_dict(st)
        restore_rng(base["rng"])
        baseline=pilot.read(SMALL/"node_000000/scores.json")["values"]
    if adjust:
        choice=pilot.read(SMALL/"adjustment.json")
        assert choice["at"]==start and adjust==choice["lr"]
        for opt in opts:
            for g in opt.param_groups:
                if torch.is_tensor(g["lr"]):g["lr"].fill_(adjust)
                else:g["lr"]=adjust
    last=pilot.read(SMALL/f"node_{start:06}/check.json") if start else dict(passed=False,warn=False)
    old=pilot.read(SMALL/f"node_{start:06}/scores.json")["values"]
    norm=torch.zeros((),device=run.device)
    original=wm_learner._optimize_step
    def measure(*a,**kw):
        n=original(*a,**kw)
        norm.copy_(n.detach())
        return n
    for first in range(start,stop,10):
        n=first+10
        node=SMALL/f"node_{n:06}"
        node.mkdir(parents=True,exist_ok=True)
        ns=[]
        subset=(first//10)%2
        with patch.object(wm_learner,"_optimize_step",measure),observed_draws(run) as draws,(node/"updates.jsonl").open("x",buffering=1) as log:
            for i,h in enumerate(ORDER,first):
                td,on=run.registered_wm.draw(h,i,run.b,subsets[subset])
                assert on==192
                metrics=run.learners[h].update([td])
                g=float(norm)
                losses={k:float(v) for k,v in metrics.items()}
                if not np.isfinite([g,*losses.values()]).all():raise FloatingPointError(i+1)
                r=draws.get(f"wm_{i:03}_h{h}_response")
                boundary_n=int((r[:,1]>=boundary).sum()) if h==1 and r is not None else 0
                rec=dict(step=i+1,train_chunk=subset,preclip=g,clipped=g>1,boundary_h1=boundary_n,losses=losses,**run.registered_wm.rows[-1])
                import json
                log.write(json.dumps(rec,allow_nan=False)+"\n")
                ns.append(g)
        np.savez_compressed(node/"draws.npz",**draws)
        save(run,n)
        current=val.score(run,node)
        scores=pilot.read(node/"scores.json")
        assert scores["long_counts"]==reg["long_denominators"]
        long_ok=all(current[k]<=lim for k,lim in reg["limits"].items())
        online_ok=all(current[k]<baseline[k] for k in current if k.startswith("H"))
        p95=float(np.percentile(ns,95))
        warn=p95>10*reg["grad_p95"] and current["H7_loss"]>old["H7_loss"]
        passed=long_ok and online_ok
        check=dict(step=n,chunk=subset,long_ok=long_ok,online_ok=online_ok,passed=passed,warn=warn,preclip_p95=p95,preclip_max=max(ns),clipped=sum(x>1 for x in ns))
        pilot.write(node/"check.json",check)
        print(n,current,check,flush=True)
        if passed and last["passed"]:
            pilot.write(SMALL/"qualified.json",dict(first=n-10,second=n,checkpoint=str(ck(n)),actual_updates=n))
            return
        if warn and last["warn"]:raise FloatingPointError(f"Registered gradient instability at batch {n}")
        last,old=check,current

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("register")
    t=sub.add_parser("train")
    t.add_argument("start",type=int)
    t.add_argument("stop",type=int)
    t.add_argument("--adjust",type=float)
    a=p.parse_args()
    if a.cmd=="register":register()
    else:train(a.start,a.stop,a.adjust)
