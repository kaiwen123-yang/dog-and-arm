"""Evaluate the registered C20 nodes and lock one experimental WM before either H32 arm."""
import argparse
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import torch
import yaml
from scripts.b0.dynamics_c20_pair import (DEVICE, OUT, RAW, checkpoint, digest, load_registration,
                                          model_and_rep, new_wm, write)
from scripts.b0.score_temporal_wm import csv_file, score_branches, score_long, validation_episodes


def maybe_num(x):
    return float(x) if x is not None and np.isfinite(float(x)) else None


@torch.no_grad()
def evaluate(info, arm, node):
    model, rep = model_and_rep(info["physics_dt"])
    path = checkpoint(info,arm,node)
    weight = torch.load(path, weights_only=False, map_location="cpu")
    if weight.get("physics_dt",.002) != info["physics_dt"] or weight.get("substep_coeff",.55) != rep.substep_coeff:
        raise ValueError("WM and validation numerical identities differ")
    dyn = new_wm(model,rep,weight).eval()
    recipe = yaml.safe_load(Path(info["data_recipe"]).read_text())["wm_data_recipe"]["sources"]
    registration = Path(recipe["response"]["registration"])
    response_dir = Path(recipe["response"]["raw"])
    endpoints, directions, _ = score_branches(model,rep,dyn,"C20",DEVICE,response_dir,registration)
    result, values = {}, {}
    for side in ("pull","push"):
        selected = [r for r in endpoints if (r["side"],r["phase"],r["actor"],r["branch"])==(side,"hold","u0","actor")]
        if len(selected)!=1 or not selected[0]["legal_first20"]:
            values[side+"_first_tcp_mm"] = None
        else:
            values[side+"_first_tcp_mm"] = maybe_num(selected[0]["tcp_mm"])
    long = []
    for source in ("grip","multimode"):
        folder = Path(recipe[source]["directory"]).resolve()
        eps = validation_episodes(str(folder), model, rep, DEVICE)
        rows = score_long(source,eps,model,rep,dyn,DEVICE)
        long.extend(rows)
        for side in ("pull","push"):
            matches = [r for r in rows if (r["side"],r["h"],r["mode"],r["metric"])==(side,32,"two_finger","tcp_mm")]
            key = f"{side}_{source}_h32_two_finger_tcp_p95_mm"
            values[key] = maybe_num(matches[0]["p95"]) if len(matches)==1 and matches[0]["scored"]>0 and not matches[0]["nonfinite"] else None
            result[key+"_scored"] = int(matches[0]["scored"]) if matches else 0
    result.update(values=values, checkpoint=str(path), checkpoint_sha256=digest(path), c=rep.substep_coeff,
                  physics_dt=info["physics_dt"], validation_source_roles=list(recipe), response_registration=str(registration),
                  nonfinite_response_coordinates=sum(r["nonfinite_coordinates"] for r in endpoints),
                  nonfinite_long_metric_windows=sum(r["nonfinite"] for r in long), gradients_or_updates=0)
    return result,endpoints,directions,long


def score(info,arm,node):
    folder=OUT/"offline_scores"/f"{arm}_{node:06}"
    folder.mkdir(parents=True,exist_ok=True)
    result,ends,directions,long=evaluate(info,arm,node)
    if node == 1000:
        again,_,_,_=evaluate(info,arm,node)
        result["repeat_values"]=again["values"]
        result["same_metric_sample_counts_on_repeat"]=all(result[k]==again[k] for k in result if k.endswith("_scored"))
        result["repeat_abs"]= {key:(abs(values-again["values"][key]) if values is not None and again["values"][key] is not None else None)
                               for key,values in result["values"].items()}
    csv_file(folder/"responses.csv",ends)
    if directions:
        csv_file(folder/"directions.csv",directions)
    csv_file(folder/"long_validation.csv",long)
    write(folder/"six_metrics.json",result)
    print(json.dumps(result),flush=True)


def lock(info):
    result={}
    for arm in ("C20","rebase"):
        if arm=="rebase" and (OUT/"rebase_closed_early.json").is_file():
            continue
        result[arm]=json.loads((OUT/"offline_scores"/f"{arm}_001000"/"six_metrics.json").read_text())
        if not result[arm]["same_metric_sample_counts_on_repeat"]:
            raise ValueError("A repeated score used different sample counts")
        for node in (0,50,200,1000):
            probe=json.loads((OUT/f"{arm}_fixed_probe_{node:06}.json").read_text(), parse_constant=lambda s:sys.exit(s))
            if len(probe)!=2 or any(len(v)!=4 for v in probe.values()):
                raise ValueError("Incomplete fixed physical-unit probe")
    metrics={}
    if "rebase" in result:
        baseline,changed=result["C20"],result["rebase"]
        for key,v in baseline["values"].items():
            alt=changed["values"][key]
            sample_key=key+"_scored"
            if baseline.get(sample_key) != changed.get(sample_key):
                raise ValueError("Unequal validation sample support")
            noise=[r["repeat_abs"][key] for r in (baseline,changed)]
            tol=max(noise) if all(n is not None for n in noise) else None
            metrics[key]=dict(old_stats_mm=v,rebase_mm=alt,repeat_tolerance_mm=tol,
                              noninferior=v is not None and alt is not None and tol is not None and alt<=v+tol)
    reviews={}
    for arm in result:
        for node in (50,200,1000):
            review_path = OUT/f"{arm}_stability_{node:06}.json"
            reviews[f"{arm}_{node}"] = json.loads(review_path.read_text())
    stable = "rebase" in result and all(r["disposition"]=="stable_on_fixed_probes" for key,r in reviews.items() if key.startswith("rebase"))
    if "rebase" in result:
        stable &= not (result["rebase"]["nonfinite_long_metric_windows"] or result["rebase"]["nonfinite_response_coordinates"])
    selected = "rebase" if len(metrics)==6 and all(r["noninferior"] for r in metrics.values()) and stable else "C20"
    exp=checkpoint(info,selected,1000)
    control=checkpoint(info,"C20",0)
    rec=dict(locked_at_bjt=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
             experiment_kind="development_h32_pilot", original_selected_wm=None, original_gate_passed=False,
             final_candidate=None, physics_identity=info["physics_identity"], physics_dt=info["physics_dt"], c=info["substep_coeff"],
             pilot_wm=str(exp), pilot_wm_sha256=digest(exp), control_wm=str(control), control_wm_sha256=digest(control),
             control_checkpoint=str(control), experiment_checkpoint=str(exp),
             selected_arm=selected, selection_rule="Default C20+1000; substitute rebased +1000 only when all six fixed metrics noninferior within exact same-sample repeat and no new nonfinite or unstable recurrence.",
             selection_metrics=metrics, physical_stability=stable, fixed_probes=list(reviews),
             rebase_closed_early=(OUT/"rebase_closed_early.json").exists(),
             new_h32_updates_at_lock=0, pilot_Budget=dict(h32=20,joint_wm=200,critic=400))
    budgets = {}
    for arm in ("C20","rebase"):
        runs = sorted(OUT.glob(f"{arm}_train_*.jsonl"))
        rows = [json.loads(line) for path in runs for line in path.read_text().splitlines()]
        if [r["k"] for r in rows] != list(range(1,len(rows)+1)):
            raise ValueError("Duplicate or incomplete sequence in offline update receipts")
        h1=sum(r["h"]==1 for r in rows)
        h7=sum(r["h"]==7 for r in rows)
        budgets[arm]=dict(new_updates=len(rows),h1=h1,h7=h7,real_windows=256*len(rows),
                          supervised_successors=256*(h1+7*h7),
                          fixed_coordinate_preclip_gt1=sum(r["grad_norm"]>1 for r in rows),
                          training_loop_seconds=sum(json.loads(p.read_text().splitlines()[-1])["elapsed_s"] for p in runs if p.stat().st_size),
                          peak_allocated_bytes=max((r["peak_allocated_bytes"] for r in rows),default=0),
                          interval_evidence=[str(p) for p in runs])
    rec["offline_warmup"]=budgets
    rec["train_data_lock"]=str(OUT/"c20_data_identity.json")
    write(OUT/"pilot_wm_locked.json",rec,exclusive=True)
    print(json.dumps(rec),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("score")
    s.add_argument("--arm",choices=("C20","rebase"),required=True)
    s.add_argument("--node",choices=(0,50,200,1000),type=int,required=True)
    sub.add_parser("lock")
    args=p.parse_args()
    torch.set_float32_matmul_precision("highest")
    info=load_registration()
    if args.cmd=="score":
        score(info,args.arm,args.node)
    else:
        lock(info)


if __name__=="__main__":
    main()
