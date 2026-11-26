"""Check loss, every gradient, weight reloads and elapsed CUDA time on observed H7 windows."""
import argparse
import json
from pathlib import Path
import statistics
import time

import torch

from learning.multimodal.wm_replay import PhysicalReplay
from learning.multimodal.world_model import PerceptualDynamics
from scripts.multimodal.mm03_launch import write, now
from scripts.multimodal.train_wm import physical_loss


def compare(root,output,graph_class):
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    dev=torch.device("cuda:0")
    points=[root/f"B/rounds/r{r:02d}/wm/seed1701/wm.pt" for r in (1,2)]
    states=[torch.load(p,map_location=dev,weights_only=False) for p in points]
    reference,model=[PerceptualDynamics(states[0]["width"]).to(dev) for _ in range(2)]
    for item in (reference,model):
        item.load_state_dict(states[0]["model"])
    episodes=[root/"B/teachers"/f"teacher_26112600_tr_nominal_{s}15"/"episode" for s in ("pull","push")]
    data=PhysicalReplay(None,"train",dev,episode_dirs=episodes)
    starts,_=data.starts(7)
    rng=torch.Generator(device=dev).manual_seed(1701026)
    windows=[data.window(starts[torch.randint(len(starts),(128,),device=dev,generator=rng)],7) for _ in range(8)]
    candidate=graph_class(model)
    def eager(batch):
        reference.zero_grad(set_to_none=True)
        loss=physical_loss(reference,batch)
        loss.backward()
        return loss

    cold=eager(windows[0]).detach().clone()
    cold_grads=[p.grad.clone() for p in reference.parameters()]
    ready=eager(windows[0])
    eager_startup=dict(loss_max_abs=(cold-ready).abs().item(),
        gradient_max_abs=max((a-b.grad).abs().max().item() for a,b in zip(cold_grads,reference.parameters(),strict=True)))
    rows=[]
    for i,batch in enumerate(windows):
        if i==4:
            for item in (model,reference):
                item.load_state_dict(states[1]["model"])
        a=eager(batch)
        b=candidate.backward(batch)
        maxloss=(a-b).abs().item()
        maxgrad=max((x.grad-y.grad).abs().max().item() for x,y in zip(reference.parameters(),model.parameters(),strict=True))
        if not (torch.isfinite(a).item() and torch.isfinite(b).item()):
            raise FloatingPointError("Nonfinite H7 comparison")
        rows.append(dict(batch=i,source=str(points[i//4]),loss_max_abs=maxloss,grad_max_abs=maxgrad))
        if maxloss!=0 or maxgrad!=0:
            print(json.dumps(rows[-1]),flush=True)
        # Confirm that capture overwrites old gradient storage as normal Adam training requires.
        for p in model.parameters():
            p.grad.fill_(7.0)
    observations={"eager":[],"graph":[]}
    for name in ("eager","graph","graph","eager"):
        grad=eager if name=="eager" else candidate.backward
        torch.cuda.synchronize(dev)
        st=time.monotonic()
        for j in range(16):
            grad(windows[j%len(windows)])
        torch.cuda.synchronize(dev)
        observations[name].append((time.monotonic()-st)/16)
    e,g=[statistics.mean(v) for v in observations.values()]
    result=dict(checked_beijing=now(),eager_vs_eager_first_calls=eager_startup,capture_guard=candidate.check,episodes=list(map(str,episodes)),batch=128,horizon=7,
                weight_points=list(map(str,points)),comparisons=rows,eager_ms=1000*e,graph_ms=1000*g,
                speedup=e/g,time_per_actual_backward_s=observations,graph_replays=candidate.replays,
                exact=all(row["loss_max_abs"]==0 and row["grad_max_abs"]==0 for row in rows),
                diagnostic_grad_evaluations=2+2*len(windows)+4*16+candidate.extra_gradient_evaluations,
                optimizer_updates=0,native_steps=0)
    write(output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("comparisons","time_per_actual_backward_s","episodes")}),flush=True)
    if not result["exact"] or candidate.disabled:
        raise RuntimeError("H7 backward differs from the eager reference")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        from scripts.multimodal.mm03_h7_graph import H7Backward
    except ModuleNotFoundError:
        from mm03_h7_graph import H7Backward
    compare(a.root,a.output,H7Backward)

