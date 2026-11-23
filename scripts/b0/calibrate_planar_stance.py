"""Compare one scalar planar feedback rate on independent registered Warp starts at a fixed clock."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td
from learning.b0.contact_policy import DoorMotions, PRIVILEGED_TRANSLATION, build_actor, sensor
from learning.b0.contact_warp import ContactPlant, PHASE_ID
from learning.b0.model import RobotRepresentation, full_state
from learning.b0.physics import build, settings
from learning.b0.stance_base import PlanarStanceFeedback
from scripts.b0.recovery_bc import ANCHOR, AUGMENT, DESIGN, REF, REFERENCE, dump, migrate


@torch.no_grad()
def run_side(side, all_cases, rates, weights, device):
    cases = [c for c in all_cases if c["side"]==side]
    cases += [dict(episode_id="nominal",split="nominal",side=side)]
    ref_dir = REFERENCE/REF[side]
    path = lambda c: ref_dir if c["episode_id"]=="nominal" else AUGMENT/c["episode_id"]
    q0 = np.stack([np.load(path(c)/"qpos.npy",mmap_mode="r")[0] for c in cases for _ in rates])
    v0 = np.stack([np.load(path(c)/"qvel.npy",mmap_mode="r")[0] for c in cases for _ in rates])
    m = build(settings("mobile" if side=="pull" else "push",1))
    rep = RobotRepresentation(m,device)
    bank = DoorMotions([ref_dir],rep,device)
    cfg = weights["cfg"]
    actor,_ = build_actor(rep,cfg,m,device)
    actor.load_state_dict(weights["actor"]);actor.eval()
    controller = PlanarStanceFeedback(m).to(device)
    plant = ContactPlant(m,len(q0),device)
    q,v = [torch.tensor(a,dtype=torch.float32,device=device) for a in (q0,v0)]
    plant.reset(q,v)
    prev=torch.zeros((len(q),23),device=device)
    hist=sensor(rep,full_state(q,v),prev)[:,None].expand(-1,10,-1).clone()
    sides=torch.full((len(q),),int(side=="push"),device=device)
    rates_tensor = torch.tensor(rates * len(cases),device=device)[:,None]
    phases=np.load(ref_dir/"phase.npy")
    end = int(np.flatnonzero(phases==bank.metas[ref_dir.name]["phases"].index("settle"))[-1])+1
    offset, heading, failed=[],[],torch.zeros(len(q),device=device,dtype=torch.int64)
    for k in range(end):
        frame = torch.full((len(q),),k,device=device)
        wm,g=bank.goals(rep,frame,q[:,:7])
        obs=build_actor_obs_td({"motion":g},hist)
        base=actor.raw(obs)
        err=wm[:,480:482]
        yaw=torch.atan2(g[:,482],g[:,480])
        action=controller(base,prev,err,yaw,rates_tensor)
        action=torch.where(rates_tensor==0,base,action).clamp(-1,1)
        pid=PHASE_ID[bank.metas[ref_dir.name]["phases"][phases[k]]]
        measured=plant.step_contact(action,sides,torch.full_like(sides,pid))
        hit=(failed==0)&((measured["first_fail_substep"]>0)|(~measured["valid_full_interval"]))
        failed[hit]=k+1
        q,v=plant.data.qpos[:].clone(),plant.data.qvel[:].clone()
        prev=action
        hist=torch.cat((hist[:,1:],sensor(rep,full_state(q,v),prev)[:,None]),dim=1)
        offset.append((q[:,:2]-bank.qpos[k+1,:2]).norm(dim=1))
        _,gn=bank.goals(rep,frame+1,q[:,:7])
        heading.append(torch.atan2(gn[:,482],gn[:,480]).abs()*180/np.pi)
    distance=torch.stack(offset)[-30:].amax(0).cpu().numpy()
    turn=torch.stack(heading)[-30:].amax(0).cpu().numpy()
    rows=[]
    for i,(c,rate) in enumerate((c,rate) for c in cases for rate in rates):
        rows.append(dict(side=side,episode=c["episode_id"],split=c["split"],gain_per_s=rate,
             policy_steps=end,last_600ms_max_xy_error_mm=float(distance[i]*1000),last_600ms_max_yaw_deg=float(turn[i]),
             first_collector_failure_tick=int(failed[i]),last_600ms_at_reference=bool(distance[i]<.010 and turn[i]<1. and failed[i]==0)))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",required=True)
    p.add_argument("--package-from",type=Path,help="Package the registered rate selected on measured training starts")
    a=p.parse_args()
    if Path(a.run).name!=a.run: p.error("fresh run name required")
    out=Path("results/b0")/a.run;out.mkdir(exist_ok=False)
    if a.package_from:
        measured=json.loads((a.package_from/"selection.json").read_text())
        old=torch.load(ANCHOR,map_location="cpu",weights_only=False)
        cfg=dict(old["cfg"],actor_goal_schema=PRIVILEGED_TRANSLATION,planar_stance_rate=measured["gain"],
                 reference_directory=str(REFERENCE))
        model=build(settings("mobile",1))
        rep=RobotRepresentation(model,"cpu")
        actor,_=build_actor(rep,cfg,model,"cpu")
        migrate(old["actor"],actor)
        torch.save(dict(old,cfg=cfg,actor=actor.state_dict(),planar_fit=str(a.package_from)),
                   out/"checkpoint_000000.pt")
        dump(out/"actual_config.json",dict(source=str(ANCHOR),fit=str(a.package_from),cfg=cfg,
             optimizer="one scalar selected by actual independent training-start rollouts, no H32 in this fit",
             nominal_encoder="old 540 columns copied, 30 XYZ encoder columns start at zero; deterministic leg/wheel feedback sees the current root"))
        return
    rates=[0.,1.,2.,4.]
    cases=json.loads(DESIGN.read_text())["cases"]
    dump(out/"registration.json",dict(rates=rates,anchor=str(ANCHOR),reference=str(REFERENCE),
      starts="all 16 registered independent training/validation starts plus both nominal; no C/H",
      target="max planar error <10mm and max heading error <1 degree for last 600ms of frozen settle; no collector hard failure",
      selection="largest number passing across 12 training episodes; ties lower max planar error, then smaller gain",
      scope="local real-physics station diagnostic through fixed reference settle only, not official full scoring",
      per_action_bounds="wheel correction +/-1.5 rad/s, leg correction +/-0.245 rad; native physical judge unchanged"))
    w=torch.load(ANCHOR,map_location="cpu",weights_only=False)
    results=[]
    for side in REF:
        results.extend(run_side(side,cases,rates,w,"cuda:0"))
        print(side,flush=True)
    dump(out/"stations.json",results)
    by_gain=[]
    for rate in rates:
        row=[r for r in results if r["split"]=="train" and r["gain_per_s"]==rate]
        by_gain.append((sum(r["last_600ms_at_reference"] for r in row),-max(r["last_600ms_max_xy_error_mm"] for r in row),-rate))
    gain=-max(by_gain)[2]
    dump(out/"selection.json",dict(gain=gain,training_comparison=by_gain,rows=len(results)))
    print("selected",gain,flush=True)


if __name__=="__main__":
    main()
