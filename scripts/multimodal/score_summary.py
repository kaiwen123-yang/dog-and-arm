"""Summarize preassigned physical attempts and command pairs using the recorded trajectories."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np


def read(path):
    return json.loads(path.read_text())


def summarize(rows):
    return dict(attempts=len(rows),successes=sum(r["success"] for r in rows),
                physics_steps=sum(r["physics_steps"] for r in rows),decisions=sum(r["decision_calls"] for r in rows),
                camera_frames=sum(r["camera_frames"] for r in rows),
                completed_events=dict(Counter(e["phase"] for r in rows for e in r["events"])),
                first_failure_phase=dict(Counter(r["first_failure"]["phase"] for r in rows if r["first_failure"])),
                first_failure_reason=dict(Counter(r["first_failure"]["reason"] for r in rows if r["first_failure"])),
                cases_with_door_contact=sum(r["robot_door_contact_steps"]>0 for r in rows),
                cases_with_bilateral_contact=sum(r["bilateral_contact_steps"]>0 for r in rows),
                max_effective_hinge_change_deg=max(abs(r["final_deg"]-r["initial_deg"]) for r in rows))


def cases(directory):
    rows=[]
    for path in sorted(directory.glob("*/result.json")):
        r=read(path)
        ep=Path(r["raw_episode"])
        o=np.load(ep/"object_state.npy",mmap_mode="r")
        t=np.load(ep/"t.npy",mmap_mode="r")
        if len(t)!=r["decision_calls"]+1 or abs(t[-1]-r["physics_steps"]*.002)>1e-7:
            raise ValueError(f"Interval count mismatch in {path}")
        if r["success"] != (len(r["events"])==12 and r["first_failure"] is None):
            raise ValueError(f"Invalid success label in {path}")
        r["initial_deg"]=float(np.rad2deg(o[0,0]))
        r["camera_source"]="integrated native MuJoCo trajectory"
        r["result_file"]=str(path)
        rows.append(r)
    return rows


def compare_commands(rows):
    pairs=[]
    for scene,side in sorted({(r["scene_id"],r["side"]) for r in rows}):
        pair=sorted([r for r in rows if r["scene_id"]==scene and r["side"]==side],
                    key=lambda r:r["target_deg"])
        if [r["target_deg"] for r in pair]!=[15,25]:
            raise ValueError(f"Incomplete instruction pair for {scene}/{side}")
        a,b=pair
        ea,eb=Path(a["raw_episode"]),Path(b["raw_episode"])
        initial_equal={}
        for name in ("qpos","qvel","proprio","previous_action","rgb","depth","depth_valid"):
            aa=np.load(ea/f"{name}.npy",mmap_mode="r")
            bb=np.load(eb/f"{name}.npy",mmap_mode="r")
            initial_equal[name]=bool(np.array_equal(aa[0],bb[0]))
        if not all(initial_equal.values()) or a["initial_state_sha256"]!=b["initial_state_sha256"]:
            raise ValueError(f"Reset conditions differ in {scene}/{side}")
        aa,ab=(np.load(e/"action_clipped.npy",mmap_mode="r") for e in (ea,eb))
        n=min(len(aa),len(ab))
        d=np.abs(aa[:n].astype(float)-ab[:n])
        difftick=np.flatnonzero(np.max(d,axis=1)>1e-5)
        pairs.append(dict(scene=scene,side=side,case_ids=[a["case_id"],b["case_id"]],identical_initial=initial_equal,
                          first_action_maxabs=float(d[0].max()),first_action_l1mean=float(d[0].mean()),
                          first_gt_1e_minus5_s=float(difftick[0]*.02) if len(difftick) else None,
                          shared_duration_decisions=n,matched_time_mean_abs_action_difference=float(d.mean()),
                          terminal_hinge_difference_25_minus_15_deg=float(b["final_deg"]-a["final_deg"]),
                          final_deg=[a["final_deg"],b["final_deg"]],success=[a["success"],b["success"]]))
    return pairs


def main(run,output):
    output.mkdir(parents=True,exist_ok=True)
    rows=cases(run/"formal_cases")
    methods={}
    for method in ("supervised","wm_optimized"):
        part=[r for r in rows if r["branch"]==method]
        if len(part)!=12 or len({r["checkpoint_sha256"] for r in part})!=1:
            raise ValueError(f"Expected a single frozen checkpoint across 12 {method} cases")
        methods[method]=dict(total=summarize(part),scenes={},command_pairs=compare_commands(part))
        for scene in ("tr_nominal","va_pose","te_combination"):
            group=[r for r in part if r["scene_id"]==scene]
            if len(group)!=4:
                raise ValueError(f"Missing cases for {scene}")
            methods[method]["scenes"][scene]=summarize(group)
    for scene,side,goal in {(r["scene_id"],r["side"],r["target_deg"]) for r in rows}:
        same=[r for r in rows if (r["scene_id"],r["side"],r["target_deg"])==(scene,side,goal)]
        if len(same)!=2 or len({r["initial_state_sha256"] for r in same})!=1:
            raise ValueError("Branch reset mismatch")
    datasets={}
    for name,folder in (("parent","parent_cases"),("development","development"),("repair","repair_cases")):
        evidence=cases(run/folder)
        if not evidence:
            continue
        datasets[name]=dict(outcome=summarize(evidence),cases=evidence)
        if name!="development":
            datasets[name]["command_pairs"]=compare_commands(evidence)
    for name,value in (("physics_cases",rows),("physics_summary",methods),("development_cases",datasets)):
        (output/f"{name}.json").write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps({method:r["total"] for method,r in methods.items()}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("run",type=Path)
    p.add_argument("output",type=Path)
    args=p.parse_args()
    main(args.run,args.output)
