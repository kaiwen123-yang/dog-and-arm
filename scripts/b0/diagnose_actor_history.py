"""Separate proprio and previous-action dependence on one measured closed-loop failure."""
from argparse import ArgumentParser
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions, build_actor, sensor
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import ActionMap, make_model
from scripts.b0.calibrate_contact_actor import save


@torch.no_grad()
def diagnose(args):
    r=json.loads(args.result.read_text())
    actual=Path(r["raw_directory"])
    ref=Path("results/raw_large/b0/contact_held_r1")/r["episode"]
    out=args.output
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    model=make_model()
    dev=args.device
    rep=RobotRepresentation(model,dev)
    bank=DoorMotions([ref],rep,dev)
    checkpoint=torch.load(args.checkpoint,weights_only=False,map_location=dev)
    actor,_=build_actor(rep,checkpoint["cfg"],model,dev)
    actor.load_state_dict(checkpoint["actor"])
    actor.eval()
    a,q,v=[tensor(np.load(actual/(f+".npy")),dev) for f in ("clipped_action","qpos","qvel")]
    count=len(a)
    offset=r["start_substep"]//10
    refq,refv,refprev,refa=[tensor(np.load(ref/(f+".npy"))[offset:offset+count],dev)
                              for f in ("qpos","qvel","last_action","action_clipped")]
    k=torch.arange(10,count,device=dev)
    window=k[:,None]+torch.arange(-9,1,device=dev)
    _,goal=bank.goals(rep,k+offset,q[k,:7])
    measurements={}
    scale=tensor(ActionMap(model).scale,dev)
    for label,sq,sv,sp in (("measured_both",q[1:count],v[1:count],a[:-1]),
                            ("teacher_proprio_only",refq[1:],refv[1:],a[:-1]),
                            ("teacher_previous_only",q[1:count],v[1:count],refprev[1:]),
                            ("teacher_both",refq[1:],refv[1:],refprev[1:])):
        history=sensor(rep,full_state(sq,sv),sp)[window-1]
        predicted=actor(build_actor_obs_td({"motion":goal},history))
        error=((predicted-refa[k])*scale).cpu().numpy()
        result={}
        for name, sl in (("leg_rad",slice(0,12)),("wheel_rad_s",slice(12,16)),("arm_rad",slice(16,22)),("jaw_m",slice(22,23))):
            x=error[:,sl]
            result[name]=dict(rmse=float(np.sqrt(np.mean(x*x))),max_abs=float(np.max(np.abs(x))))
        if label=="measured_both":
            result["recomputed_vs_logged_clipped_max_abs"]=float((predicted-a[k]).abs().max())
        measurements[label]=result
    save(out,dict(source_trajectory=str(actual), reference=str(ref), checkpoint=str(args.checkpoint),
                  failed=r["first_failure"],frames=len(k),first_local_policy_index=10,
                  constant_inputs="same weights, fixed-reference absolute frame and measured current root for goal construction in all four interventions",
                  interpretation="one-step re-evaluation on measured failure; swapped permitted sensors create counterfactual inputs and are never used for scored task execution",
                  measurements=measurements))
    print(json.dumps(measurements,indent=2))


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("--result",type=Path,required=True)
    p.add_argument("--checkpoint",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--device",default="cpu")
    diagnose(p.parse_args())


if __name__=="__main__":
    main()
