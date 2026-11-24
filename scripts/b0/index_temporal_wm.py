"""Index registered bilateral validation results using per-start errors and unchanged long-window strata."""
import csv
import json
from pathlib import Path

import numpy as np


ROOT = Path("results/b0/standard_temporal_20261124/wm_validation")


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def index_node(path):
    meta=json.loads((path/"score.json").read_text())
    first=rows(path/"responses.csv")
    micro=rows(path/"microsteps.csv") if (path/"microsteps.csv").exists() else []
    directions=rows(path/"directions.csv")
    long=rows(path/"long_validation.csv")
    response=[]
    for row in first:
        if row["phase"]!="hold" or row["branch"]!="actor":
            continue
        repeat=next(r for r in first if (r["start"],r["actor"],r["branch"])==(row["start"],row["actor"],"repeat"))
        record={k:row[k] for k in ("start","actor","side")}
        record.update({k:float(row[k]) if row[k] else None for k in
            ("jaw_mm","finger1_mm","finger2_mm","finger1_v_m_s","finger2_v_m_s","tcp_mm","arm_rad","arm_v_rad_s",
             "door_rad","door_v_rad_s","j2_rad","j2_v_rad_s","actual_jaw_mm","pred_jaw_mm","state_max_abs_z","action_max_abs_z")})
        record["jaw_repeat_difference_mm"]=abs(float(row["actual_jaw_mm"])-float(repeat["actual_jaw_mm"]))
        trace=[r for r in micro if r["start"]==row["start"] and r["actor"]==row["actor"] and r["branch"]=="actor"]
        if trace:
            def gap(col):
                return np.array([float(t[col]) if t[col] else np.nan for t in trace])
            record["micro"]={}
            for k in ("actual","pred"):
                velocity=gap(k+"_vel1_m_s")-gap(k+"_vel2_m_s")
                position=gap(k+"_jaw_mm")
                record["micro"][k]=dict(peak_abs_opening_speed_m_s=float(abs(velocity).max()),
                    opening_speed_sign_changes=int((velocity[1:]*velocity[:-1]<0).sum()),
                    first2_to_20ms_total_variation_mm=float(abs(np.diff(position)).sum()),
                    opening_range_mm=[float(position.min()),float(position.max())])
            record["micro"]["signed_opening_errors_mm"]=gap("jaw_mm").tolist()
            record["micro"]["finger_q_rmse_mm"]=float(np.sqrt(np.mean(np.r_[gap("finger1_mm"),gap("finger2_mm")]**2)))
            record["micro"]["finger_v_rmse_m_s"]=float(np.sqrt(np.mean(np.r_[gap("finger1_v_m_s"),gap("finger2_v_m_s")]**2)))
        response.append(record)
    retention=[dict(source=r["source"],side=r["side"],metric=r["metric"],h=int(r["h"]),mode=r["mode"],available=int(r["available"]),
                    p95=float(r["p95"]) if r["p95"] else None,nonfinite=int(r["nonfinite"])) for r in long
               if r["metric"] in ("tcp_mm","jaw_mm") and r["scored"]!="0"]
    slopes={}
    for channel in ("17","22"):
        t=[r for r in directions if r["channel"]==channel and r["interpretable"]=="True"]
        slopes[channel]=dict(usable=len(t),sign_agree=sum(np.sign(float(r["actual_mm"]))==np.sign(float(r["pred_mm"])) for r in t).item() if t else 0)
    return dict(meta=meta,hold_first_actual_commands=response,retention=retention,directions=slopes,
        nonfinite_response_coordinates=sum(int(r["nonfinite_coordinates"]) for r in first),
        nonfinite_micro_coordinates=sum(int(r["nonfinite_coordinates"]) for r in micro),
        long_nonfinite_metric_windows=sum(int(r["nonfinite"]) for r in long))


def main():
    result={p.name:index_node(p) for p in sorted(ROOT.iterdir()) if p.is_dir() and (p/"score.json").exists()}
    path=ROOT/"node_summary.json"
    tmp=path.with_suffix(".pending")
    tmp.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    tmp.replace(path)
    for k,v in result.items():
        severe=[a for a in v["hold_first_actual_commands"] if a["actor"]=="u0"]
        def score(source,mode):
            return [round(r["p95"],2) for r in v["retention"] if r["source"]==source and r["h"]==32 and r["mode"]==mode and r["metric"]=="tcp_mm"]
        print(k,"hold jaw abs", [round(abs(a["jaw_mm"]),2) for a in severe],"repeat",[round(a["jaw_repeat_difference_mm"],5) for a in severe],
            "H32 TCP grip",score("recovery_b_grip_challenge_r1","two_finger"),"multi",score("lanes_modes_v1","two_finger"),
            "micro fingerVel RMS",[round(a["micro"]["finger_v_rmse_m_s"],3) for a in severe if "micro" in a])


if __name__=="__main__":
    main()
