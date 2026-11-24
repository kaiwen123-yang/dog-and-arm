"""Paired forecasts at the exact measured first commands and their open-loop tails."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.models import Dynamics
from learning.b0.contact_model import ContactRepresentation, contact_context
from learning.b0.physics import ActionMap, make_model
from learning.b0.model import tensor
from scripts.b0.training_entry_response import RAW,OUT,DEVICE


@torch.no_grad()
def main(file,tag,raw_root=RAW):
    model=make_model()
    rep=ContactRepresentation(model,DEVICE)
    m=ActionMap(model)
    ck=torch.load(file,map_location="cpu",weights_only=False)
    dyn=Dynamics(rep,23,5,tensor(m.scale,DEVICE),tensor(m.offset,DEVICE),
        tuple(ck["hidden"] if "hidden" in ck else ck["cfg"]["wm_hidden"])).to(DEVICE)
    dyn.load_state_dict(ck["dyn"])
    dyn.eval()
    dest=raw_root/("predictions_"+tag)
    dest.mkdir(exist_ok=True)
    rows=[]
    for r in json.loads((OUT/"registration.json").read_text())["starts"]:
        folder=raw_root/r["id"]
        rec=json.loads((folder/"receipt.json").read_text())
        if rec.get("rejected"):
            continue
        d=np.load(folder/"dynamics.npz")
        x=tensor(d["state"],DEVICE)
        act=tensor(d["action"],DEVICE)
        ctx=contact_context(model,r["side"],DEVICE).expand(len(x[0]),-1)
        aux=x[0,:,:7]
        rr=rep.represent(x[0])
        forecasts=[]
        with np.load(folder/"substeps.npz") as sub:
            force=np.linalg.norm(sub["door_robot_force_N"][0],axis=-1)
            both=(sub["finger_load_N"][0]>.01).all(-1)
            trphase=sub["training_phase"][0].tolist()
            ephase=sub["event_phase"][0,:,0]
        for k,action in enumerate(act):
            aux,rr=dyn(rr,action,aux,ctx)
            pred=rep.reconstruct_full_state(aux,rr)
            forecasts.append(pred.cpu().numpy())
            if k+1 not in (1,7,32):
                continue
            truth=x[k+1]
            tcp=rep.tcp_pose(aux,pred[:,7:31])[0]
            tcp0=rep.tcp_pose(truth[:,:7],truth[:,7:31])[0]
            err=pred-truth
            oracle=x[0,:,29:31]+rep.dt*(x[0,:,59:61]+rep.substep_coeff*(truth[:,59:61]-x[0,:,59:61]))
            for b,(actor,label,ch,delta) in enumerate(rec["labels"]):
                truejaw=float((truth[b,29]-truth[b,30])*1000)
                predjaw=float((pred[b,29]-pred[b,30])*1000)
                oraclejaw=float((oracle[b,0]-oracle[b,1])*1000) if k==0 else None
                tick=int(d["fail"][0,b])
                rows.append(dict(start=r["id"],split=r["split"],side=r["side"],phase=r["phase"],actor=actor,
                    branch=label,channel=ch,requested_delta=delta,
                    realized_delta=float((action[b,ch]-action[next(i for i,v in enumerate(rec["labels"]) if v[0]==actor),ch])*m.scale[ch]) if k==0 and label=="delta" else None,
                    h=k+1,legal=bool(d["valid"][k,b]),training_phase0=trphase[0],event_phase0=int(ephase[b]),
                    training_first_failure_tick20=tick,event_first_failure=(rec["judges"][b]["failure"] or {}).get("first_failure_substep"),
                    first20_peak_force_n=float(force[b].max()),first20_dual_ticks=int(both[b].sum()),
                    physical_j2=float(d["physical"][b,17]),command_mm=float(1000*d["physical"][b,22]),
                    true_mm=truejaw,pred_mm=predjaw,jaw_abs_mm=abs(predjaw-truejaw),h1_endpoint_oracle_mm=oraclejaw,
                    h1_integration_residual_mm=(oraclejaw-truejaw) if k==0 else None,
                    h1_velocity_model_residual_mm=(predjaw-oraclejaw) if k==0 else None,
                    finger_position_rmse_mm=float(1000*err[b,29:31].square().mean().sqrt()),
                    finger_velocity_rmse_m_s=float(err[b,59:61].square().mean().sqrt()),
                    arm_rmse_rad=float(err[b,23:29].square().mean().sqrt()),
                    arm_velocity_rmse_rad_s=float(err[b,53:59].square().mean().sqrt()),
                    tcp_mm=float(1000*(tcp[b]-tcp0[b]).norm()),door_rad=float(err[b,61]),door_speed_rad_s=float(err[b,62]),
                    state_rmse=float(err[b].square().mean().sqrt())))
        np.save(dest/(r["id"]+".npy"),forecasts)
    with (OUT/(tag+".csv")).open("w") as f:
        writer=csv.DictWriter(f,rows[0])
        writer.writeheader()
        writer.writerows(rows)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("wm",type=Path)
    p.add_argument("tag")
    p.add_argument("--raw",type=Path,default=RAW)
    a=p.parse_args()
    main(a.wm,a.tag,a.raw)
