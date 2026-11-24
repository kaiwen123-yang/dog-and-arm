"""Registered frozen Actor first actions after a measured training-style RSI prefix."""
import argparse
import json
import time
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
import torch
import warp as wp
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from learning.b0.contact_model import ContactRepresentation, contact_state
from learning.b0.contact_policy import DoorMotions, build_actor, sensor
from learning.b0.contact_warp import ContactPlant, PHASES, PHASE_ID
from learning.b0.model import RobotRepresentation, full_state, tensor
from learning.b0.physics import ActionMap, make_model, settings
from scripts.b0.register_contact_dev import SEGMENTS

OUT = Path("results/b0/standard_response_20261124")
RAW = Path("results/raw_large/b0/response_entries_v1")
BASE = Path("results/b0")
U0 = BASE/"lanes_s0_v1/checkpoint_000000.pt"
U200 = BASE/"lanes_s0_to200_v1/checkpoint_000200.pt"
DEVICE = "cuda:0"


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")


def arr(path, name):
    return np.load(path/(name+".npy"), mmap_mode="r")


def phases(path):
    names = json.loads((path/"metadata.json").read_text())["phases"]
    return np.array([PHASE_ID[name] for name in names])[arr(path, "substeps/phase")]


def entry(path, phase):
    labels = phases(path)
    if phase == "grasp":
        force = arr(path, "substeps/finger_load_N")
        touched = np.flatnonzero((labels == PHASE_ID[phase]) & (force > .01).any(1))
        if len(touched):
            return max(11, int(touched[0])//10-1)
    return int(np.flatnonzero(labels == PHASE_ID[phase])[0])//10


def register(cfg):
    root = Path(cfg["reference_directory"])
    rows = []
    for side in ("pull", "push"):
        for name, split in [(f"{side}_0_train_grip", "train"), (f"{side}_5_train", "train"),
                            (f"{side}_0_validation_grip", "validation")]:
            path = root/name
            goal = root/name.replace("validation", "train")
            assert goal.name in cfg["references"] and json.loads((path/"metadata.json").read_text())["wm_split"] == split
            for phase in ("grasp", "hold" if "grip" in name else "open", "release"):
                segment = {"hold":"stable_grip","open":"open_5","grasp":"approach_grasp","release":"release_retreat"}[phase]
                proto = "hold_margin_v2" if phase == "open" or (phase == "hold" and side == "push") else "v1"
                formal_dir = BASE/f"lanes_s0_v1_u0_warp_{proto}"
                plan = json.loads((formal_dir/"run_spec.json").read_text())["plan"]
                case = json.loads((formal_dir/side/segment/"nominal/result.json").read_text())
                rows.append(dict(id=name+"_"+phase, split=split, side=side, phase=phase, path=str(path),
                    reference=str(goal), frame=entry(path,phase), goal_frame=entry(goal,phase), seed=93000+len(rows),
                    alternative_offsets=[0, 12, 18], segment=segment, formal_spec=str(formal_dir/"run_spec.json"),
                    formal_ref=str(Path(plan["source"])/case["episode"]), formal_start=case["start_substep"]))
    return rows


def branches(raws, reference, scale):
    labels, commands = [], []
    for name, raw in raws.items():
        center = raw.clamp(-1,1)
        for arm, jaw, label in [(False,False,"actor"),(False,True,"ref_jaw"),(True,False,"ref_arm"),
                                (True,True,"ref_arm_jaw"),(False,False,"repeat")]:
            cmd = center.clone()
            if arm:
                cmd[16:22] = reference[16:22]
            if jaw:
                cmd[22] = reference[22]
            labels.append([name,label,0,0.])
            commands.append(cmd)
        for channel, unit in [(17,.001),(22,.00025)]:
            for factor in ([1,-1,10,-10] if channel==17 else [1,-1,4,-4]):
                cmd = center.clone()
                cmd[channel] = (cmd[channel]+unit*factor/scale[channel]).clamp(-1,1)
                commands.append(cmd)
                labels.append([name,"delta",channel,unit*factor])
    for tag in ("reference","repeat"):
        commands.append(reference)
        labels.append(["reference",tag,0,0.])
    return labels, torch.stack(commands)


def register_solver(plant, lane=0):
    fields = {name:wp.to_torch(getattr(plant.sim.wp_data,name)) for name in
              ("qpos","qvel","qacc_warmstart","ctrl","time","act") if name!="act" or plant.model.na}
    fields.update({name:getattr(plant,name) for name in ("load_ticks","lost_ticks","slip_ticks","sat_ticks")})
    for value in fields.values():
        value.copy_(value[lane:lane+1].clone().expand_as(value))
    if plant.preserve_continuous_bias:
        bias = wp.to_torch(plant.sim.wp_data.qfrc_bias)
        previous_bias = bias[lane].clone()
    plant.sim.forward()
    if plant.preserve_continuous_bias:
        bias.copy_(previous_bias.expand_as(bias))
        fields["qfrc_bias"] = bias
    return {name:value[lane].cpu().numpy().copy() for name,value in fields.items()}


def judge_trace(model,row,initial_q,initial_v,records):
    """Feed solved Warp measurements to the unchanged event state machine."""
    side = row["side"]
    cfg = settings("push" if side=="push" else "mobile",1)
    ref = FrozenDoorReference.from_episode(row["formal_ref"],model)
    event_phases = SEGMENTS[row["segment"]][1]
    base = row["formal_start"]
    end = ref.phase_bounds[event_phases[-1]][1]
    judges = [ContactEvents(model,cfg,side,ref,phases=event_phases,hold_seconds=3.,
        start_step=base,score_until_step=end-base) for _ in range(records["qpos_post"].shape[1])]
    event = np.full(records["qpos_post"].shape[:3],-1,dtype=np.int8)
    data = mujoco.MjData(model)
    for j in range(len(event)):
        for b,judge in enumerate(judges):
            for k in range(10):
                if judge.failure or judge.passed:
                    break
                event[j,b,k] = PHASE_ID[judge.phase]
                q0 = initial_q if j==k==0 else records["qpos_post"][j if k else j-1,b,k-1]
                v0 = initial_v if j==k==0 else records["qvel_post"][j if k else j-1,b,k-1]
                data.qpos[:] = q0
                mujoco.mj_kinematics(model,data)
                data.qpos[:] = records["qpos_post"][j,b,k]
                data.qvel[:] = records["qvel_post"][j,b,k]
                data.actuator_force[:] = records["actuator_force"][j,b,k]
                finger = records["finger_load_N"][j,b,k]
                wheel = records["wheel_load_N"][j,b,k]
                slip = records["wheel_slip_m_s"][j,b,k]
                contact = SimpleNamespace(finger_normal=finger,normal=wheel,both=bool((finger>cfg["contact_threshold_n"]).all()),
                    supported=wheel>=cfg["wheel_threshold_n"],door_force=records["door_robot_force_N"][j,b,k],
                    force_norm_sum=records["door_force_norm_sum_N"][j,b,k],slip_long=np.atleast_1d(slip),
                    slip_lat=np.zeros(1),unexpected=["unregistered_pair"] if records["unexpected_contact_N"][j,b,k]>cfg["contact_threshold_n"] else [])
                judge.observe(data,contact,q0,v0)
    return event,[dict(failure=j.failure,events=j.events) for j in judges]


def integrate_branches(folder,row,off,t,g,plant,side,solver,first,ref,labels,labs,rep,mapping,attempts,start_time):
    n=len(labels)
    model=plant.model
    records,states,actions,fails,valid={},[],[],[],[]
    for j in range(32):
        states.append(contact_state(plant.data.qpos[:],plant.data.qvel[:]).cpu().numpy())
        cmd=first if j==0 else ref[j].expand(n,-1)
        actions.append(cmd.cpu().numpy())
        ev=plant.step_contact(cmd,side,torch.as_tensor(labs[(t+j)*10:(t+j+1)*10],device=DEVICE).expand(n,-1),record=True)
        for key,value in ev["substeps"].items():
            records.setdefault(key,[]).append(value.cpu().numpy())
        fails.append(ev["first_fail_substep"].cpu().numpy())
        valid.append(ev["valid_full_interval"].cpu().numpy())
    states.append(contact_state(plant.data.qpos[:],plant.data.qvel[:]).cpu().numpy())
    records={k:np.stack(v) for k,v in records.items()}
    events,judges=judge_trace(model,row,solver["qpos"],solver["qvel"],records)
    np.savez_compressed(folder/"substeps.npz",**records,event_phase=events,training_phase=labs[10*t:10*(t+32)].reshape(32,10))
    failed=np.stack(fails)
    valid=np.stack(valid)
    live=valid & np.concatenate([np.ones((1,n),bool),np.logical_and.accumulate(valid & (failed==0),axis=0)[:-1]])
    np.savez(folder/"dynamics.npz",state=states,action=actions,valid=live,fail=failed,
             physical=(first.cpu().numpy()*mapping.scale+mapping.offset),
             fixed_effort=((first-rep.reward_home)/rep.reward_unit).cpu().numpy())
    dump(folder/"receipt.json",dict(row=row,offset=off,attempts=attempts,labels=labels,judges=judges,
         frame=t,goal_frame=g,legal_h1=int(live.sum()),wall_s=time.monotonic()-start_time))
    return int(live.sum())


@torch.no_grad()
def collect(args):
    begin=time.monotonic()
    cfg=json.loads((U0.parent/"actual_config.json").read_text())["cfg"]
    root=Path(cfg["reference_directory"])
    out, raw_root = args.output, args.raw
    out.mkdir(exist_ok=True)
    raw_root.mkdir(exist_ok=True)
    rows=register(cfg)
    spec=dict(starts=rows,actors=[str(U0),str(U200)],common_tail="31 recorded reference targets",
              query="frozen actor, common seeded noisy measured proprio, no added action exploration",
              tail=cfg["reference_tail"],prefix_ticks=100, retries="only after a rejected physical prefix; first valid registered offset")
    if args.preserve_continuous_bias:
        spec["solver_schema"] = "continuous_bias_v1"
        if out == OUT or raw_root == RAW:
            raise ValueError("A new solver identity requires independent output directories")
    reg=out/"registration.json"
    if reg.exists() and json.loads(reg.read_text())!=spec:
        raise ValueError("Changed registered matrix")
    dump(reg,spec)
    if args.register_only:
        return
    model=make_model()
    rep=ContactRepresentation(model,DEVICE)
    robot=RobotRepresentation(model,DEVICE)
    mapping=ActionMap(model)
    bank=DoorMotions([root/n for n in cfg["references"]],rep,DEVICE,reference_tail=cfg["reference_tail"])
    actors={}
    for tag,file in [("u0",U0),("u200",U200)]:
        actor,_=build_actor(rep,cfg,model,DEVICE)
        actor.load_state_dict(torch.load(file,map_location="cpu",weights_only=False)["actor"])
        actors[tag]=actor.eval()
    n=28
    plant=ContactPlant(model,n,DEVICE,preserve_continuous_bias=args.preserve_continuous_bias)
    for row in rows:
        folder=raw_root/row["id"]
        folder.mkdir(exist_ok=True)
        if (folder/"receipt.json").exists():
            continue
        start_time=time.monotonic()
        path,goal=Path(row["path"]),Path(row["reference"])
        labs=phases(path)
        side=torch.full((n,),int(row["side"]=="push"),device=DEVICE,dtype=torch.long)
        def vec(a):
            return tensor(np.array(a),DEVICE)
        def phase_at(t):
            return torch.as_tensor(labs[t*10:t*10+10],device=DEVICE).expand(n,-1)
        attempts=[]
        for off in row["alternative_offsets"]:
            t=row["frame"]+off
            g=row["goal_frame"]+off
            torch.manual_seed(row["seed"])
            plant.reset(vec(arr(path,"qpos")[t-10]).expand(n,-1),vec(arr(path,"qvel")[t-10]).expand(n,-1))
            previous=vec(arr(path,"action_clipped")[t-11])
            clean,noisy=[],[]
            failures=[]
            for j in range(t-10,t+1):
                obs=sensor(robot,full_state(plant.data.qpos[:1],plant.data.qvel[:1]),previous[None])
                clean.append(obs)
                noisy.append(robot.add_proprio_noise(obs))
                if j<t:
                    previous=vec(arr(path,"action_clipped")[j])
                    ev=plant.step_contact(previous.expand(n,-1),side,phase_at(j))
                    failures.append([int(ev["first_fail_substep"][0]),int(ev["reason"][0]),bool(ev["valid_full_interval"][0])])
            attempts.append(dict(offset=off,failures=failures))
            if not any(f or not valid for f,_,valid in failures):
                break
        else:
            dump(folder/"receipt.json",dict(row=row,attempts=attempts,rejected=True))
            continue
        solver=register_solver(plant)
        frame=torch.tensor([bank.starts[goal.name]+g],device=DEVICE)
        _,motion=bank.goals(rep,frame,plant.data.qpos[:1,:7],plant.data.qpos[:1,31])
        history=torch.stack(noisy[-10:],1)
        obs=build_actor_obs_td({"motion":motion},history)
        raw={name:a.raw(obs)[0] for name,a in actors.items()}
        ref=vec(arr(goal,"action_clipped")[g:g+32])
        labels,first=branches(raw,ref[0],mapping.scale)
        assert len(first)==n
        np.savez(folder/"start.npz",**solver,history=history.cpu().numpy(),clean_history=torch.stack(clean[-10:],1).cpu().numpy(),
            goal=motion.cpu().numpy(),clock=frame.cpu().numpy(),previous=previous.cpu().numpy(),
            reference=ref.cpu().numpy(),**{name:value.cpu().numpy() for name,value in raw.items()})
        count=integrate_branches(folder,row,off,t,g,plant,side,solver,first,ref,labels,labs,rep,mapping,attempts,start_time)
        print(row["id"],off,count,flush=True)
    dump(out/"collection.json",dict(wall_s=time.monotonic()-begin,entries=[json.loads((raw_root/r["id"]/"receipt.json").read_text()) for r in rows]))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--register-only",action="store_true")
    p.add_argument("--output",type=Path,default=OUT)
    p.add_argument("--raw",type=Path,default=RAW)
    p.add_argument("--preserve-continuous-bias",action="store_true")
    collect(p.parse_args())
