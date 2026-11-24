"""Apply the registered nominal first event to archived training-identity physics."""
import csv
import json
from pathlib import Path
import numpy as np
from learning.b0.physics import make_model
from scripts.b0.training_entry_response import OUT, RAW, judge_trace, dump


def main():
    roots=[RAW, RAW.parent/"response_requery_v1", RAW.parent/"response_requery_final_v1"]
    model=make_model()
    corrected={}
    counts={}
    for root in roots:
        lookup={}
        changed=0
        for receipt in sorted(root.glob("*/receipt.json")):
            rec=json.loads(receipt.read_text())
            if rec.get("rejected"):
                continue
            folder=receipt.parent
            state=np.load(RAW/folder.name/"start.npz")
            with np.load(folder/"substeps.npz") as f:
                sub=dict(f)
            ev,judges=judge_trace(model,rec["row"],state["qpos"],state["qvel"],sub)
            changed+=int((ev!=sub["event_phase"]).sum())
            if not np.array_equal(ev,sub["event_phase"]):
                sub["event_phase"]=ev
                temp=folder/"event_refresh.npz"
                np.savez_compressed(temp,**sub)
                temp.replace(folder/"substeps.npz")
            rec.update(judges=judges,formal_clock_start=rec["row"]["formal_start"],
                       formal_event_init="frozen nominal segment first phase and fresh judge counters")
            dump(receipt,rec)
            for b,(actor,label,ch,delta) in enumerate(rec["labels"]):
                key=folder.name,actor,label,ch,delta
                f=judges[b]["failure"] or {}
                lookup[key]=int(ev[0,b,0]),f.get("first_failure_substep")
        counts[root.name]=dict(trajectories=len(list(root.glob("*/receipt.json"))),changed_phase_ticks=changed)
        corrected[root.name]=lookup
    data=json.loads((OUT/"collection.json").read_text())
    data["entries"]=[json.loads((RAW/r["row"]["id"]/"receipt.json").read_text()) for r in data["entries"]]
    dump(OUT/"collection.json",data)
    for path in [*OUT.glob("response_*.csv"),OUT/"previous_u200.csv"]:
        root=roots[2] if path.stem=="response_actual_u200" else roots[1] if path.stem.startswith("response_actual_") else RAW
        with path.open() as f:
            rows=list(csv.DictReader(f))
        for r in rows:
            key=(r["start"],r["actor"],r["branch"],int(r["channel"]),float(r["requested_delta"]))
            r["event_phase0"],r["event_first_failure"]=corrected[root.name][key]
        with path.open("w") as f:
            w=csv.DictWriter(f,rows[0]); w.writeheader();w.writerows(rows)
    dump(OUT/"event_clock_receipt.json",dict(roots=counts,
        semantics="Nominal event judge starts at its registered segment origin on a measured training/validation state. Training clock and physical solver history remain those of that trajectory. All arrays tagged -1 after event termination.",
        physics_reintegrated=False,updates=0,formal_scores_changed=0))


if __name__=="__main__":
    main()
