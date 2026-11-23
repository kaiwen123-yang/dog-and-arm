"""Fit and validate a real one-interval contact failure predictor before using it in imagination."""
import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from torch import nn
from learning.b0.contact_model import ContactRepresentation
from learning.b0.contact_policy import DoorMotions
from learning.b0.physics import make_model
from learning.b0.contact_warp import PHASES,REASONS
from scripts.b0.h32_fit_recovery_wm import load_cohorts,csv_out
from scripts.b0.h32_recovery import write


class FailureHead(nn.Module):
    def __init__(self,rep_dim):
        super().__init__()
        size=rep_dim+23+5+len(PHASES)
        self.register_buffer("mean",torch.zeros(size))
        self.register_buffer("scale",torch.ones(size))
        self.net=nn.Sequential(nn.Linear(size,128),nn.SiLU(),nn.Linear(128,64),nn.SiLU(),nn.Linear(64,1))
    def features(self,rep,action,ctx,phase):
        return torch.cat((rep,action,ctx,nn.functional.one_hot(phase,len(PHASES)).float()),-1)
    def forward(self,rep,action,ctx,phase):
        x=self.features(rep,action,ctx,phase)
        return self.net(((x-self.mean)/self.scale).clamp(-15,15)).squeeze(-1)


def summarize(p,y,threshold):
    pred=p>=threshold
    tp=int((pred & y).sum())
    tn=int((~pred & ~y).sum())
    fp=int((pred & ~y).sum())
    fn=int((~pred & y).sum())
    return dict(tp=tp,tn=tn,fp=fp,fn=fn,precision=tp/max(1,tp+fp),recall=tp/max(1,tp+fn),
                fpr=fp/max(1,tn+fp),f1=2*tp/max(1,2*tp+fp+fn))


def main(a):
    device="cuda:0"
    torch.manual_seed(77)
    np.random.seed(77)
    spec=json.loads((a.data/"registration.json").read_text())
    rows=json.loads((a.data/"cohorts.json").read_text())
    anchor=torch.load(spec["anchor"],weights_only=False,map_location="cpu")
    paths=[Path(spec["reference_directory"])/n for n in anchor["cfg"]["references"]]
    rep=ContactRepresentation(make_model(),device)
    bank=DoorMotions(paths,rep,device)
    episodes,details=load_cohorts(rows,paths,bank,make_model(),device)
    head=FailureHead(rep.rep_state_dim).to(device)
    splits={}
    for split in ("train","calibration","validation"):
        select=[(ep,d) for ep,d in zip(episodes,details) if ep.split==split]
        s=torch.cat([e.state[:-1] for e,d in select])
        ss=torch.cat([e.state[1:] for e,d in select])
        ctx=torch.cat([e.context.expand(len(e.action),-1) for e,d in select])
        actions=torch.cat([e.action for e,d in select])
        frames=torch.as_tensor(np.concatenate([d["frames"] for e,d in select]),device=device)
        phase=torch.as_tensor(np.concatenate([d["phase"] for e,d in select]),device=device)
        y=torch.as_tensor(np.concatenate([d["terminated"] for e,d in select]),device=device)
        raw=rep.represent(s)
        features=head.features(raw,actions,ctx,phase)
        # This oracle applies official height/tilt soft termination to the *measured* successor.
        # Even perfect prediction of the root cannot make a missing contact criterion visible here.
        rpos,rquat=bank.body_state(frames+1)[:2]
        height=(rpos[:,0,2]-ss[:,2]).abs()/.1
        tilt=(2*(ss[:,4:6].square().sum(-1)-rquat[:,0,1:3].square().sum(-1))).abs()/.12
        p_root=torch.sigmoid((torch.maximum(height,tilt)-1)/.05)
        splits[split]=(features,y,p_root,np.concatenate([d["reason"] for e,d in select]),phase)
    x,y,*_=splits["train"]
    head.mean.copy_(x.mean(0))
    head.scale.copy_(x.std(0).clamp_min(.002))
    def predict(x):
        return head.net(((x-head.mean)/head.scale).clamp(-15,15)).squeeze(-1)
    opt=torch.optim.AdamW(head.net.parameters(),lr=.001)
    pos=y.nonzero().flatten()
    neg=(~y).nonzero().flatten()
    if min(len(pos),len(neg))<1:
        raise ValueError("Both event classes required")
    out=Path("results/b0")/a.run
    out.mkdir(exist_ok=False)
    write(out/"registration.json",dict(raw=str(a.data),split="allocation inherited from source cohorts",
        target="first hard failure anywhere in upcoming ten real 2ms solves; one binary per 20ms transition",
        features="current 75D GenCoord with relative handle/door geometry, current 23 normalized targets, 5 context and current fixed reference phase. No future physical state.",
        selection="800 balanced 256-sample batches; fixed final checkpoint, threshold chosen by calibration F1 among thresholds with FPR<=1%; accept for H32 only if validation precision and recall >=0.5 and FPR<=1%.",seed=77))
    for step in range(800):
        idx=torch.cat((pos[torch.randint(len(pos),(128,),device=device)],neg[torch.randint(len(neg),(128,),device=device)]))
        loss=nn.functional.binary_cross_entropy_with_logits(predict(x[idx]),y[idx].float())
        opt.zero_grad()
        loss.backward()
        opt.step()
    with torch.no_grad():
        cal=torch.sigmoid(predict(splits["calibration"][0])).cpu().numpy()
        yc=splits["calibration"][1].cpu().numpy()
        choices=[(summarize(cal,yc,t),float(t)) for t in np.r_[np.linspace(0.,1.,501),np.nextafter(1.,2.)]]
        threshold=max((c for c in choices if c[0]["fpr"]<=.01),key=lambda z:(z[0]["f1"],z[1]))[1]
        scores=[]
        reasons=[]
        for split,(x,y,root,why,phase) in splits.items():
            yp=torch.sigmoid(predict(x)).cpu().numpy()
            y=y.cpu().numpy()
            root=root.cpu().numpy()
            for name,probs,t in (("head",yp,threshold),("upper_bound_true_root_of_official_rule",root,.5)):
                scores.append(dict(split=split,model=name,threshold=t,**summarize(probs,y,t),
                    p50_hard_fail=np.median(probs[y]).item() if y.any() else None,
                    p50_nonterminal=np.median(probs[~y]).item()))
                for code,label in enumerate(REASONS):
                    sel=why==code
                    if sel.any():
                        reasons.append(dict(split=split,model=name,reason=label,n=int(sel.sum()),flagged=int((probs[sel]>=t).sum())))
        csv_out(out/"confusion.csv",scores)
        csv_out(out/"failure_reasons.csv",reasons)
        v=next(r for r in scores if r["model"]=="head" and r["split"]=="validation")
        accept=(v["precision"]>=.5 and v["recall"]>=.5 and v["fpr"]<=.01)
        write(out/"outcome.json",dict(accepted_for_diagnostic=accept,threshold=threshold,validation=v,
              application="A pass warrants an explicitly named contact risk diagnostic. Balanced logits are classification scores; no direct interpretation as calibrated per-step event probability."))
        torch.save(dict(model=head.state_dict(),threshold=threshold,seed=77,optimizer=opt.state_dict(),rng=torch.get_rng_state(),gpu_rng=torch.cuda.get_rng_state(),numpy_rng=np.random.get_state()),out/"head.pt")
        print(v,accept,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",required=True,type=Path)
    p.add_argument("--run",required=True)
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", ".."):
        p.error("Select a fresh output directory")
    main(a)
