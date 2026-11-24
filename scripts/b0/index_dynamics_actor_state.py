"""Read actual Actor samples and frozen state changes, without composing or fitting any policies."""
from pathlib import Path

import numpy as np
import torch
from learning.b0.contact_model import ContactRepresentation
from learning.b0.contact_policy import build_actor
from learning.b0.contact_warp import PHASES, PHASE_ID
from learning.b0.physics import make_model
from scripts.b0.dynamics_h32_pilot import ARMS, OUT, RAW, REG, read, resolved, write


def compare_models(a,b,parameters):
    param={}
    buffers={}
    for name,x in a.items():
        delta=(b[name].double()-x.double())
        row=dict(changed=int(torch.count_nonzero(delta)),elements=x.numel(),l2=float(delta.norm()),
            max_abs=float(delta.abs().max()),initial_l2=float(x.double().norm()))
        if name.endswith(".count"):
            row.update(before=float(x),after=float(b[name]))
        (param if name in parameters else buffers)[name]=row
    return dict(parameter_total=dict(tensors=len(param),elements=sum(x["elements"] for x in param.values()),
        changed=sum(x["changed"] for x in param.values()),changed_tensors=sum(bool(x["changed"]) for x in param.values()),
        change_l2=sum(x["l2"]**2 for x in param.values())**.5,max_abs=max(x["max_abs"] for x in param.values())),
        normalization={k:v for k,v in buffers.items() if "normalizer" in k},
        other_buffers={k:v for k,v in buffers.items() if "normalizer" not in k})


def actual_draws(raw,out):
    full=torch.load(raw/"cohort_state.pt",map_location="cpu",weights_only=False)
    chunks=full["replay"]
    if len(chunks)!=full["ratio_state"]["cohorts"] or len(chunks)>=full["cfg"]["replay_cohorts"]:
        raise ValueError("Cannot match initial draw indices after replay eviction")
    saved=np.load(raw/"u1_true_actor_batch.npz")
    report={}
    for u in range(1,11):
        with np.load(out/f"draws_u{u:02}.npz") as logged:
            picks=logged["actor_online"]
        arrays={}
        for k in ("motion_time","episode","sim_ctx","draw_phase","draw_mode","terminated"):
            data=np.stack([chunks[c][0][k][lane,t].numpy() for c,lane,t in picks])
            arrays[k]=data
            if u==1:
                np.testing.assert_array_equal(data,saved[k],err_msg=k)
        per_side={}
        for k,side in enumerate(("pull","push")):
            m=arrays["sim_ctx"][:,0]==k
            phase=arrays["draw_phase"]
            oh=m & np.isin(phase,(PHASE_ID["open"],PHASE_ID["hold"]))
            terminal=arrays["terminated"]
            per_side[side]=dict(samples=int(m.sum()),distinct_episodes=int(len(np.unique(arrays["episode"][m]))),
                open_hold=int(oh.sum()),open_hold_terminal=int((oh&terminal).sum()),
                open_hold_two_finger=int((oh & (arrays["draw_mode"]==2)).sum()),
                terminal=int((m&terminal).sum()),
                phases={PHASES[int(p)]:int((m & (phase==p)).sum()) for p in np.unique(phase[m])})
        report[u]=per_side
    return report


@torch.no_grad()
def main():
    cfg=resolved(read(REG)["config"])
    source=cfg["wm_data_recipe"]["sources"]["response"]
    history=[]; goal=[]; ids=[]
    for row in read(source["registration"])["starts"]:
        f=Path(source["raw"])/row["id"]
        if row["split"]=="validation" and not read(f/"receipt.json").get("rejected"):
            with np.load(f/"start.npz") as z:
                history.append(torch.tensor(z["history"]))
                goal.append(torch.tensor(z["goal"]))
                ids.append(row["id"])
    hs=torch.cat(history); gs=torch.cat(goal)
    model=make_model(); model.opt.timestep=cfg["physics_dt"]
    rep=ContactRepresentation(model,"cpu")
    actor,_=build_actor(rep,cfg,model,"cpu")
    actor.eval()
    parameters=set(dict(actor.named_parameters()))
    arms={}
    for arm in ARMS:
        raw=RAW/"h32"/arm; out=OUT/"h32"/arm
        states={n:torch.load(raw/f"checkpoint_{n:06}.pt",map_location="cpu",weights_only=False)["actor"] for n in (0,1,10)}
        norm={}
        for n,state in states.items():
            actor.load_state_dict(state,strict=True)
            norm[n]=(actor.obs_normalizer(hs),actor.goal_normalizers["motion"](gs))
        delta={}
        for key,lo,hi in (("u0_to_u1",0,1),("u1_to_u10",1,10),("u0_to_u10",0,10)):
            delta[key]=compare_models(states[lo],states[hi],parameters)
            z={}
            for idx,name in enumerate(("history","goal")):
                x=(norm[hi][idx]-norm[lo][idx]).abs().numpy()
                z[name]=dict(p95=float(np.percentile(x,95)),max=float(x.max()))
            delta[key]["fixed_validation_input_absolute_z_change"]=z
        arms[arm]=dict(checkpoint_changes=delta,real_actor_starts=actual_draws(raw,out))
    write(OUT/"h32"/"actor_state_and_starts.json",dict(arms=arms,validation_history_ids=ids,
        inputs="Recorded fine-solver validation histories and goals; each checkpoint evaluated only as saved",
        attribution="At u1 the shared collection left these normalizers fixed; later actual Actor parameters and normalization both change",
        selections="Actual ordered memoized replay positions at each H32, cross-checked with full recorded u1 batch",
        additional_forward_H32=0,additional_training_steps=0))


if __name__=="__main__":
    main()
