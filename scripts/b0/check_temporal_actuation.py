"""Verify physical sign/units and count registered response draws for four hold starts."""
import argparse
import csv
import json
import sys
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from learning.b0.physics import ActionMap, make_model

OUT=Path("results/b0/standard_temporal_20261124")
RAW=Path("results/raw_large/b0/temporal_entries_v1")


def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=1,allow_nan=False)+"\n")


def model_fields(m, mapping, fields):
    actuators=mapping.actuator_ids[[17,22]]
    joints=np.array([m.joint(n).id for n in ("piper_joint2","piper_gripper_joint1","piper_gripper_joint2")])
    eq=m.equality("piper_finger_symmetry").id
    out={}
    for k,inds in {
        "actuator_gainprm":actuators,"actuator_biasprm":actuators,"actuator_gear":actuators,
        "actuator_trnid":actuators,"actuator_forcerange":actuators,"actuator_forcelimited":actuators,
        "actuator_ctrllimited":actuators,"jnt_range":joints,"jnt_axis":joints,"jnt_limited":joints,
        "eq_obj1id":eq,"eq_obj2id":eq,"eq_data":eq,"eq_solref":eq,"eq_solimp":eq,"eq_type":eq
    }.items():
        array=getattr(fields,k)
        if hasattr(array,"numpy"):
            array=array.numpy()
            if array.ndim>getattr(m,k).ndim:
                array=array[0]
        out[k]=array[inds].tolist()
    return out


def model_receipt(tag):
    result={"version":mujoco.__version__}
    for side in ("mobile","push"):
        m=make_model(side)
        a=ActionMap(m)
        values=model_fields(m,a,m)
        result[side]=dict(named_joint_ids={n:int(m.joint(n).id) for n in
                           ("piper_joint2","piper_gripper_joint1","piper_gripper_joint2")},
                           powered_joints=[m.joint(int(j)).name for j in m.actuator_trnid[:,0]],
                           target_offset=a.offset[[17,22]].tolist(),target_scale=a.scale[[17,22]].tolist(),
                           position_factor=a.finger_factor[[17,22]].tolist(),bias_gain=a.bias_gain[[17,22]].tolist(),
                           native=values)
        if tag=="research":
            import mujoco_warp as mjw
            warp_values=model_fields(m,a,mjw.put_model(m))
            diff={k:float(np.max(np.abs(np.asarray(v,dtype=float)-warp_values[k]))) for k,v in values.items()}
            result[side].update(warp=warp_values,warp_native_max_error=diff)
    write("actuation_model_"+tag+".json",result)


def actual_draws(ends,source,batches,starts,group,h,age_zero):
    if group is None:
        return 0
    lo=ends[group-1] if group else 0
    chosen=(source[:batches]==3)&(starts[:batches]>=lo)&(starts[:batches]<ends[group]-h)
    if age_zero:
        chosen &= starts[:batches]==lo
    chosen &= ((np.arange(batches)%10<2) if h==1 else (np.arange(batches)%10>=2))[:,None]
    return int(chosen.sum())


def audit():
    registry=json.loads((OUT/"paired_sources.json").read_text())
    assert registry["names"][3]=="response"
    episodes=registry["inventory"]["response"]
    group_indices={r["group"]:i for i,r in enumerate(episodes)}
    ends=np.cumsum([e["n"] for e in episodes])
    src=np.load(OUT/"paired_indices.npz")
    m=make_model()
    a=ActionMap(m)
    ix=np.array([17,22])
    actuators=a.actuator_ids[ix]
    qids=a.q[ix]
    vids=a.dof[ix]
    cutoff=m.actuator_forcerange[actuators,1]
    kp=m.actuator_gainprm[actuators,0]
    kd=-m.actuator_biasprm[actuators,2]
    last={arm:json.loads((OUT/(arm+"_training.jsonl")).read_text().splitlines()[-1])["k"] for arm in ("C20","T2")}
    node=min(last.values())
    nodes=[x for x in (50,200,1000) if x<=node]
    output=[]
    pool_samples=[]
    for rec in json.loads((OUT/"collection.json").read_text())["entries"]:
        row=rec["row"]
        if row["phase"]!="hold":
            continue
        folder=RAW/row["id"]
        d=np.load(folder/"dynamics.npz")
        sub=np.load(folder/"substeps.npz")
        start=np.load(folder/"start.npz")
        with sub:
            Q=sub["qpos_post"][0]
            V=sub["qvel_post"][0]
            CTRL=sub["ctrl"][0][:,:,actuators]
            F=sub["actuator_force"][0][:,:,actuators]
            train_phase=sub["training_phase"][0].tolist()
        for b,label in enumerate(rec["labels"]):
            group=group_indices.get(f"{row['id']}/b{b}")
            n=int(d["valid"][:,b].sum())
            assert n and (group is not None)==(label[1]!="repeat" and row["split"]=="train")
            if group is not None:
                assert episodes[group]["n"]==n+1
            for h in (1,7):
                item=dict(start=row["id"],split=row["split"],actor=label[0],intervention=label[1],
                          changed_channel=label[2],requested_delta=label[3],branch=b,h=h,
                          physical_legal_windows=max(n-h+1,0),training_eligible=group is not None and n>=h,
                          training_stop_tick=int(d["fail"][0,b]),event_stop_tick=(rec["judges"][b]["failure"] or {}).get("first_failure_substep"))
                for k in nodes:
                    item[f"age0_draws_at_{k}"]=actual_draws(ends,src["source"],k,src["start"],group,h,True)
                    item[f"any_age_draws_at_{k}"]=actual_draws(ends,src["source"],k,src["start"],group,h,False)
                pool_samples.append(item)
            if label[1] not in ("actor","ref_arm","ref_jaw","ref_arm_jaw","reference"):
                continue
            raw=d["action"][0,b,ix]
            physical=a.offset[ix]+a.scale[ix]*raw
            target=physical*a.finger_factor[ix]
            qpre=np.vstack([start["qpos"],Q[b,:-1]])[:,qids]
            vpre=np.vstack([start["qvel"],V[b,:-1]])[:,vids]
            expected_first=target+start["qfrc_bias"][vids]*a.bias_gain[ix]
            predicted=np.clip(kp*(CTRL[b]-qpre)-kd*vpre,-cutoff,cutoff)
            fields=dict(start=row["id"],split=row["split"],actor=label[0],command=label[1],branch=b,
                        unnormalized_target_j2_rad_total_opening_m=physical.tolist(),ctrl0_j2_and_finger1=CTRL[b,0].tolist(),
                        target_finger1_m=float(target[1]),max_first_ctrl_residual=np.abs(expected_first-CTRL[b,0]).tolist(),
                        servo_residual_max=np.abs(predicted-F[b]).max(0).tolist(),clip98pct_ticks=(np.abs(F[b])>=.98*cutoff).sum(0).tolist(),
                        force_min=F[b].min(0).tolist(),force_max=F[b].max(0).tolist(),ctrl_min=CTRL[b].min(0).tolist(),ctrl_max=CTRL[b].max(0).tolist(),
                        q1_q2_j2_min=Q[b][:,[29,30,24]].min(0).tolist(),q1_q2_j2_max=Q[b][:,[29,30,24]].max(0).tolist(),
                        v1_v2_j2_min=V[b][:,[28,29,23]].min(0).tolist(),v1_v2_j2_max=V[b][:,[28,29,23]].max(0).tolist(),
                        v1_v2_j2_peak=abs(V[b][:,[28,29,23]]).max(0).tolist(),
                        max_joint_range_violation_m=np.maximum(np.maximum(-Q[b,:,29],Q[b,:,29]-.05),np.maximum(Q[b,:,30],-Q[b,:,30]-.05)).clip(min=0).max().item(),
                        measured_peak_abs_q1_plus_q2_mm=float(1000*np.abs(Q[b,:,29]+Q[b,:,30]).max()),
                        realized_20ms_opening_mm=float((Q[b,-1,29]-Q[b,-1,30])*1000),
                        training_phase_substeps=train_phase,first_physical_failure_tick=int(d["fail"][0,b]),
                        event_failure=rec["judges"][b]["failure"])
            output.append(fields)
    with (OUT/"hold_actual_draws.csv").open("w") as handle:
        writer=csv.DictWriter(handle,pool_samples[0],lineterminator="\n")
        writer.writeheader();writer.writerows(pool_samples)
    native=json.loads((OUT/"actuation_model_native33.json").read_text())
    research=json.loads((OUT/"actuation_model_research.json").read_text())
    diff={s:{k:float(np.max(np.abs(np.asarray(v,dtype=float)-research[s]["native"][k])))
             for k,v in native[s]["native"].items()} for s in ("mobile","push")}
    write("hold_actuation_audit.json",dict(completed_for_both=nodes,receipt_updates_at_read=last,
         index_source="paired_indices.npz/paired_sources.json; count only the shared nodes completed by both arms",
         axes="Non-finger arrays [J2 rad, finger1 m]; force [Nm,N]. Triple rows [finger1 m, finger2 m, J2 rad] or their speeds. Physical command channel 22 is TOTAL opening m.",
         replay="Each saved 2 ms actuator force replayed using preceding qpos and qvel, original gain/bias and force limits; first ctrl uses restored prior-solve bias",
         native33_and_research_model_max_error=diff,rows=output))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("native33","research","audit"))
    args=parser.parse_args()
    if args.mode=="audit":
        audit()
    else:
        model_receipt(args.mode)
