"""Identify two fixed servo boundaries using registered measured prefixes and independent 20 ms branches."""
import argparse
from pathlib import Path
import mujoco
import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_model import contact_state
from learning.b0.contact_policy import build_actor
from learning.b0.contact_warp import ContactPlant
from learning.b0.model import tensor
from learning.b0.physics import ActionMap
from scripts.b0.dynamics_c20_pair import model_and_rep
from scripts.b0.dynamics_closedloop_entries import judge_for
from scripts.b0.dynamics_h32_score import restore_entry
from scripts.b0.dynamics_warp_windows import feed
from scripts.b0.joint_physics_audit import IDENTITIES, OLD, OUT, RAW, SIGMA, arrays, read, source, write
from scripts.b0.score_temporal_wm import csv_file
from scripts.b0.training_entry_response import phases

DEVICE="cuda:0"
REG=OUT/"boundary_registration.json"
POINTS=[("j2_outer",17,1),("j2_edge",17,0),("j2_inner",17,-1),
        ("jaw_outer",22,1),("jaw_edge",22,0),("jaw_inner",22,-1),("joint_inner",None,-1)]


def registered_actor(model, rep):
    bundle=torch.load(OLD/"h32"/"control"/"checkpoint_000000.pt",map_location="cpu",weights_only=False)
    shared=torch.load(OLD/"h32_shared"/"first.pt",map_location="cpu",weights_only=False)["actor"]
    assert set(shared)==set(bundle["actor"]) and all(torch.equal(v,bundle["actor"][k]) for k,v in shared.items())
    actor,_=build_actor(rep,bundle["cfg"],model,DEVICE)
    actor.load_state_dict(shared)
    return actor.eval()


@torch.no_grad()
def register():
    audit=read(OUT/"raw_audit.json")
    assert audit["branches"]==240
    plan=[]
    for identity,dt in IDENTITIES.items():
        model,rep=model_and_rep(dt)
        mapping=ActionMap(model)
        actor=registered_actor(model,rep)
        for side in ("pull","push"):
            for split in ("train","validation"):
                start=side+"_0_"+split+"_grip_hold"
                folder=source(identity)/start
                rec=read(folder/"receipt.json")
                with np.load(folder/"start.npz") as saved:
                    obs=build_actor_obs_td({"motion":tensor(saved["goal"],DEVICE)},tensor(saved["history"],DEVICE))
                    u=actor.raw(obs)[0].cpu().numpy().clip(-1,1)
                    np.testing.assert_allclose(u,saved["u0"].clip(-1,1),atol=1e-6,rtol=1e-6)
                    bias=saved["servo_bias" if dt<.002 else "qfrc_bias"]
                    limits={}
                    for ch in (17,22):
                        aid=mapping.actuator_ids[ch]
                        kp=model.actuator_gainprm[aid,0]
                        kv=-model.actuator_biasprm[aid,2]
                        t=(mapping.offset[ch]+mapping.scale[ch]*u[ch])
                        q=saved["qpos"][mapping.q[ch]]
                        v=saved["qvel"][mapping.dof[ch]]
                        bb=float(bias[mapping.dof[ch]])
                        fac=mapping.finger_factor[ch]
                        low,high=(q+(kv*v-bb+model.actuator_forcerange[aid])/kp)/fac
                        edges=sorted([(float(low),-1),(float(high),1)],key=lambda p:abs(p[0]-t))
                        legal=[(e,s) for e,s in edges if abs((e-mapping.offset[ch])/mapping.scale[ch])<=1]
                        limits[ch]=dict(lower=float(low),upper=float(high),command=t,
                            nearest_legal_edge=(legal[0][0] if legal else None),outward_sign=(legal[0][1] if legal else None),
                            sigma=SIGMA[ch],kp=float(kp),kv=float(kv),force_limit=float(model.actuator_forcerange[aid,1]))
                    pts=[]
                    for label,single,factor in POINTS:
                        applied=u.astype(float).copy()
                        targets={}
                        eligible=True
                        for ch in ((17,22) if single is None else (single,)):
                            lim=limits[ch]
                            if lim["nearest_legal_edge"] is None:
                                eligible=False
                                continue
                            target=lim["nearest_legal_edge"]+lim["outward_sign"]*factor*2*SIGMA[ch]
                            targets[ch]=target
                            applied[ch]=(target-mapping.offset[ch])/mapping.scale[ch]
                            eligible=eligible and abs(applied[ch])<=1
                        pts.append(dict(label=label,eligible=bool(eligible),targets=targets,
                            action=applied.tolist() if eligible else None))
                    plan.append(dict(id=start,identity=identity,dt=dt,side=side,split=split,source=str(folder),
                        row=rec["row"],offset=rec["offset"],frame=rec["frame"],u0=u.tolist(),boundaries=limits,points=pts))
    obj=dict(raw_first_decision=audit["coverage"],points=plan,repeat_orders=["registered","reversed"],
        rule="Physical commands are preregistered from measured post-prefix state and frozen shared-u0. Skip illegal targets. Only fine train/repeat0 unique finite complete intervals enter response H1; each branch is a standalone episode.",
        prefixes="Exact archived complete 200 ms solved reference prefixes with registered measured q/v, ctrl, previous bias, warmstart, timer and history are reused; zero new prefix steps.",
        steps_per_branch={"formal_2ms":10,"training":80},additional_train_open=False)
    if REG.exists():
        assert read(REG)==read_json_roundtrip(obj)
    else:
        write(REG,obj)


def read_json_roundtrip(obj):
    import json
    return json.loads(json.dumps(obj))


@torch.no_grad()
def run(identity, repeat):
    reg=read(REG)
    dt=IDENTITIES[identity]
    model,rep=model_and_rep(dt)
    mapping=ActionMap(model)
    plants={}
    rows=[]
    train=[]
    for entry in reg["points"]:
        if entry["identity"]!=identity:
            continue
        pts=[p for p in entry["points"] if p["eligible"]]
        if repeat:
            pts=pts[::-1]
        n=len(pts)
        if not n:
            continue
        if n not in plants:
            plants[n]=ContactPlant(model,n,DEVICE,preserve_continuous_bias=True)
        plant=plants[n]
        src=Path(entry["source"])
        row=entry["row"]|dict(id="joint_boundary__"+entry["id"])
        dst=RAW/"boundary"/identity/f"repeat{repeat}"/row["id"]
        dst.mkdir(parents=True,exist_ok=True)
        if (dst/"receipt.json").exists():
            prior=read(dst/"receipt.json")
            rows.extend(prior["results"])
            if identity=="training" and repeat==0 and row["split"]=="train":
                train.append(row)
            continue
        with np.load(src/"start.npz") as snap:
            restore_entry(plant,snap)
            q0=snap["qpos"]; v0=snap["qvel"]
            sides=torch.full((n,),int(row["side"]=="push"),device=DEVICE,dtype=torch.long)
            state0=contact_state(plant.data.qpos[:],plant.data.qvel[:]).cpu().numpy()
            applied=tensor(np.array([p["action"] for p in pts]),DEVICE)
            ix=entry["frame"]*10
            phase=phases(Path(row["path"]))[ix:ix+10]
            ev=plant.step_contact(applied,sides,torch.as_tensor(phase,device=DEVICE).expand(n,-1),record=True)
            state1=contact_state(plant.data.qpos[:],plant.data.qvel[:]).cpu().numpy()
            sub={k:v.cpu().numpy()[None] for k,v in ev["substeps"].items()}
            physical=applied.cpu().numpy()*mapping.scale+mapping.offset
            servo=arrays(model,mapping,snap,sub,physical,dt)
        np.savez_compressed(dst/"servo.npz",**servo)
        training_phase=phase.repeat(plant.clock.servo_stride)[None]
        np.savez_compressed(dst/"substeps.npz",**sub,training_phase=training_phase)
        valid=ev["valid_full_interval"].cpu().numpy()
        failure=ev["first_fail_substep"].cpu().numpy()
        np.savez_compressed(dst/"dynamics.npz",state=np.stack((state0,state1)),action=applied.cpu().numpy()[None],
            physical=physical,valid=valid[None],fail=failure[None])
        res=[]
        for i,p in enumerate(pts):
            judge=judge_for(model,read(src/"receipt.json"))
            record={k:x[0,i] for k,x in sub.items()}
            record.update(qpos=record["qpos_post"],qvel=record["qvel_post"],q0=q0,v0=v0)
            feed(judge,mujoco.MjData(model),record)
            signed={}
            measured={}
            for c in p["targets"]:
                ch=int(c)
                lim=entry["boundaries"][c]
                frac=1 if "edge" in p["label"] else (1.05 if "outer" in p["label"] else .95)
                target=frac*lim["outward_sign"]
                signed[c]=float(servo["unclipped_force"][i,0,ch-16])/lim["force_limit"]
                measured[c]=float(servo["measured_force"][i,0,ch-16])/lim["force_limit"]
                if abs(signed[c]-target)>2.e-5 or abs(measured[c]-np.clip(target,-1,1))>2.e-5:
                    raise ValueError(f"Wrong signed force crossing {row['id']} {p['label']}: {signed}, {measured}, {target}")
            res.append(dict(identity=identity,repeat=repeat,split=row["split"],start=entry["id"],side=row["side"],
                point=p["label"],lane=i,runtime_eligible_h1=bool(valid[i]),train_h1=bool(identity=="training" and not repeat and row["split"]=="train" and valid[i]),
                training_terminal_tick=int(failure[i]),failure=judge.failure,events=judge.events,
                judge_ticks=judge.step,net_door_first_N=float(np.linalg.norm(record["door_robot_force_N"][0])),
                raw_first_by_limit=signed,actual_first_by_limit=measured,
                j2_end_rad=float(state1[i,24]),j2_end_rad_s=float(state1[i,54]),jaw_end_m=float(state1[i,29]-state1[i,30]),
                raw=str(dst)))
        write(dst/"receipt.json",dict(row=row,labels=[["u0",p["label"],0,0.] for p in pts],results=res))
        rows.extend(res)
        if identity=="training" and repeat==0 and row["split"]=="train":
            train.append(row)
    write(OUT/f"boundary_{identity}_r{repeat}.json",dict(rows=rows,branches=len(rows),microsteps=round(.02/dt)*len(rows),
        new_prefix_physics_steps=0,source="Measured registered prefix snapshots reused",training_h1=sum(r["train_h1"] for r in rows)))
    if identity=="training" and repeat==0:
        write(OUT/"boundary_train_registration.json",dict(starts=train,raw=str(RAW/"boundary/training/repeat0"),
            physics_dt=dt,independent_branch_steps=1,h7=0))
    print(identity,repeat,len(rows),sum(r["train_h1"] for r in rows),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["register",*IDENTITIES])
    p.add_argument("--repeat",type=int,choices=[0,1],default=0)
    args=p.parse_args()
    register() if args.action=="register" else run(args.action,args.repeat)
