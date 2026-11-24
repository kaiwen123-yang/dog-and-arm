"""Continue the qualified seed-zero chain from its second measured WM block."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import argparse
from contextlib import ExitStack
from unittest.mock import patch
import numpy as np
import torch
from supermimic.learners import wm_learner
from learning.b0.contact_gradient import trace_first_update
from scripts.b0 import dynamics_h32_pilot as pilot
from scripts.b0.dynamics_h32_probe import observed_draws,restore_rng,rng_state
from scripts.b0.joint_collection import OUT,RAW
from scripts.b0.joint_adapt import REG,SMALL,extend_response,get_train
from scripts.b0.joint_validation import Validation

def load_training(run):
    state,_=get_train(run)
    common=torch.load(pilot.SHARED/"first.pt",map_location="cpu",weights_only=False)
    for name in ("actor","critic"):
        for key,value in getattr(run,name).state_dict().items():
            assert torch.equal(value.cpu(),common[name][key])
    run.replay.chunks.extend(state["chunks"])
    run.replay.tail=state["tail"]
    run.lanes=state["lanes"]
    run.total,run.simulated,run.last_episode=state["total"],state["simulated"],state["last_episode"]
    run.sampler.load_state_dict(state["sampler"])
    run.schedule.load_state_dict(state["schedule"])
    with patch.object(pilot,"SHARED",RAW/"collection/train"):
        pilot.solver_snapshot(run,True)
    for k,v in state["counters"].items():
        target=getattr(run.plant,k,None)
        if target is None:setattr(run.plant,k,v)
        else:target.copy_(v)

def train(stop):
    reg=pilot.read(REG)
    qual=pilot.read(SMALL/"qualified.json")
    pre=qual["second"]
    assert all(pilot.read(SMALL/f"node_{n:06}/check.json")["passed"] for n in (pre-10,pre))
    out,raw=OUT/"main",RAW/"main"
    for path in (raw,out):path.mkdir(parents=True,exist_ok=True)
    if (out/"updates.jsonl").exists() or (out/"pre_actor_pause.json").exists():
        raise FileExistsError("Main chain has a recorded state")
    run=pilot.build("experiment")
    load_training(run)
    extend_response(run,reg)
    val=Validation(run)
    saved=torch.load(qual["checkpoint"],weights_only=False,map_location=run.device)
    run.dyn.load_state_dict(saved["dyn"])
    for opt,state in zip(run.learners[7].optimizers,saved["optimizers"],strict=True):opt.load_state_dict(state)
    restore_rng(saved["rng"])
    run.compact_directory=raw
    run.wm_index=pre
    pilot.checkpoint(run,0,out,raw)
    assert pilot.optimizer_steps(run)==dict(wm=pre,actor=0,critic=0)
    for count in range(1,stop+1):
        while not run.schedule.pending:
            pilot.append(out/"cohorts.jsonl",run.collect())
        norms={h:torch.zeros(n,device=run.device) for h,n in [(7,8),(1,2)]}
        indices={}
        original=wm_learner._optimize_step
        def measure(opts,loss,params,max_norm):
            h=indices["h"]
            g=original(opts,loss,params,max_norm)
            norms[h][indices["i"]].copy_(g.detach())
            indices["i"]+=1
            return g
        def wrapped(h,func):
            def update(batches):
                indices.update(h=h,i=0)
                return func(batches)
            return update
        normal=run.policy.update
        def before_actor():
            actual=val.score(run,out/f"pre_actor_{count:06}")
            bad=any(actual[k]>max(50,2*v) for k,v in reg["exact_e0"].items())
            if bad:
                second=val.score(run,out/f"pre_actor_{count:06}_repeat")
                bad=any(second[k]>max(50,2*v) for k,v in reg["exact_e0"].items())
            if bad:
                pilot.atomic_torch(dict(dyn=run.dyn.state_dict(),optimizers=[o.state_dict() for o in run.learners[7].optimizers],
                    rng=rng_state(),wm_index=run.wm_index),raw/f"paused_before_actor_{count:06}.pt")
                pilot.write(out/"pre_actor_pause.json",dict(update=count,completed_actor=count-1,wm=run.wm_index-pre,
                    long_scores=second,gradients={str(h):t.tolist() for h,t in norms.items()}))
                raise FloatingPointError("Repeated registered long-window instability before Actor")
            if count==1:
                pilot.atomic_torch(dict(dyn=run.dyn.state_dict(),rng=rng_state(),wm_index=run.wm_index),
                    raw/"u1_after_wm_before_actor.pt")
                trace_first_update(run,out,raw)
            return normal()
        with ExitStack() as stack:
            stack.enter_context(patch.object(wm_learner,"_optimize_step",measure))
            for h in norms:
                stack.enter_context(patch.object(run.learners[h],"update",wrapped(h,run.learners[h].update)))
            stack.enter_context(patch.object(run.policy,"update",before_actor))
            actual=stack.enter_context(observed_draws(run))
            metrics=run.update()
        run.schedule.pending-=1
        count_expected=dict(wm=pre+count*10,actor=count,critic=count*20)
        assert count_expected==pilot.optimizer_steps(run)
        np.savez_compressed(out/f"draws_{count:06}.npz",**actual)
        for item in run.registered_wm.rows:pilot.append(out/"wm_draws.jsonl",dict(update=count,**item))
        run.registered_wm.rows.clear()
        pilot.append(out/"updates.jsonl",dict(update=count,optim=count_expected,gradients={str(h):t.tolist() for h,t in norms.items()},
            ratio=run.schedule.state_dict(),valid=run.total,simulated=run.simulated,metrics=metrics))
        if count in (1,10,50,100,200,stop):pilot.checkpoint(run,count,out,raw)
        print(count,count_expected,flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stop",type=int,default=50,nargs="?")
    train(p.parse_args().stop)
