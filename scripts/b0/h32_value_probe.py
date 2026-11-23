"""Held-out real failure values and Actor commands on identical measured histories."""
import argparse
import json
import os
from pathlib import Path
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from supermimic.models import build_mlp
from supermimic.tasks.task_spec import build_actor_obs_td
from learning.b0.contact_model import ContactRepresentation
from learning.b0.contact_policy import DoorMotions,actor_goal_schema,build_actor
from learning.b0.physics import ActionMap,make_model
from scripts.b0.h32_fit_recovery_wm import csv_out,load_cohorts
from scripts.b0.h32_recovery import write


@torch.no_grad()
def main(a):
    device="cuda:0"
    model=make_model()
    mapping=ActionMap(model)
    rep=ContactRepresentation(model,device)
    spec=json.loads((a.data/"registration.json").read_text())
    rows=[r for r in json.loads((a.data/"cohorts.json").read_text()) if r["split"]=="validation"]
    weights=[torch.load(p,weights_only=False,map_location="cpu") for p in a.checkpoints]
    cfg=weights[0]["cfg"]
    paths=[Path(spec["reference_directory"])/n for n in cfg["references"]]
    bank=DoorMotions(paths,rep,device)
    eps,ds=load_cohorts(rows,paths,bank,model,device)
    st=torch.cat([e.state[:-1] for e in eps])
    context=torch.cat([e.context.expand(len(e.action),-1) for e in eps])
    frames=torch.as_tensor(np.concatenate([d["frames"] for d in ds]),device=device)
    label=np.concatenate([d["terminated"] for d in ds])
    phase=np.concatenate([d["phase"] for d in ds])
    sides=context[:,0].cpu().numpy()
    goal,_=bank.goals(rep,frames,st[:,:7])
    obs=torch.cat([rep.represent(st),goal,context],-1)
    # Probe actual actions without synthetic noise on identical recorded histories and reference clocks.
    co=torch.load(a.replay,weights_only=False,map_location=device)
    chunk, indices=co["replay"][0]
    ij=indices[1]
    sample=chunk[ij[:,0],ij[:,1]]
    banks={"proprio_motion":bank}
    anchor_action=None
    results=[]
    for checkpoint,states in zip(a.checkpoints,weights):
        critic=build_mlp(rep.rep_state_dim+570+5,tuple(cfg["critic_hidden"]),1).to(device)
        critic.load_state_dict(states["critic"])
        critic.eval()
        pred=critic(obs).squeeze(-1).cpu().numpy()
        paired=[]
        for i in np.flatnonzero(label):
            matched=(phase==phase[i]) & (sides==sides[i]) & ~label
            if matched.any():
                paired.append(np.mean(pred[i]<pred[matched]))
        schema=actor_goal_schema(states["cfg"])
        if schema not in banks:
            banks[schema]=DoorMotions(paths,rep,device,actor_schema=schema)
        _,ag=banks[schema].goals(rep,sample["motion_time"],sample["state"][:,:7],sample["state"][:,61])
        act_obs=build_actor_obs_td({"motion":ag},sample["history"].unflatten(-1,(10,77)))
        actor,_=build_actor(rep,states["cfg"],model,device)
        actor.load_state_dict(states["actor"])
        actor.eval()
        action=actor(act_obs).cpu().numpy()
        if anchor_action is None:
            anchor_action=action
        change=np.abs((action-anchor_action)*mapping.scale)
        results.append(dict(checkpoint=str(checkpoint),real_term=int(label.sum()),ordinary=int((~label).sum()),
              median_v_terminal=float(np.median(pred[label])),median_v_nonterminal=float(np.median(pred[~label])),
              p_terminal_below_phase_and_side_matched_ordinary=float(np.mean(paired)),pairs_with_negative=len(paired),
              replay_identical_histories=len(ij),max_dleg_rad=float(change[:,:12].max()),max_dwheel_rad_s=float(change[:,12:16].max()),
              max_darm_rad=float(change[:,16:22].max()),max_djaw_m=float(change[:,22].max())))
    out=Path("results/b0")/a.run
    out.mkdir(exist_ok=False)
    csv_out(out/"probe.csv",results)
    write(out/"source.json",dict(failure_validation=str(a.data),actual_action_replay=str(a.replay),
          description="Compare critic on real current observations before terminal versus nonterminal rows matched within side and reference phase. Actor deltas use same replay histories for all packages (no observation noise, clipped commands in physical units)."))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data",type=Path,required=True)
    p.add_argument("--replay",type=Path,required=True)
    p.add_argument("--checkpoints",nargs="+",type=Path,required=True)
    p.add_argument("--run",required=True)
    a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ("", ".", ".."):
        p.error("Fresh run directory required")
    main(a)
