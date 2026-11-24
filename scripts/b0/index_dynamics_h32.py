"""Index the completed development pilot without promoting a model or opening held-out cases."""
import csv
from pathlib import Path
import numpy as np
from scripts.b0.dynamics_h32_pilot import ARMS, OUT, RAW, REG, SHARED, read, write


def main():
    root=OUT/"h32"
    raw=RAW/"h32"
    with np.load(raw/"control/u1_true_actor_batch.npz") as a,np.load(raw/"experiment/u1_true_actor_batch.npz") as b:
        invariant=("episode","motion_time","state","history","prev_action","sim_ctx","first_command","draw_mode","draw_phase","terminated")
        matches={k:bool(np.array_equal(a[k],b[k])) for k in invariant}
        size,shape=len(a["episode"]),list(a["state"].shape)
    with np.load(root/"control/draws_u01.npz") as x,np.load(root/"experiment/draws_u01.npz") as y:
        n_groups=len(x.files)
        equal=x.files==y.files and all(np.array_equal(x[k],y[k]) for k in x.files)
    if not equal or not all(matches.values()):
        raise ValueError("Actual u1 pairing mismatch")
    write(root/"actual_u1_pair.json",dict(identical_first_training_draw_groups=n_groups,
        ordered_wm_and_actor_indices=equal,actual_actor_inputs=matches,
        first_command_source="actual rollout after each arm's 10 WM, before first actor/critic optimizers",
        underlying_rows=size,state_shape=shape,requested_reg="0/1/10 development H32",independent_after="first H32 update"))
    shared=read(OUT/"shared_collection.json")
    with np.load(SHARED/"lanes_000001.npz") as x:
        shared_prefix=int(x["prefix"].sum())
    branches={}
    for arm in ARMS:
        folder=root/arm
        branch=branches[arm]=dict(training=read(folder/"outcome.json"),recovery=read(folder/"recovery.json"))
        online=read(folder/"online_physics.json")
        branch["physical_intervals"]={k:online[k] for k in ("complete_valid","simulated","prefix_intervals","prefix_rejected","post_failure_substeps")}
        branch["by_side"]={}
        for side in ("pull","push"):
            z=[r for r in online["groups"] if r["side"]==side]
            oh=[r for r in z if r["phase"] in ("open","hold")]
            branch["by_side"][side]=dict(valid=sum(r["count"] for r in z),open_or_hold=sum(r["count"] for r in oh),
                entire_dual=sum(r["complete_two_finger"] for r in z),open_or_hold_entire_dual=sum(r["complete_two_finger"] for r in oh))
        branch["u1"]={}
        for name in ("preflight","u1_after_wm_objective"):
            d=read(folder/(name+".json"))
            branch["u1"][name]=dict(objective_mean=d["objective_mean"],actor_preclip_grad_l2=d["actor_preclip_grad_l2"],
                unchanged_rng=d["training_rng_unchanged"],unchanged_params_and_buffers=d["actor_critic_rep_wm_state_unchanged"],
                finite=d["finite"],raw=d["raw"])
        branch["u1"]["real_contribution_after_joint_wm"]=read(folder/"gradient_u1.json")["return_mean"]
        branch["formal"]={}
        branch["h32_two_finger_tcp_p95_mm"]={}
        for u in (0,1,10):
            tag="shared_u0" if u==0 else f"{arm}_u{u}"
            formal=read(root/f"{tag}_formal.json")
            branch["formal"][u]={k:formal[k] for k in ("cases","passed","events","at_first_2ms_overforce")}
            with (root/f"validation_{arm}_u{u}.csv").open() as f:
                ds=[r for r in csv.DictReader(f) if (r["h"],r["mode"],r["metric"])==("32","two_finger","tcp_mm")]
            branch["h32_two_finger_tcp_p95_mm"][u]={r["source"]+"_"+r["side"]:dict(P95=float(r["p95"]) if r["p95"] else None,
                scored=int(r["scored"]),nonfinite=int(r["nonfinite"])) for r in ds}
    totals={k:sum(row["training"][k] for row in branches.values()) for k in ("H32","WM","Critic")}
    totals.update(unique_formal_cases=50,unique_simulated=sum(x["training"]["simulated"] for x in branches.values())-shared["simulated"],
        unique_valid=sum(x["training"]["valid"] for x in branches.values())-shared["collected"],
        unique_prefix_intervals=sum(x["physical_intervals"]["prefix_intervals"] for x in branches.values())-shared_prefix)
    if (totals["H32"],totals["WM"],totals["Critic"])!=(20,200,400):
        raise ValueError("Incomplete or duplicated updates")
    counts=[read(root/f"{k}_formal.json") for k in ("shared_u0",*[f"{a}_u{u}" for a in ARMS for u in (1,10)])]
    if sum(r["cases"] for r in counts)!=50:
        raise ValueError("Incomplete original formal cases")
    totals.update(unique_formal_passes=sum(r["passed"] for r in counts),unique_formal_events=sum(r["events"] for r in counts))
    write(root/"pilot_summary.json",dict(experiment_kind="development_h32_pilot",seed=0,locked=read(REG)["pilot_wm"],
        formal_u0="One shared fresh 10-case protocol evaluation, exact Actor and normalization match",
        historical_response_u200_accounted=False,previous_selected_wm=None,total=totals,branches=branches,
        source_losses=str(root/"matched_joint_source_losses.csv"),shared_replay=shared["shared_state"],
        initial_control_state=shared["warp_data"],actual_first_batch=str(root/"actual_u1_pair.json"),
        training_dt=.00025,formal_dt=.002,policy_dt=.02))


if __name__=="__main__":
    main()
