"""First-command calibration and interval reward for matched development entries."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import mujoco as mj
import numpy as np
import torch

from learning.b0.contact_model import contact_state
from learning.b0.contact_reward import reward_terms
from learning.b0.model import full_state, tensor
from scripts.b0.score_contact_return import MAX_RATE
from scripts.b0.score_temporal_wm import csv_file

OUT=Path("results/b0/standard_dynamics_20261124/h32")
ENTRY_IDS=[f"{s}_0_validation_grip_{p}" for s in ("pull","push") for p in ("grasp","hold","release")]


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()


def register():
    OUT.mkdir(parents=True,exist_ok=True)
    entries=json.loads(Path("results/b0/standard_temporal_20261124/registration.json").read_text())["starts"]
    assert {r["id"] for r in entries if r["split"]=="validation"}==set(ENTRY_IDS)
    reg=dict(kind="matched_development_first_command",entries=ENTRY_IDS,policy_seed=0,
             clocks=dict(formal_2ms=.002,training=.00025,external_servo=.002,actor=.02,real_prefix=.2),
             histories="For each physics identity all arms receive exactly the registered measured 10-frame history, previous command, reference observation, clock, post-prefix q/v and continuous solver cache.",
             arms=["shared_u0","control_u1","experiment_u1","control_u10","experiment_u10"],
             timing="Evaluate the Actor once after registration. Apply its complete clipped command during the first 20ms, then the previously stored 31 common reference actions for a diagnostic effect of that first action. Mark every physical step after original failure.",
             repeat="Two lanes per checkpoint/command per registered start. If a possible extension emerges, independently rerun fixed entries before extending.",
             metrics="Complete 20ms physical effort-coordinate reward and its signed components, separately first-failure-absorbed diagnostic reward. Common D/C/H-free registered development sources, per-microstep door force, finger loads, stage and observation/decision times.",
             reference_for_interval_reward="Use the same measured reference-frame key as the Actor goal; recorded 2ms grid. Only a fine early stop needs between-grid free-base/joint interpolation.",
             interpretation="First-command development evidence; no H32 imagination, training input, formal-ten denominator or whole-door bilateral return.")
    file=OUT/"same_state_registration.json"
    if file.exists():
        assert json.loads(file.read_text())==reg
    else:
        file.write_text(json.dumps(reg,indent=2)+"\n")


def state_at(model, folder, base_tick, at_s):
    exact=base_tick+at_s/.002
    lo=int(np.floor(exact+1.e-10))
    part=max(0.,exact-lo)
    qs=np.load(folder/"substeps/qpos.npy",mmap_mode="r")
    vs=np.load(folder/"substeps/qvel.npy",mmap_mode="r")
    q=qs[lo].astype(float,copy=True)
    v=vs[lo].astype(float,copy=True)
    if part>1.e-8:
        delta=np.empty(model.nv)
        mj.mj_differentiatePos(model,delta,1.,q,qs[lo+1].astype(float))
        mj.mj_integratePos(model,q,delta,part)
        v=(1-part)*v+part*vs[lo+1]
    return q,v


@torch.no_grad()
def interval_rewards(rep, model, meta, saved, q, v, act, durations):
    device=rep.reward_home.device
    pair=[state_at(model,Path(meta["row"]["reference"]),10*meta["goal_frame"],float(dt)) for dt in durations]
    ref_q=tensor(np.stack([p[0] for p in pair]),device)
    ref_v=tensor(np.stack([p[1] for p in pair]),device)
    rs=full_state(ref_q,ref_v)
    targets=rep.fk(ref_q[:,:3],ref_q[:,3:7],ref_q[:,7:31],rs[:,31:34],rs[:,34:37],ref_v[:,6:30])
    x=contact_state(tensor(q,device),tensor(v,device))
    prev=tensor(saved["previous"],device).expand(len(act),-1)
    terms=reward_terms(rep,rep.represent(x),x[:,:7],tensor(act,device),prev,targets,coordinates="fixed_effort",
                       previous_valid=True,dt=tensor(np.array(durations),device))
    values={k:v.cpu().numpy().astype(float) for k,v in terms.items()}
    scores=np.stack(list(values.values())).sum(0)
    return [dict(signed_sum=float(s),normalized_to_planned_20ms=float(s/(MAX_RATE*.02)),
                 terms={k:float(v[i]) for k,v in values.items()}) for i,s in enumerate(scores)]


def first_interval(folder, meta, saved, rep, model, dt):
    with np.load(folder/"substeps.npz") as sub, np.load(folder/"dynamics.npz") as dyn:
        n=sub["qpos_post"].shape[2]
        q,v,act=sub["qpos_post"][0],sub["qvel_post"][0],dyn["action"][0]
        ids=np.arange(len(q))
        receipt=json.loads((folder/"receipt.json").read_text())
        stop=np.array([min(n,(x["failure"] or {}).get("first_failure_substep",n)) for x in receipt["judges"]])
        first20=interval_rewards(rep,model,meta,saved,q[:,-1],v[:,-1],act,np.full(len(q),.02))
        accepted=interval_rewards(rep,model,meta,saved,q[ids,stop-1],v[ids,stop-1],act,dt*stop)
        force=np.linalg.norm(sub["door_robot_force_N"][0],axis=-1)
        loads=sub["finger_load_N"][0]
        cfg=.01
        records=[]
        for i in ids:
            idx=np.flatnonzero(force[i]>6.)
            both=(loads[i]>cfg).all(-1)
            before=both[:stop[i]]
            physical_first=dyn["fail"][0,i]
            trainstop=int(physical_first) if physical_first else n
            records.append(dict(full_20ms_effort_reward=first20[i]["signed_sum"],
                full_20ms_normalized=first20[i]["normalized_to_planned_20ms"],full_20ms_action_rate=first20[i]["terms"]["action_rate"],
                full_20ms_reward_components=first20[i]["terms"],original_judge_absorbed_20ms_reward=accepted[i]["signed_sum"],
                original_judge_absorbed_20ms_normalized=accepted[i]["normalized_to_planned_20ms"],
                original_judge_20ms_observed_s=float(stop[i]*dt),absorbed_20ms_s=float((n-stop[i])*dt),
                original_training_terminal_20ms_s=float(physical_first*dt) if physical_first else None,
                first20_peak_before_judge_stop_n=float(force[i,:stop[i]].max()),first20_oversix_sample_s=float(idx[0]*dt) if len(idx) else None,
                first20_oversix_observed_s=float((idx[0]+1)*dt) if len(idx) else None,first20_force_peak_sample_s=float(force[i].argmax()*dt),
                both_duration_first20ms_s=float(both.sum()*dt),both_duration_first20ms_before_stop_s=float(before.sum()*dt),
                both_initial_first20ms_before_stop_s=float((np.flatnonzero(~before)[0] if not before.all() else len(before))*dt),
                both_during_training_valid_prefix_s=float(both[:trainstop].sum()*dt),
                both_fingers_before_first20ms_stop=bool(before.any()),peak_each_finger_n=loads[i].max(0).tolist()))
        return records


def input_fields(saved):
    return {k:saved[k] for k in ("qpos","qvel","qacc_warmstart","qfrc_bias","servo_bias","ctrl","time",
        "sat_ticks","slip_ticks","load_ticks","lost_ticks","history","goal","clock","previous") if k in saved}


def controls_csv(rows, folder, mapping, identity, ckpaths, basis):
    with np.load(folder/"first_commands_and_inputs.npz") as data:
        results=[]
        for actor in [r for r in rows if r["repeat"]=="actor"]:
            label=actor["node"]
            for i,name in enumerate(mapping.names):
                results.append(dict(identity=identity,start=actor["start"],node=label,channel=i,joint=name,
                    canonical_raw=float(data[label+"_raw"][i]),canonical_applied=float(data[label+"_clipped"][i]),
                    mapped_physical=float(data[label+"_physical"][i]),physical_unit="opening_m" if i==22 else ("rad/s" if 12<=i<16 else "rad"),
                    actuator_target_before_bias=float(data[label+"_servo_target"][i]),checkpoint=str(ckpaths[label]),
                    archive_start=str(basis/"start.npz")))
        return results


def summarize_pair(identity, rows):
    reg=json.loads((OUT/"same_state_registration.json").read_text())
    assert {r["start"] for r in rows}<=set(reg["entries"])
    group={}
    for r in rows:
        group.setdefault((r["start"],r["node"]),[]).append(r)
    metrics=["first_door_force_n","first20_peak_before_judge_stop_n","peak_first_interval_n",
        "both_duration_first20ms_before_stop_s","before_stop_dual_longest_s","before_stop_t_s","events",
        "full_20ms_normalized","original_judge_absorbed_20ms_normalized","jaw_command_mm","j2_command_rad"]
    out=[]
    for start in sorted({k[0] for k in group}):
        u0=group[(start,"shared_u0")]
        for arm in ("control","experiment"):
            for u in (1,10):
                key=f"{arm}_u{u}"
                if (start,key) not in group:
                    continue
                entry=group[start,key]
                for anchor in ["shared_u0"]+(["control_u10"] if arm=="experiment" and u==10 and (start,"control_u10") in group else []):
                    base=group[start,anchor]
                    for m in metrics:
                        x=np.array([r[m] for r in entry])
                        y=np.array([r[m] for r in base])
                        lo=float(x.min()-y.max()); hi=float(x.max()-y.min())
                        out.append(dict(identity=identity,start=start,side=u0[0]["side"],phase=u0[0]["phase"],
                            node=key,baseline=anchor,measure=m,mean=float(x.mean()),repeat_range=float(np.ptp(x)),
                            baseline_mean=float(y.mean()),baseline_repeat_range=float(np.ptp(y)),delta_mean=float(x.mean()-y.mean()),
                            min_delta=lo,max_delta=hi,repeat_ranges_separated=lo>0 or hi<0))
    return out


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register",action="store_true",required=True)
    parser.parse_args()
    register()
