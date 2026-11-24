"""Recover solve-start servo evidence from the 240 registered first-action branches."""
import json
from pathlib import Path

import numpy as np
from learning.b0.physics import ActionMap, make_model
from scripts.b0.score_temporal_wm import csv_file

OLD = Path("results/raw_large/b0/dynamics_20261124")
OUT = Path("results/b0/standard_joint_contact_20261124/physics")
RAW = Path("results/raw_large/b0/joint_contact_20261124/physics")
IDENTITIES = {"formal_2ms":.002,"training":.00025}
CHANNEL = np.arange(16,23)
SIGMA = {17:.0025,22:.001/3}


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")


def source(identity):
    return OLD/"response" if identity=="training" else Path("results/raw_large/b0/temporal_entries_v1")


def arrays(model, mapping, saved, sub, target, dt):
    ids=mapping.actuator_ids[CHANNEL]
    # All seven transmissions are unit-gear joints, so lengths and speeds equal mapped q and v.
    assert np.all(model.actuator_gear[ids]==np.array([1,0,0,0,0,0])) and np.all(model.actuator_trntype[ids]==0)
    q1,v1=sub["qpos_post"][0],sub["qvel_post"][0]
    count,n=q1.shape[:2]
    assert n==round(.02/dt)
    q=np.concatenate((np.broadcast_to(saved["qpos"],(count,1,model.nq)),q1[:,:-1]),axis=1)
    v=np.concatenate((np.broadcast_to(saved["qvel"],(count,1,model.nv)),v1[:,:-1]),axis=1)
    length,vel=q[:,:,mapping.q[CHANNEL]],v[:,:,mapping.dof[CHANNEL]]
    ctrl=sub["ctrl"][0][:,:,ids].astype(float)
    force=sub["actuator_force"][0][:,:,ids]
    limited=np.where(model.actuator_ctrllimited[ids],np.clip(ctrl,*model.actuator_ctrlrange[ids].T),ctrl)
    gain=model.actuator_gainprm[ids,0]
    biasprm=model.actuator_biasprm[ids,:3]
    raw=gain*limited + biasprm[:,0]+biasprm[:,1]*length+biasprm[:,2]*vel
    lo,hi=model.actuator_forcerange[ids].T
    clipped=raw.clip(lo,hi)
    error=np.abs(clipped-force)
    if error.max()>.00015:
        raise ValueError(f"Solve-start force mismatch {error.max()}")
    target=np.asarray(target)[:,CHANNEL]*mapping.finger_factor[CHANNEL]
    # Only the initial cache is directly archived. Subsequent caches recover from actual held ctrl.
    regkey="servo_bias" if dt<.002 else "qfrc_bias"
    cache=(ctrl-target[:,None])*gain
    cache0=saved[regkey][mapping.dof[CHANNEL]]
    if np.max(np.abs(cache[:,0]-cache0))>.0001:
        raise ValueError("First solve ctrl and archived external bias disagree")
    stride=round(.002/dt)
    if not np.array_equal(ctrl,ctrl[:,::stride].repeat(stride,axis=1)):
        raise ValueError("Physical ctrl changed during an external servo tick")
    cache[:,0:stride]=cache0
    lower=((lo-biasprm[:,0]-biasprm[:,1]*length-biasprm[:,2]*vel-cache)/gain)/mapping.finger_factor[CHANNEL]
    upper=((hi-biasprm[:,0]-biasprm[:,1]*length-biasprm[:,2]*vel-cache)/gain)/mapping.finger_factor[CHANNEL]
    return dict(q_before=q,v_before=v,actuator_length=length,actuator_velocity=vel,ctrl=ctrl,limited_ctrl=limited,
        external_cached_bias=cache,unclipped_force=raw,computed_clipped_force=clipped,measured_force=force,
        force_abs_error=error,saturated=(raw<=lo)|(raw>=hi),lower_physical_target=lower,
        upper_physical_target=upper,actual_jaw_opening=q[:,:,29]-q[:,:,30])


def inspect():
    model=make_model()
    mapping=ActionMap(model)
    rows=[]
    for identity,dt in IDENTITIES.items():
        for repeat in ("","_independent_repeat"):
            base=OLD/"h32"/"same_state"/(identity+repeat)
            for p in sorted(base.iterdir()):
                meta=read(p/"receipt.json")
                with np.load(p/"first_commands_and_inputs.npz") as saved,np.load(p/"substeps.npz") as sub:
                    targets=[saved[tag+"_physical"] for tag,*_ in meta["labels"]]
                    data=arrays(model,mapping,saved,sub,targets,dt)
                rawfile=RAW/"archived_first"/base.name/(p.name+".npz")
                rawfile.parent.mkdir(parents=True,exist_ok=True)
                np.savez_compressed(rawfile,**data)
                for i,(tag,role,*_) in enumerate(meta["labels"]):
                    for channel,sigma in SIGMA.items():
                        k=channel-16
                        t=float(targets[i][channel])
                        lower=float(data["lower_physical_target"][i,0,k])
                        upper=float(data["upper_physical_target"][i,0,k])
                        dist=max(lower-t,t-upper,0.)
                        rows.append(dict(identity=identity,start=p.name,side=meta["row"]["side"],phase=meta["row"]["phase"],
                            run_repeat=int(bool(repeat)),role=role,node=tag,channel=channel,
                            physical_command=t,first_lower=lower,first_upper=upper,first_distance=dist,
                            first_distance_sigma=dist/sigma,first_raw_force=float(data["unclipped_force"][i,0,k]),
                            first_actual_force=float(data["measured_force"][i,0,k]),
                            saturated_ticks=int(data["saturated"][i,:,k].sum()),ticks=data["ctrl"].shape[1],
                            max_all_seven_force_error=float(data["force_abs_error"][i].max()),raw=str(rawfile),source=str(p)))
    OUT.mkdir(exist_ok=True,parents=True)
    assert len(rows)==480
    csv_file(OUT/"archived_servo_rows.csv",rows)
    hold=[r for r in rows if r["phase"]=="hold" and r["role"]=="actor" and r["run_repeat"]==0]
    write(OUT/"raw_audit.json",dict(branches=240,raw_solve_ticks=sum(r["ticks"] for r in rows if r["channel"]==17),
        channels=mapping.names[16:23],first20_includes_first_solve=True,
        cache="First external tick reads archived servo_bias (fine) or qfrc_bias (2ms); later ticks inferred from saved held ctrl and the archived target, separately from the force validation.",
        transmission="Unit-gear direct joints. Matched actual actuator force uses solve-start q/v, actual ctrl with engine ctrlrange, gain/bias and forcerange.",
        max_abs_force_error=max(r["max_all_seven_force_error"] for r in rows),hold=hold,
        coverage="240 records are validation only, with five learned commands. No registered seven-point boundary designs exist for both train and validation on both identities."))
    print("240 archived first actions",max(r["max_all_seven_force_error"] for r in rows))
    for r in hold:
        if r["identity"]=="training" and r["node"] in ("shared_u0","experiment_u10"):
            print(r["side"],r["node"],r["channel"],r["first_distance_sigma"],r["saturated_ticks"],r["ticks"])


if __name__=="__main__":
    inspect()
