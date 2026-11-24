"""Compare only like contact modes for paired H1 local physical responses."""
import csv
import json
from pathlib import Path

import numpy as np
import torch
from learning.b0.contact_model import ContactRepresentation
from learning.b0.model import tensor
from learning.b0.physics import make_model
from scripts.b0.training_entry_response import OUT, RAW, DEVICE


@torch.no_grad()
def main():
    rep=ContactRepresentation(make_model(),DEVICE)
    directions=[]
    for row in json.loads((OUT/"registration.json").read_text())["starts"]:
        folder=RAW/row["id"]
        rec=json.loads((folder/"receipt.json").read_text())
        if rec.get("rejected"):
            continue
        d=np.load(folder/"dynamics.npz")
        with np.load(folder/"substeps.npz") as sub:
            first_contact=sub["finger_load_N"][0]>.01
            qp=tensor(sub["qpos_post"],DEVICE)
            flat=qp.flatten(0,2)
            tcp=torch.cat([rep.tcp_pose(chunk[:,:7],chunk[:,7:31])[0] for chunk in flat.split(4096)])
            np.save(folder/"substep_tcp_post_m.npy",tcp.reshape(*qp.shape[:3],3).cpu().numpy())
        available=[tag for tag in ("response_w0","response_w200","response_w1000","previous_u200","response_u1","response_u10","response_u50")
                   if (RAW/("predictions_"+tag)/(row["id"]+".npy")).exists()]
        predictors={tag:np.load(RAW/("predictions_"+tag)/(row["id"]+".npy"),mmap_mode="r")[0] for tag in available}
        truth=d["state"][1]
        labels=rec["labels"]
        for b,(actor,kind,ch,requested) in enumerate(labels):
            if kind!="delta":
                continue
            center=next(i for i,v in enumerate(labels) if v[:2]==[actor,"actor"])
            repeat=next(i for i,v in enumerate(labels) if v[:2]==[actor,"repeat"])
            delta=d["physical"][b,ch]-d["physical"][center,ch]
            def gap(x,i):
                return float(x[i,29]-x[i,30])
            dy=gap(truth,b)-gap(truth,center)
            noise=abs(gap(truth,repeat)-gap(truth,center))
            same=bool(np.array_equal(first_contact[b],first_contact[center]) and
                np.array_equal(first_contact[repeat],first_contact[center]) and
                d["fail"][0,b]==d["fail"][0,center]==d["fail"][0,repeat])
            credible=bool(same and abs(dy)>noise and abs(delta)>1e-10)
            result=dict(start=row["id"],split=row["split"],side=row["side"],phase=row["phase"],
                actor=actor,channel=ch,requested_delta=requested,actual_delta=delta,matched_contact_pattern=same,
                repeat_noise_mm=1000*noise,observed_delta_mm=1000*dy,interpretable=credible,
                true_slope_m_per_unit=dy/delta if abs(delta)>1e-10 else None)
            for name,x in predictors.items():
                result[name+"_m_per_unit"]=(gap(x,b)-gap(x,center))/delta if abs(delta)>1e-10 else None
            directions.append(result)
    with (OUT/"h1_local_directions.csv").open("w") as f:
        w=csv.DictWriter(f,directions[0])
        w.writeheader()
        w.writerows(directions)


if __name__=="__main__":
    main()
