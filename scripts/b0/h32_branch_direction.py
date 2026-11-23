"""Compare real vs model directions after local jaw perturbations and an H32 update."""
import argparse
import collections
import csv
import json
import os
from pathlib import Path
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from supermimic.models import Dynamics
from learning.b0.contact_model import ContactRepresentation,contact_context
from learning.b0.model import tensor
from learning.b0.physics import ActionMap,make_model
from scripts.b0.h32_fit_recovery_wm import csv_out
from scripts.b0.h32_recovery import write


FIELDS=("tcp_rod_mm","door_deg","jaw_width_mm")
TOL=np.array([.01,.001,.01])  # small-effect band for this diagnostic, never used for task scoring


def endpoints(rep,back):
    r=torch.where(back[:,None],rep[:,66:69],rep[:,63:66])
    return torch.stack((1000*torch.linalg.vector_norm(r,dim=-1),torch.rad2deg(rep[:,58]),
                        1000*(rep[:,32]-rep[:,33])),-1)


@torch.no_grad()
def rollout(path,wm,rep,model,device):
    spec=json.loads((path/"branches.json").read_text())
    raw=Path(spec["raw"])
    S=tensor(np.load(raw/"state.npy"),device)
    A=tensor(np.load(raw/"clipped.npy"),device)
    V=np.load(raw/"valid.npy")
    M=np.load(raw/"mode.npy")
    ids=[l["id"] for l in spec["lanes"]]
    back=torch.tensor([name.startswith("push") for name in ids],device=device)
    ctx=torch.stack([contact_context(model,side,device) for side in ("pull","push")])[back.long()]
    aux=S[:,0,:7]
    r=rep.represent(S[:,0])
    initial=endpoints(r,back)
    data={}
    for t in range(32):
        aux,r=wm(r,A[:,t],aux,ctx)
        h=t+1
        if h in (1,7,32):
            actual=endpoints(rep.represent(S[:,h]),back)
            predicted=endpoints(r,back)
            data[h]=dict(real=(actual-initial).cpu().numpy(),wm=(predicted-initial).cpu().numpy(),
                         alive=V[:,:h].all(axis=1),mode=M[:,0],final_mode=M[:,t],
                         start=initial.cpu().numpy(),root0=S[:,0,:3].cpu().numpy(),
                         state0=S[:,0].cpu().numpy(),first_command=A[:,0].cpu().numpy())
    return ids,data


def compare(rows,kind,name,h,ref,alt,i,j):
    if not (ref["alive"][i] and alt["alive"][j]):
        return
    real,model=(alt[key][j]-ref[key][i] for key in ("real","wm"))
    start_delta=alt["start"][j]-ref["start"][i]
    for k,field in enumerate(FIELDS):
        r,p=float(real[k]),float(model[k])
        rsign=int(np.sign(r)) if abs(r)>TOL[k] else 0
        psign=int(np.sign(p)) if abs(p)>TOL[k] else 0
        rows.append(dict(comparison=kind,branch=name,h=h,start_mode=ref["mode"][i],end_mode=alt["final_mode"][j],metric=field,
              real_change_vs_reference=r,wm_change_vs_reference=p,numerical_band=TOL[k],
              real_sign=rsign,wm_sign=psign,outcome="real_small" if not rsign else "model_small" if not psign else "same" if rsign==psign else "opposite",
              paired_initial_endpoint_delta=float(start_delta[k]),paired_initial_root_distance_mm=float(1000*np.linalg.norm(alt["root0"][j]-ref["root0"][i]))))


def main(a):
    out=Path("results/b0")/a.run
    out.mkdir(exist_ok=False)
    write(out/"registration.json",dict(initial=str(a.initial),updated=str(a.updated),
        horizons=[1,7,32],numerical_bands=dict(zip(FIELDS,TOL.tolist())),
        metric="For each branch integrate its actual, clipped, held physical action sequence from its own measured start, without reinjecting measured future states. Subtract the endpoint change of the zero-offset branch (or the initial Actor's zero-offset branch) from the compared endpoint change. Report both signed values; separate real/model near-zero effects. No predicted force.",
        pairing="Same registered reference frame and teacher prefix. Actual state differences between separately integrated Warp lanes are explicitly measured and reported; change from each lane's physical start is used for differencing. Results near that scale require caution."))
    model=make_model()
    mapping=ActionMap(model)
    device="cuda:0"
    rep=ContactRepresentation(model,device)
    rows=[]
    for tag,item in (("frozen",a.initial),("after_u1",a.updated)):
        spec=json.loads((item/"branches.json").read_text())
        w=torch.load(spec["checkpoint"],weights_only=False,map_location="cpu")
        wm=Dynamics(rep,23,5,tensor(mapping.scale,device),tensor(mapping.offset,device),tuple(w["cfg"]["wm_hidden"])).to(device)
        wm.load_state_dict(w["dyn"])
        wm.eval()
        ids,base=rollout(a.initial,wm,rep,model,device)
        ids2,new=rollout(a.updated,wm,rep,model,device)
        if ids!=ids2:
            raise ValueError("intervention IDs differ")
        current=base if tag=="frozen" else new
        for h in (1,7,32):
            for j,name in enumerate(ids):
                prefix,offset=name.rsplit("_",1)
                i=ids.index(prefix+"_+0mm")
                if i!=j:
                    compare(rows,tag+"_jaw",name,h,current[h],current[h],i,j)
                else:
                    compare(rows,tag+"_wm_actor_update",name,h,base[h],new[h],i,j)
    csv_out(out/"directions.csv",rows)
    grouped=collections.defaultdict(collections.Counter)
    for r in rows:
        for mode in (r["start_mode"],"all"):
            grouped[r["comparison"],r["h"],mode,r["metric"]][r["outcome"]]+=1
    summary=[]
    for (kind,h,mode,metric),m in sorted(grouped.items()):
        summary.append(dict(comparison=kind,h=h,mode=mode,metric=metric,n=sum(m.values()),
                            real_small=m["real_small"],model_small=m["model_small"],same=m["same"],opposite=m["opposite"]))
    csv_out(out/"summary.csv",summary)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--initial",type=Path,required=True)
    p.add_argument("--updated",type=Path,required=True)
    p.add_argument("--run",required=True)
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", ".."):
        p.error("Fresh output directory required")
    main(a)
