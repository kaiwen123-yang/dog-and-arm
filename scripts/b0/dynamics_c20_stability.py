"""Review interval-wide gradients together with same-coordinate physical probes before extending C20."""
import argparse
import json
from pathlib import Path

import numpy as np
from scripts.b0.dynamics_c20_pair import OUT, load_registration, write
from scripts.b0 import train_temporal_pair as prior


def metrics(name):
    return json.loads(name.read_text())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm",choices=("C20","rebase"),required=True)
    p.add_argument("--node",choices=(50,200,1000),type=int,required=True)
    p.add_argument("--disposition",choices=("stable_on_fixed_probes","investigate"),required=True)
    p.add_argument("--reason",required=True)
    args=p.parse_args()
    info=load_registration()
    previous={50:0,200:50,1000:200}[args.node]
    old_path=OUT/f"{args.arm}_fixed_probe_{previous:06}.json"
    new_path=OUT/f"{args.arm}_fixed_probe_{args.node:06}.json"
    before,after=metrics(old_path),metrics(new_path)
    baseline=metrics(OUT/f"{args.arm}_fixed_probe_000000.json")
    gradroot=OUT
    gradfile=f"{args.arm}_gradients_{args.node:06}.json"
    if info["original_2ms"] and args.arm=="C20":
        gradroot,gradfile=prior.OUT,f"C20_review_{args.node:06}.json"
    stats=metrics(gradroot/gradfile)
    if (stats["first"],stats["last"]) != (previous+1,args.node):
        raise ValueError("Incomplete interval-wide gradient report")
    rows=[]
    for horizon,items in after.items():
        for source,values in items.items():
            keys=("loss","mean_tcp_error_mm","finger_q_rms_mm","finger_v_rms_m_s",
                  "state_vjp_l2","first_processed_action_vjp_l2","all_processed_action_vjp_l2")
            def subset(table):
                return {k:table[horizon][source][k] for k in keys}
            rows.append(dict(horizon=horizon,source=source,initial=subset(baseline),
                             previous=subset(before),current=subset(after)))
    if not all(np.isfinite(v) for row in rows for block in ("initial","previous","current") for v in row[block].values()):
        raise FloatingPointError("Nonfinite physical probe")
    result=dict(arm=args.arm,node=args.node,previous=previous,disposition=args.disposition,interpretation=args.reason,
                same_arm_original_units=True,gradient_interval=stats,group_measurements=rows)
    write(OUT/f"{args.arm}_stability_{args.node:06}.json",result,exclusive=True)
    print(json.dumps(dict(arm=args.arm,node=args.node,gradient_interval=stats,disposition=args.disposition)))


if __name__=="__main__":
    main()
