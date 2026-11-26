"""Compare CF32 replay, losses and all trainable gradients on real, fixed native branches."""
import argparse
import importlib.util
import json
from pathlib import Path
import pickle
import statistics
import sys
import time

import numpy as np
import torch

from learning.multimodal.actor import load_actor
from learning.multimodal.mm03_task import load_task_actor
from scripts.multimodal.mm03_launch import now, read, write


def load_source(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod
    spec.loader.exec_module(mod)
    return mod


class Capture:
    """Record only a diagnostic execution. The production native worker is the forward backend."""
    def __init__(self,pool):
        self.pool=pool
        self.ticks=[]
        self.steps=0
    def reset(self,paths):
        self.paths=list(map(str,paths))
        self.initial=self.pool.reset(paths)
        return self.initial
    def advance(self,slots,actions):
        replies=self.pool.advance(slots,actions)
        self.steps+=sum(v["substeps"] for v in replies.values())
        self.ticks.append((tuple(slots),actions.copy(),replies))
        return replies


class Tape:
    """Check the current policy's action at every decision before returning its recorded solve."""
    def __init__(self,data):
        self.data=data
    def reset(self,paths):
        if list(map(str,paths))!=self.data["paths"]:raise AssertionError("Changed anchors")
        self.tick=0
        return self.data["initial"]
    def start_step(self,slots,actions):
        old,expected,replies=self.data["ticks"][self.tick];self.tick+=1
        if tuple(slots)!=old or not np.array_equal(actions,expected):
            raise AssertionError(f"Changed action or terminated slot at decision {self.tick}")
        return replies
    def finish_step(self,ticket):
        return ticket
    def advance(self,slots,actions):
        return self.finish_step(self.start_step(slots,actions))


def equal(a,b,where):
    if isinstance(a,dict):
        if a.keys()!=b.keys():raise AssertionError(f"{where} fields differ")
        for k in a:equal(a[k],b[k],f"{where}.{k}")
    elif isinstance(a,(tuple,list)):
        if len(a)!=len(b):raise AssertionError(f"{where} length differs")
        for i,(x,y) in enumerate(zip(a,b,strict=True)):equal(x,y,f"{where}[{i}]")
    elif isinstance(a,(np.ndarray,torch.Tensor)):
        if isinstance(a,torch.Tensor):a=a.detach().cpu().numpy();b=b.detach().cpu().numpy()
        if a.dtype!=b.dtype or a.shape!=b.shape or a.tobytes()!=b.tobytes():
            raise AssertionError(f"{where} array differs")
    elif a!=b:raise AssertionError(f"{where} differs")


class CheckedPool:
    """Compare both the issued actions and returned native observations with the retained trace."""
    def __init__(self,pool,record):
        self.pool=pool
        self.tape=Tape(record)
    def reset(self,paths):
        expected=self.tape.reset(paths)
        actual=self.pool.reset(paths)
        equal(actual,expected,"restored solver observations")
        return actual
    def start_step(self,slots,actions):
        expected=self.tape.start_step(slots,actions)
        return self.pool.start_step(slots,actions),expected
    def finish_step(self,ticket):
        active,expected=ticket
        actual=self.pool.finish_step(active)
        equal(actual,expected,"solved observations")
        return actual
    def advance(self,slots,actions):
        return self.finish_step(self.start_step(slots,actions))


def live_check(out,original,proposed,native_mod,record,params,args):
    dev=params[0].device
    pool=native_mod.NativePool(2)
    times={"reference":[],"candidate":[]}
    steps=0
    try:
        pool.reset(record["paths"])
        for ids,actions,_ in record["ticks"][:6]:
            steps+=sum(q["substeps"] for q in pool.advance(ids,actions).values())
        ref=None
        for key,mod in (("reference",original),("candidate",proposed),("candidate",proposed),("reference",original)):
            torch.cuda.synchronize(dev)
            begin=time.perf_counter()
            loss,stats=mod.MM03Objective.loss_for(*args,native=CheckedPool(pool,record),collect=True)
            grads=torch.autograd.grad(loss,params,allow_unused=True)
            torch.cuda.synchronize(dev)
            times[key].append(time.perf_counter()-begin)
            steps+=stats["native_substeps"]
            actual=(loss.detach().cpu(),stats,[g.detach().cpu() if g is not None else None for g in grads])
            if ref is None:
                ref=actual
            else:
                equal(ref,actual,"live CF32")
    finally:
        pool.close()
    data=dict(checked_beijing=now(),native_workers=2,actual_diagnostic_substeps=steps,
        gradient_evaluations=4,optimizer_updates=0,exact=True,wall_s=times,
        speedup=statistics.mean(times["reference"])/statistics.mean(times["candidate"]),
        scope="Two warm native workers; same H9 package, 32 anchors, every real action and observation, loss, replay arrays and all policy gradients. Four alternating H32 solves, excluding Adam.")
    write(out/"live_native_overlap.json",data)
    print(json.dumps(data),flush=True)


def check(root,out,name,original,proposed,native_mod,live):
    dev=torch.device('cuda:0')
    if name=="full_h9":
        training=root/"B/rounds/r05/H9-WM/seed1701/paired"
        spec=read(training/"spec.json")
        ck=Path(spec["parent"]);bundle=spec["bundle"]
        model,vocab,_=load_task_actor(ck,dev)
        model.low.requires_grad_(False).eval()
        cap=read(training/"fixed_cap.json")["cap"]
    else:
        training=root/"C/CF32/seed1701"
        ck=Path(read(root/"C/parent.json")["actor"]);bundle=root/"C/bridge/trajectory_bundle.pt"
        model,vocab,_=load_actor(ck,dev)
        cap=read(root/"C/calibration.json")["cap"]
    model.set_encoder_grad(False)
    obj=original.MM03Objective(bundle,dev,vocab,1701);obj.verify_actor(model)
    source=next((training/"shared_replay").glob("applied0001_step0001.npz"))
    with np.load(source) as z:
        rows=torch.as_tensor(z["rows"],device=dev)
        if list(z["keys"])!=[obj.keys[i] for i in rows.cpu().tolist()]:raise ValueError("Recovery membership differs")
    params=[p for p in model.parameters() if p.requires_grad]
    args=(obj,model,rows,"CF32",cap)
    # The same TorchScript warmup precedes both timed implementations.
    with torch.no_grad():
        for _ in range(2):obj.loss_for(model,rows,"C32",cap)
    tape=out/(name+"_native.pkl")
    if not tape.is_file():
        pool=native_mod.NativePool(1)
        capper=Capture(pool)
        try:
            loss,stats=original.MM03Objective.loss_for(*args,native=capper,collect=True)
            del loss,stats
            record=dict(paths=capper.paths,initial=capper.initial,ticks=capper.ticks,substeps=capper.steps)
            with tape.with_suffix(".part").open("wb") as f:pickle.dump(record,f,protocol=5)
            tape.with_suffix(".part").replace(tape)
            print(name,'additional diagnostic native substeps',capper.steps,flush=True)
        finally:
            pool.close()
    with tape.open("rb") as f:record=pickle.load(f)
    if live:
        live_check(out,original,proposed,native_mod,record,params,args)
        return
    def evaluate(module,retain=False):
        source_tape=Tape(record)
        loss,stats=module.MM03Objective.loss_for(*args,native=source_tape,collect=True)
        gradients=torch.autograd.grad(loss,params,allow_unused=True)
        if source_tape.tick!=len(record["ticks"]):raise AssertionError("Execution length differs")
        if retain:
            return (loss.detach().cpu(),stats,[g.detach().cpu() if g is not None else None for g in gradients])
    reference=evaluate(original,True)
    test=evaluate(proposed,True)
    equal(reference,test,name)
    times={'reference':[],'candidate':[]}
    for key,module in (('reference',original),('candidate',proposed),('candidate',proposed),('reference',original)):
        torch.cuda.synchronize(dev)
        begin=time.perf_counter();evaluate(module);torch.cuda.synchronize(dev)
        times[key].append(time.perf_counter()-begin)
    stats=reference[1]
    result=dict(name=name,checked_beijing=now(),checkpoint=str(ck),fixed_observations=str(source),batch=len(rows),
                horizon=32,gradient_tensors=len(params),captured_native_substeps=record["substeps"],optimizer_updates=0,
                identical_executed_actions_replay_fields_loss_and_all_gradients=True,
                terminal_lanes=len(stats["terminals"]),partial_intervals=sum(t["partial_dt"] is not None for t in stats["terminals"]),
                wall_s_without_native=times,gpu_part_speedup=statistics.mean(times['reference'])/statistics.mean(times['candidate']),
                timed_scope="Synchronous recorded-reply H32 forward, replay materialization and full backward; excludes native wait and Adam.",
                gradient_evaluations=6)
    write(out/(name+"_parity.json"),result)
    print(json.dumps(result),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--reference",type=Path,required=True)
    p.add_argument("--candidate",type=Path,required=True)
    p.add_argument("--native",type=Path,required=True)
    p.add_argument("--live",action="store_true")
    args=p.parse_args()
    torch.set_num_threads(1);torch.set_float32_matmul_precision('high')
    args.output.mkdir(parents=True,exist_ok=True)
    reference=load_source("learning.multimodal.mm03_timed_reference",args.reference)
    candidate=load_source("learning.multimodal.mm03_timed_candidate",args.candidate)
    native=load_source("scripts.multimodal.mm03_timed_native",args.native)
    # NativePool launches a separate 3.3.0 interpreter using its published module entry point.
    native.__name__="scripts.multimodal.mm03_c_native"
    from scripts.multimodal.mm03_launch import REPO
    native.__file__=str(REPO/"scripts/multimodal/mm03_c_native.py")
    for scenario in (("full_h9",) if args.live else ("full_h9","partial_direct23")):
        check(args.root,args.output,scenario,reference,candidate,native,args.live)
