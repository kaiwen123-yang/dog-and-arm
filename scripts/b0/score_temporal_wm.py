"""Score a temporal WM on registered validation branches and original long windows."""
import argparse
import csv
import json
import os
import time
from pathlib import Path

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg, contact_context, contact_state
from learning.b0.contact_policy import DoorMotions
from learning.b0.contact_replay import MODES
from learning.b0.physics import ActionMap, WHEELS, make_model
from scripts.b0.fit_contact_model import prediction_errors
from scripts.b0.h32_fit_recovery_wm import load_cohorts

BASE = Path("results/b0")
RAW = Path("results/raw_large/b0/response_entries_v1")
REG = BASE / "standard_response_20261124/registration.json"
OUT = BASE / "standard_temporal_20261124/wm_validation"
SOURCES = ("recovery_b_grip_challenge_r1", "lanes_modes_v1")


def csv_file(path, rows):
    with path.open("w") as f:
        writer = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_wm(path, model, rep, device):
    weight = torch.load(path, map_location="cpu", weights_only=False)
    ident = weight.get("temporal_id", weight.get("cfg", {}).get("temporal_id", "C20"))
    mapping = ActionMap(model)
    hidden = tuple(weight["hidden"] if "hidden" in weight else weight["cfg"]["wm_hidden"])
    if ident == "C20":
        from supermimic.models import Dynamics
        from learning.b0.model import tensor
        dyn = Dynamics(rep, 23, 5, tensor(mapping.scale, device), tensor(mapping.offset, device), hidden).to(device)
    else:
        from learning.b0.temporal_dynamics import make_dynamics
        dyn = make_dynamics(model, rep, mapping, hidden, ident, device)
    dyn.load_state_dict(weight["dyn"], strict=True)
    return dyn.eval(), ident


def metrics(rep, y, x):
    delta = y - x
    tcp1 = rep.tcp_pose(y[..., :7], y[..., 7:31])[0]
    tcp0 = rep.tcp_pose(x[..., :7], x[..., 7:31])[0]
    return dict(tcp_mm=(tcp1 - tcp0).norm(dim=-1)*1000, jaw_mm=(delta[...,29]-delta[...,30])*1000,
                coupling_mm=(delta[...,29]+delta[...,30])*1000, finger1_mm=delta[...,29]*1000,
                finger2_mm=delta[...,30]*1000, finger1_v_m_s=delta[...,59], finger2_v_m_s=delta[...,60],
                j2_rad=delta[...,24], j2_v_rad_s=delta[...,54], arm_rad=delta[...,23:29].square().mean(-1).sqrt(),
                arm_v_rad_s=delta[...,53:59].square().mean(-1).sqrt(), door_rad=delta[...,61], door_v_rad_s=delta[...,62])


def error_value(t):
    return None if not torch.isfinite(t) else float(t)


def score_branches(model, rep, dyn, ident, device, raw, reg):
    endpoints, substeps, directions = [], [], []
    for row in json.loads(reg.read_text())["starts"]:
        if row["split"] != "validation":
            continue
        folder = raw / row["id"]
        receipt = json.loads((folder / "receipt.json").read_text())
        if receipt.get("rejected"):
            continue
        if row != receipt["row"]:
            raise ValueError("Response registration identity mismatch")
        with np.load(folder / "dynamics.npz") as d, np.load(folder / "substeps.npz") as s:
            truth = torch.as_tensor(d["state"][:2], device=device)
            action = torch.as_tensor(d["action"][0], device=device)
            cmd = d["physical"]
            q = torch.as_tensor(s["qpos_post"][0], device=device)
            v = torch.as_tensor(s["qvel_post"][0], device=device)
            both = (s["finger_load_N"][0] > .01)
            fail = d["fail"][0]
            legal = d["valid"][0]
        aux0 = truth[0,...,:7]
        r0 = rep.represent(truth[0])
        context = contact_context(model, row["side"], device).expand(len(action), -1)
        aux, r = dyn(r0, action, aux0, context)
        pred = rep.reconstruct_full_state(aux, r)
        real_path = contact_state(q, v)
        torch.testing.assert_close(real_path[:, -1], truth[1], rtol=0, atol=0)
        path = None
        if ident == "T2":
            aux, r = aux0, r0
            inner = []
            for _ in range(10):
                aux, r = dyn.inner_step(r, action, aux, context)
                inner.append(rep.reconstruct_full_state(aux,r))
            path = torch.stack(inner, dim=1)
            torch.testing.assert_close(path[:,-1], pred, equal_nan=True)
        state_norm = dyn.state_normalizer(r0).abs().amax(-1)
        action_norm = dyn.action_normalizer(dyn.proc(action)).abs().amax(-1)
        errs = metrics(rep, pred, truth[1])
        labels = receipt["labels"]
        jaw = lambda a: (a[...,29] - a[...,30])*1000
        for b, (actor,kind,ch,delta) in enumerate(labels):
            common = dict(start=row["id"], side=row["side"], phase=row["phase"], actor=actor, branch=kind,
                          channel=ch, requested_delta=delta, legal_first20=bool(legal[b]), train_failure_tick=int(fail[b]),
                          judge_failure_tick=(receipt["judges"][b]["failure"] or {}).get("first_failure_substep"))
            endpoints.append(dict(**common, actual_jaw_mm=float(jaw(truth[1,b])), pred_jaw_mm=error_value(jaw(pred[b])),
                state_max_abs_z=error_value(state_norm[b]), action_max_abs_z=error_value(action_norm[b]),
                nonfinite_coordinates=int((~pred[b].isfinite()).sum()), **{k:error_value(t[b]) for k,t in errs.items()}))
            if kind=="delta":
                base=labels.index(next(i for i in labels if i[:2]==[actor,"actor"]))
                repeat=labels.index(next(i for i in labels if i[:2]==[actor,"repeat"]))
                gap=cmd[b,ch]-cmd[base,ch]
                true=float(jaw(truth[1,b])-jaw(truth[1,base]))
                pred_delta=error_value(jaw(pred[b])-jaw(pred[base]))
                repeat_mm=float(abs(jaw(truth[1,repeat])-jaw(truth[1,base])))
                same=(np.array_equal(both[b],both[base]) and np.array_equal(both[repeat],both[base])
                      and fail[b]==fail[base]==fail[repeat])
                directions.append(dict(**common, realized_delta=float(gap), actual_mm=true, pred_mm=pred_delta, repeat_mm=repeat_mm,
                    same_contact_and_failure=bool(same), interpretable=bool(same and abs(true)>repeat_mm and abs(gap)>1e-10)))
        if path is not None:
            me = metrics(rep, path, real_path)
            # All ten points are predictions under a single command, including the physical diagnostic tail.
            for b,(actor,kind,ch,delta) in enumerate(labels):
                for k in range(10):
                    substeps.append(dict(start=row["id"],actor=actor,branch=kind,channel=ch,delta=delta,step=k+1,
                        actual_jaw_mm=float(jaw(real_path[b,k])), pred_jaw_mm=error_value(jaw(path[b,k])),
                        actual_vel1_m_s=float(v[b,k,28]), actual_vel2_m_s=float(v[b,k,29]),
                        pred_vel1_m_s=error_value(path[b,k,59]),pred_vel2_m_s=error_value(path[b,k,60]),
                        nonfinite_coordinates=int((~path[b,k].isfinite()).sum()), **{n:error_value(t[b,k]) for n,t in me.items()}))
    return endpoints,directions,substeps


def validation_episodes(source, model, rep, device):
    registration=json.loads((BASE/source/"registration.json").read_text())
    cfg=json.loads((Path(registration["anchor"]).parent/"actual_config.json").read_text())["cfg"]
    refs=[Path(registration["reference_directory"])/p for p in cfg["references"]]
    rows=[r for r in json.loads((BASE/source/"cohorts.json").read_text()) if r["split"]=="validation"]
    if [r["seed"] for r in rows]!=[s for sp,s in registration["allocation"] if sp=="validation"]:
        raise ValueError("Validation allocation mismatch")
    return load_cohorts(rows,refs,DoorMotions(refs,rep,device),model,device)[0]


def fmt(x):
    finite=x[np.isfinite(x)].astype(np.float64)
    return dict(nonfinite=len(x)-len(finite), p95=float(np.percentile(finite,95)) if len(finite) else None,
                rmse=float(np.mean(finite**2)**.5) if len(finite) else None,
                maximum=float(np.max(finite)) if len(finite) else None)


def score_long(source, episodes, model, rep, dyn, device):
    wheel=torch.tensor([31+model.joint(n).dofadr.item() for n in WHEELS],device=device)
    rows=[]
    for side in ("pull","push"):
        eps=[ep for ep in episodes if ep.side==side]
        offsets=np.cumsum([0]+[len(e.state) for e in eps])[:-1]
        states=torch.cat([e.state for e in eps])
        actions=torch.cat([torch.cat((e.action,e.action[-1:])) for e in eps])
        contexts=torch.cat([e.context.expand(len(e.state),-1) for e in eps])
        for h in (1,7,32):
            selected={}
            for mode in (*MODES,"recontact"):
                idx=np.concatenate([off+e.starts(h)[e.modes[e.starts(h)]==mode] for off,e in zip(offsets,eps,strict=True)])
                n=len(idx)
                if n>512:
                    idx=np.random.default_rng(301).choice(idx,512,replace=False)
                selected[mode]=n,idx
            union=np.unique(np.concatenate([picks for _,picks in selected.values()]))
            measurements={}
            for chunk in np.array_split(union,max(1,int(np.ceil(len(union)/512)))):
                if not len(chunk):
                    continue
                ix=torch.as_tensor(chunk,device=device)
                aux=states[ix,:7]
                r=rep.represent(states[ix])
                for t in range(h):
                    aux,r=dyn(r,actions[ix+t],aux,contexts[ix])
                me=prediction_errors(rep,aux,r,states[ix+h],wheel)
                for k,v in me.items():
                    measurements.setdefault(k,[]).append(v.cpu().numpy())
            for mode,(n,ids) in selected.items():
                for metric, arrs in measurements.items():
                    vals=np.concatenate(arrs)[np.searchsorted(union,ids)]
                    rows.append(dict(source=source,side=side,h=h,mode=mode,metric=metric,available=n,scored=len(ids),**fmt(vals)))
    return rows


@torch.no_grad()
def main(args):
    rep=ContactRepresentation(model:=make_model(),args.device)
    datasets={s:validation_episodes(s,model,rep,args.device) for s in SOURCES}
    for name,path in args.node:
        started=time.monotonic()
        output=OUT/name
        output.mkdir(parents=True,exist_ok=True)
        dyn,ident=load_wm(Path(path),model,rep,args.device)
        ends,directions,steps=score_branches(model,rep,dyn,ident,args.device,args.raw,args.registration)
        csv_file(output/"responses.csv",ends)
        csv_file(output/"directions.csv",directions)
        if steps:
            csv_file(output/"microsteps.csv",steps)
        long=[]
        for source,eps in datasets.items():
            long.extend(score_long(source,eps,model,rep,dyn,args.device))
        csv_file(output/"long_validation.csv",long)
        (output/"score.json").write_text(json.dumps(dict(checkpoint=path,temporal_id=ident,device=args.device,
            validation_registration=str(args.registration),response_raw=str(args.raw),start_branches=len(ends),
            starts=len(set(r["start"] for r in ends)),source_trajectories=2,
            long_window_cap=512,selection_seed=301,sources=list(datasets),wall_seconds=time.monotonic()-started,
            response_errors="signed prediction minus measurement, except TCP norm and arm joint RMS",
            first_interval="all ten substeps, including diagnostic tail after either judge or training failure",
            long_window_definition="same >=h preregistered valid transitions within lane; end at h, stratify by initial contact mode; includes full terminal interval",
            validation_only=True,parameter_updates=0),indent=2)+"\n")
        print(name,ident,round(time.monotonic()-started,2),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node",nargs=2,action="append",required=True,metavar=("TAG","CHECKPOINT"))
    p.add_argument("--device",default="cuda:0")
    p.add_argument("--raw",type=Path,default=RAW)
    p.add_argument("--registration",type=Path,default=REG)
    main(p.parse_args())
