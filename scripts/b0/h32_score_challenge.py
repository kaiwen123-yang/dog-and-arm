"""Frozen-WM evaluation on newly acquired recovery and failure episodes."""
import argparse
import json
import os
from pathlib import Path
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from supermimic.models import Dynamics
from learning.b0.contact_model import ContactRepresentation
from learning.b0.contact_policy import DoorMotions
from learning.b0.model import tensor
from learning.b0.physics import ActionMap,make_model
from scripts.b0.h32_fit_recovery_wm import load_cohorts,validate
from scripts.b0.h32_recovery import write


def main(a):
    device="cuda:0"
    root=json.loads((a.data/"registration.json").read_text())
    rows=[r for r in json.loads((a.data/"cohorts.json").read_text()) if r["split"]=="validation"]
    frozen=torch.load(a.initial,map_location="cpu",weights_only=False)
    model=make_model()
    mapping=ActionMap(model)
    rep=ContactRepresentation(model,device)
    paths=[Path(root["reference_directory"])/n for n in frozen["cfg"]["references"]]
    bank=DoorMotions(paths,rep,device)
    episodes,details=load_cohorts(rows,paths,bank,model,device)
    dyn=Dynamics(rep,23,5,tensor(mapping.scale,device),tensor(mapping.offset,device),
                 tuple(frozen["cfg"]["wm_hidden"])).to(device)
    out=Path("results/b0")/a.run
    out.mkdir(exist_ok=False)
    for label,weight in (("initial",frozen),("adapted",torch.load(a.adapted,map_location="cpu",weights_only=False))):
        dyn.load_state_dict(weight["dyn"])
        dyn.eval()
        validate(rep,dyn,model,episodes,out/(label+".csv"))
    write(out/"sources.json",dict(initial=str(a.initial),adapted=str(a.adapted),validation=str(a.data),
        episodes=len(episodes),groups=[e.group for e in episodes],real_transitions=sum(len(e.action) for e in episodes),
        genuine_failure_transitions=sum(int(np.sum(d["terminated"])) for d in details)))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--initial",type=Path,required=True)
    p.add_argument("--adapted",type=Path,required=True)
    p.add_argument("--run",required=True)
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", ".."):
        p.error("Fresh run name required")
    main(a)
