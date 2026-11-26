"""Resolve the local scale of the fixed C parent imagination derivative in double precision."""
import argparse
import json
from pathlib import Path

import torch
from learning.multimodal.actor import load_actor
from learning.multimodal.mm03_model import MM03Objective
from scripts.multimodal.mm03_c import read, report


def check(root):
    out=root/"C"
    if (out/"directional_local_fp64.json").is_file():
        return
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("highest")
    device=torch.device("cuda:0")
    father=read(out/"parent.json")
    actor,vocab,_=load_actor(father["actor"],device)
    actor.freeze_encoders()
    obj=MM03Objective(out/"bridge/trajectory_bundle.pt",device,vocab,1701)
    obj.verify_actor(actor)
    # The fixed observed images/text are encoded once in their original inference precision.
    # All perturbed recurrent dynamics, task heads and trajectory losses run in float64.
    actor.double()
    obj.model.double()
    obj.bridge.double()
    obj.obs={k:x.double() if x.is_floating_point() else x for k,x in obj.obs.items()}
    obj.targets={k:x.double() if x.is_floating_point() else x for k,x in obj.targets.items()}
    old=read(out/"directional_response.json")
    cap=read(out/"calibration.json")["cap"]
    results=[]
    calls=0
    for selection in old["strata"]:
        keys=selection.get("anchors",[])
        if not keys:
            results.append(dict(stratum=selection["stratum"],n=0))
            continue
        idx=torch.tensor([obj.keys.index(k) for k in keys],device=device)
        bias=actor.head[-1].bias
        initial=bias.detach().clone()
        try:
            cost,stats=obj.loss_for(actor,idx,"C32",cap)
            calls+=stats["model_queries"]
            grad,=torch.autograd.grad(cost,bias)
            direction=grad.detach()/grad.detach().norm().clamp_min(1e-16)
            ad=float(grad@direction)
            comparisons=[]
            with torch.no_grad():
                for eps in (2e-3,5e-4,1e-4,2e-5,4e-6,8e-7,1.6e-7,3.2e-8,6.4e-9):
                    values=[]
                    for sign in (1,-1):
                        bias.copy_(initial+(sign*eps)*direction)
                        val,di=obj.loss_for(actor,idx,"C32",cap)
                        values.append(float(val))
                        calls+=di["model_queries"]
                    fd=(values[0]-values[1])/(2*eps)
                    comparisons.append(dict(epsilon=eps,plus=values[0],minus=values[1],central=fd,
                                            error_relative=abs(fd-ad)/max(abs(ad),1e-10)))
            results.append(dict(stratum=selection["stratum"],n=len(keys),keys=keys,
                                autograd_fp64=ad,base_loss=float(cost.detach()),central_differences=comparisons))
        finally:
            with torch.no_grad():
                bias.copy_(initial)
    report(out/"directional_local_fp64.json",dict(strata=results,model_queries=calls,actor_updates=0,native_substeps=0,
           finite_difference="fixed observed encoder outputs, double precision trainable head and closed-loop model"))
    print(json.dumps(results),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    check(p.parse_args().root)
