"""Replay only new first commands on the retained solver state and identical measured observation."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import warp as wp
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_model import ContactRepresentation
from learning.b0.contact_policy import build_actor
from learning.b0.contact_warp import ContactPlant
from learning.b0.physics import make_model,ActionMap
from learning.b0.model import tensor
from scripts.b0.training_entry_response import BASE,OUT,RAW,DEVICE,branches,integrate_branches,phases


@torch.no_grad()
def main(args):
    model=make_model()
    rep=ContactRepresentation(model,DEVICE)
    mapping=ActionMap(model)
    actors={}
    for u in args.updates:
        ck=torch.load(BASE/args.run/f"checkpoint_{u:06d}.pt",map_location="cpu",weights_only=False)
        actor,_=build_actor(rep,ck["cfg"],model,DEVICE)
        actor.load_state_dict(ck["actor"])
        actors[f"u{u}"]=actor.eval()
    n=len(actors)*13+2
    plant=ContactPlant(model,n,DEVICE)
    raw=Path("results/raw_large/b0")/args.output
    raw.mkdir(exist_ok=False)
    for row in json.loads((OUT/"registration.json").read_text())["starts"]:
        begin=time.monotonic()
        source=RAW/row["id"]
        rec=json.loads((source/"receipt.json").read_text())
        folder=raw/row["id"]
        folder.mkdir()
        if rec.get("rejected"):
            (folder/"receipt.json").write_text(json.dumps(rec))
            continue
        saved=np.load(source/"start.npz")
        solver={k:saved[k] for k in ("qpos","qvel","qacc_warmstart","ctrl","time","load_ticks","lost_ticks","slip_ticks","sat_ticks")}
        if model.na:
            solver["act"]=saved["act"]
        q=tensor(solver["qpos"],DEVICE).expand(n,-1)
        v=tensor(solver["qvel"],DEVICE).expand(n,-1)
        plant.reset(q,v)
        for key,val in solver.items():
            buf=getattr(plant,key) if key.endswith("_ticks") else wp.to_torch(getattr(plant.sim.wp_data,key))
            buf.copy_(torch.as_tensor(val,device=DEVICE).expand_as(buf))
        plant.sim.forward()
        # Some backends may write derived warmstart during forward. The registered
        # buffer itself is what the original step consumed after its FK refresh.
        wp.to_torch(plant.sim.wp_data.qacc_warmstart).copy_(tensor(solver["qacc_warmstart"],DEVICE).expand(n,-1))
        obs=build_actor_obs_td({"motion":tensor(saved["goal"],DEVICE)},tensor(saved["history"],DEVICE))
        cmds={k:a.raw(obs)[0] for k,a in actors.items()}
        if "u0" in cmds:
            torch.testing.assert_close(cmds["u0"],tensor(saved["u0"],DEVICE),rtol=0.,atol=1e-6)
        ref=tensor(saved["reference"],DEVICE)
        labels,first=branches(cmds,ref[0],mapping.scale)
        np.savez(folder/"commands.npz",**{k:x.cpu().numpy() for k,x in cmds.items()})
        side=torch.full((n,),int(row["side"]=="push"),device=DEVICE,dtype=torch.long)
        integrate_branches(folder,row,rec["offset"],rec["frame"],rec["goal_frame"],plant,side,solver,first,ref,
            labels,phases(Path(row["path"])),rep,mapping,rec["attempts"],begin)
        print(row["id"],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",required=True)
    p.add_argument("--updates",type=int,nargs="+",required=True)
    p.add_argument("--output",required=True)
    main(p.parse_args())
