"""Index actual frozen cohorts and every charged WM source draw."""
import argparse
from collections import Counter
from pathlib import Path
import csv,json
import numpy as np
import torch
from learning.b0.contact_warp import PHASES
from scripts.b0.joint_collection import OUT,RAW
from scripts.b0.dynamics_h32_pilot import read,write

def main():
    groups=[]
    for split in ("train","development"):
        states=torch.load(RAW/"collection"/split/"state.pt",map_location="cpu",weights_only=False)
        for index,(td,starts) in enumerate(states["chunks"]):
            for h in (1,7):
                i,t=starts[h].T
                phase=td["draw_phase"][i,t].tolist()
                mode=td["draw_mode"][i,t].tolist()
                side=td["sim_ctx"][i,t,0].int().tolist()
                ids=td["episode"][i,t]
                term=td["terminated"][i,t+h-1]
                keys=list(zip(side,phase,mode))
                for s,p,m in sorted(set(keys)):
                    mask=torch.tensor([k==(s,p,m) for k in keys])
                    groups.append(dict(split=split,cohort=index,h=h,side=("pull","push")[s],phase=PHASES[p],
                        mode=("free","other_contact","two_finger","loss_or_slip","release")[m],
                        starts=int(mask.sum()),distinct_episodes=int(ids[mask].unique().numel()),terminal_last=int(term[mask].sum())))
    with (OUT/"collection/eligible_windows.csv").open("w") as f:
        w=csv.DictWriter(f,groups[0],lineterminator="\n");w.writeheader();w.writerows(groups)
    updates=[json.loads(line) for p in sorted((OUT/"adapt").glob("node_*/updates.jsonl")) for line in p.read_text().splitlines()]
    counts=Counter()
    for row in updates:
        for source,rec in row["sources"].items():
            counts[(row["h"],source)]+=rec["samples"]
    readback=[dict(h=h,source=s,samples=n) for (h,s),n in sorted(counts.items())]
    draws=Counter()
    for row in updates:
        draws.update({f"H{row['h']}/{k}":v for k,v in row["sources"]["online"]["side_phase_mode"].items()})
    write(OUT/"adapt/draw_accounting.json",dict(persisted_batches=len(updates),draws_by_horizon_and_source=readback,
        canonical_examples=len(updates)*256,boundary_h1=sum(r["boundary_h1"] for r in updates),online_strata=draws,
        preclip_p95=np.percentile([r["preclip"] for r in updates],95),preclip_max=max(r["preclip"] for r in updates),
        clipped=sum(r["clipped"] for r in updates),discarded=read(OUT/"adapt/execution_accounting.json"),
        charged_examples_extra="One lost logger step H7: 192 online, 32 native, 32 Warp, 0 boundary H1."))
    return len(updates)

if __name__=="__main__":
    print(main())
