"""Compare frozen Actors on identical archived real histories without stepping a plant."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
from mjlab.tasks.tracking.mdp.commands import MotionLoader
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions, actor_goal_schema, build_actor, sensor
from learning.b0.model import RobotRepresentation, full_state
from learning.b0.physics import ActionMap, make_model
from learning.b0.training import FreeRun

PARENT = Path("results/raw_large/b0/official_flow_continuation_20261125")
LIGHT_PARENT = Path("results/b0/standard_official_flow_continuation_20261125")
RAW = Path("results/raw_large/b0/refxy2_pair_20261125")
OUT = Path("results/b0/refxy2_pair_20261125")
WEIGHT = "encoders.motion.0.weight"


def read(p):
    return json.loads(p.read_text())


def write(p, obj):
    p.parent.mkdir(exist_ok=True, parents=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")
    tmp.replace(p)


def frozen(paths, mode, node, rep, model, device):
    where = (PARENT/"checkpoint_010000.pt" if mode=="parent" else
             RAW/mode/f"checkpoint_{node:06}.pt")
    package = torch.load(where, map_location="cpu", mmap=True, weights_only=False)
    cfg = package["cfg"]
    assert cfg["execution_recipe"] == "official_flow_s0_v1"
    if mode != "parent":
        assert cfg["feature_mode"] == mode
    actor, _ = build_actor(rep, cfg, model, device)
    actor.load_state_dict(package["actor"], strict=True)
    actor.eval().requires_grad_(False)
    bank = DoorMotions(paths, rep, device, actor_schema=actor_goal_schema(cfg),
                       reference_tail=cfg["reference_tail"])
    return SimpleNamespace(actor=actor, cfg=cfg, bank=bank, package=package, path=str(where))


def tensor(a, device):
    return torch.tensor(np.array(a), dtype=torch.float32, device=device)


def histories(device, rep, paths):
    rows = []
    # Fixed stratification across backend, approach/full and both directions.
    for backend in ("warp", "native"):
        for side in ("pull", "push"):
            for kind, segment in (("full","full"), ("v1","approach_grasp")):
                identity = Path(f"u010000_{backend}_{kind}")/side/segment/"nominal"
                record = read(LIGHT_PARENT/"physics"/identity/"result.json")
                root = PARENT/"physics"/identity
                step = np.load(root/"physics_step.npy",mmap_mode="r")
                q,v,a = (np.load(root/(n+".npy"),mmap_mode="r")
                         for n in ("qpos","qvel","clipped_action"))
                count = min(len(q)-1, len(a))
                for f in sorted(set((10, count//2, count-2))):
                    if f < 10 or f >= count:
                        continue
                    assert np.all(np.diff(step[f-10:f+1])==10)
                    s = full_state(tensor(q[f-9:f+1],device),tensor(v[f-9:f+1],device))
                    h = sensor(rep,s,tensor(a[f-10:f],device))[None]
                    rows.append(dict(identity=str(identity), kind=kind, source=str(root), f=f,
                        ep=record["episode"], frame=record["start_substep"]//10+f,
                        hist=h, current=s[-1:], hinge=tensor(q[f:f+1,31],device)))
    motion = MotionLoader(str(PARENT/"free/u010000/motion"), rep.fk, device)
    starts = torch.nn.functional.pad(motion.motion_ends[:-1],(1,0))
    for name in ("support", "moving_arm", "park"):
        root = PARENT/"free/u010000/physical"/(name+"_F01")
        q,v,a = (np.load(root/(n+".npy"),mmap_mode="r") for n in ("qpos","qvel","action_clipped"))
        times = np.load(root/"t.npy",mmap_mode="r")
        for f in (10, len(a)//2, len(a)-2):
            assert np.max(abs(np.diff(times[f-10:f+1])-.02))<1e-6
            s = full_state(tensor(q[f-9:f+1],device),tensor(v[f-9:f+1],device))
            h = FreeRun.sensor(SimpleNamespace(rep=rep),s,tensor(a[f-10:f],device))[None]
            rows.append(dict(identity="free/"+name+"_F01", kind="free", source=str(root), f=f,
                    ep=name, frame=int(starts[motion.motion_names.index(name)])+f,
                    hist=h,current=s[-1:]))
    return rows,motion


def obs_for(row, run, rep, free_motion, device):
    if row["kind"]=="free":
        motion = free_motion
        t = torch.tensor([row["frame"]],device=device)
        env = SimpleNamespace(rep=rep, motion=motion, actor=run.actor, cfg=run.cfg,
                              refxy2_mode=run.cfg.get("feature_mode"))
        obs = FreeRun.actor_obs(env,row["current"],t,row["hist"])
    else:
        motion = run.bank
        t = torch.tensor([motion.starts[row["ep"]]+row["frame"]],device=device)
        _,goal = motion.goals(rep,t,row["current"][:,:7],row["hinge"])
        obs = build_actor_obs_td({"motion":goal},row["hist"])
    return obs,motion.root_pos_w[t]


def expected(ref,aux):
    w,x,y,z = aux[...,3:7].unbind(-1)
    angle = torch.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
    dx,dy = (ref[...,:2]-aux[...,:2]).unbind(-1)
    c,s = angle.cos(),angle.sin()
    return torch.stack((c*dx+s*dy,-s*dx+c*dy),-1)/.05


def coordinate_jacobian(device):
    from learning.b0.refxy2 import append_refxy2
    goal = torch.zeros(1,540, device=device, dtype=torch.float64)
    ref = goal.new_tensor([[.35,.11,.08]])
    init = goal.new_tensor([.04,-.07,.7])
    def feature(inputs):
        x,y,yaw = inputs
        zero=x*0
        pose=torch.stack((x,y,zero,torch.cos(yaw/2),zero,zero,torch.sin(yaw/2)))[None]
        return append_refxy2(goal,ref,pose,"measured")[0,540:]
    xy=feature(init).detach()
    c,s=init[2].cos(),init[2].sin()
    analytic=torch.stack((torch.stack((-c/.05,-s/.05,xy[1])),torch.stack((s/.05,-c/.05,-xy[0]))))
    jac = torch.autograd.functional.jacobian(feature,init)
    torch.testing.assert_close(jac,analytic,rtol=1e-10,atol=1e-10)
    return dict(variable_order=["root_x_m","root_y_m","yaw_rad"],autograd=jac.tolist(),analytic=analytic.tolist())


def inference(run,obs,mapping):
    goal,history=obs["goal_motion"],obs["history"]
    normalized=run.actor.goal_normalizers["motion"](goal)
    layer=run.actor.encoders["motion"][0](normalized)
    raw=run.actor.raw(obs)
    clipped=raw.clamp(-1,1)
    physical=(clipped*torch.as_tensor(mapping.scale,device=raw.device)+
              torch.as_tensor(mapping.offset,device=raw.device))
    return dict(history=history,original_goal=goal[...,:540],original_normalized=normalized[...,:540],
                first_activation=layer,raw=raw,clipped=clipped,physical=physical)


def maxabs(x):
    return float(x.detach().abs().max())


def equivalent(runs):
    parent = runs["parent"].package
    for key in ("actor","dyn","critic"):
        a,b=(runs[m].package[key] for m in ("zero","measured"))
        assert a.keys()==b.keys()
        for name in a:
            assert torch.equal(a[name],b[name]), (key,name)
            prev=parent[key].get(name)
            if name==WEIGHT:
                assert not a[name][:,540:].count_nonzero()
                assert torch.equal(a[name][:,:540],prev)
            elif prev is not None:
                assert torch.equal(a[name],prev), (key,name)
    return {key:len(parent[key]) for key in ("actor","dyn","critic")}


def assess(node,device):
    torch.set_num_threads(2)
    torch.set_float32_matmul_precision("highest")
    parent = torch.load(PARENT/"checkpoint_010000.pt", weights_only=False, mmap=True, map_location="cpu")
    model=make_model()
    rep=RobotRepresentation(model,device)
    paths=list(map(Path,parent["cfg"]["reference_paths"]))
    modelmap=ActionMap(model)
    runs={m:frozen(paths,m,node,rep,model,device) for m in
          (("parent","zero","measured") if node==0 else ("zero","measured"))}
    exact=equivalent(runs) if node==0 else None
    jac=coordinate_jacobian(device)
    rows,motion=histories(device,rep,paths)
    results=[]
    for row in rows:
        record={k:v for k,v in row.items() if k not in ("current","hist","hinge")}
        outputs={}
        for name,run in runs.items():
            obs,ref=obs_for(row,run,rep,motion,device)
            goal=obs["goal_motion"]
            outputs[name]=inference(run,obs,modelmap)
            if name=="parent":
                continue
            xy=expected(ref,row["current"][...,:7])
            tail=goal[...,540:]
            torch.testing.assert_close(tail,xy if name=="measured" else torch.zeros_like(xy),atol=1e-4,rtol=2e-5)
            def readout(t):
                return run.actor.raw(build_actor_obs_td(
                    {"motion":torch.cat((goal[...,:540],t),-1)},row["hist"]))
            neutral=readout(torch.zeros_like(tail))
            derivatives=[]
            for axis in (0,1):
                tangent=torch.zeros_like(tail)
                tangent[...,axis]=1
                _,jvp=torch.autograd.functional.jvp(readout,tail,tangent)
                derivatives.append(maxabs(jvp))
            record[name]=dict(actual_tail=tail[0].tolist(), expected_measured_xy=xy[0].tolist(),
                action_max_delta_when_tail_zero=maxabs(outputs[name]["raw"]-neutral),
                raw_action_inf_norm_derivatives_wrt_scaled_x_y=derivatives)
        if node==0:
            for mode in ("zero","measured"):
                for comp in ("parent","zero"):
                    record[mode+"_vs_"+comp]={k:maxabs(v-outputs[comp][k]) for k,v in outputs[mode].items()}
                    if comp=="zero":
                        assert max(record[mode+"_vs_"+comp].values())==0
                assert max(record[mode]["raw_action_inf_norm_derivatives_wrt_scaled_x_y"])==0
        results.append(record)
    filename = OUT/f"frozen_inputs_{node:06}.json"
    write(filename,dict(local_node=node, new_physics=0, new_optimizer_steps=0,
                        source="Archived physical histories at ten contiguous 20ms boundaries with previous applied action",
                        device=device, float32_matmul_precision="highest", files={m:r.path for m,r in runs.items()},
                        exact_network_tensor_counts_542_pair=exact, coordinate_auto_vs_analytic=jac, rows=results))
    print(filename, len(results), flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("node", type=int)
    parser.add_argument("--device",default="cpu")
    args=parser.parse_args()
    assess(args.node,args.device)
