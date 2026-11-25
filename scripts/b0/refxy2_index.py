"""Index newly collected valid transitions and real optimizer charges by retained node."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from scripts.b0 import refxy2_state as s


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def index(mode,end):
    parent=s.io.read(s.PARENT)
    goal=s.io.read(s.node(mode,end))
    refs=[Path(f) for f in s.config(mode)["reference_paths"]]
    labels=[]
    for ref in refs:
        m=s.io.read(ref/"metadata.json")
        n=int(np.load(ref/"valid_full_interval.npy").sum())
        tags=np.load(ref/"substeps/phase.npy",mmap_mode="r")[:10*n:10]
        phases=np.array([ref.name+"/"+p for p in m["phases"]])[tags]
        labels.extend([*phases,phases[-1]])
    names,ids=np.unique(labels,return_inverse=True)
    counts=np.zeros(len(names),dtype=np.int64)
    terms=truncs=0
    light=s.LIGHT/mode
    all_rows=rows(light/"collection.jsonl")
    optrows=[r for r in rows(s.LIGHT/"optimizer_cost.jsonl") if r["mode"]==mode]
    snapshots=[]
    for u in goal["delta_nodes"]:
        rec=s.io.read(s.node(mode,u))
        with np.load(s.state_dir(mode,u)/"replay_delta.npz") as z:
            for tick in range(rec["previous_clock"],rec["clock"]):
                valid=z[f"{tick}/valid"]
                times=z[f"{tick}/motion_time"]
                counts += np.bincount(ids[times[valid]],minlength=len(names))
                terms += int((z[f"{tick}/terminated"] & valid).sum())
                truncs += int((z[f"{tick}/truncated"] & valid).sum())
        assert int(counts.sum())==rec["valid"]-parent["valid"]
        if u in (1,10,50,100,200,500,1000):
            snapshots.append(dict(node=u,clock=rec["clock"],valid=int(counts.sum()),simulated=rec["simulated"]-parent["simulated"],
                terminal_valid=terms,truncated_valid=truncs,reference_phase_valid={n:int(c) for n,c in zip(names,counts)}))
    # Recover the last retained version of each physical tick when an attempt was rolled back.
    physical={r["clock"]:r for r in all_rows if parent["clock"]<r["clock"]<=goal["clock"]}
    assert len(physical)==goal["clock"]-parent["clock"]
    assert sum(r["valid_transitions"] for r in physical.values())==goal["valid"]-parent["valid"]
    retained={k:v-parent["steps"][k] for k,v in goal["steps"].items()}
    charged={k:sum(r["cost"][k] for r in optrows) for k in retained}
    coverage=dict(nodes=snapshots,
        retained_starts_by_reference=dict(zip([p.name for p in refs],np.sum([r["starts_per_motion"] for r in physical.values()],axis=0).tolist())),
        retained_dual_valid_pull_push=np.sum([r["physical_contact_counts"]["dual_entire_valid"] for r in physical.values()],axis=0).tolist(),
        retained_valid_pull_push=np.sum([r["physical_contact_counts"]["valid"] for r in physical.values()],axis=0).tolist(),
        actual_collected=sum(r["valid_transitions"] for r in all_rows), actual_simulated=sum(r["simulated_lane_intervals"] for r in all_rows))
    s.io.write(light/f"coverage_{end:06}.json",coverage)
    s.io.write(light/"manifest.json",dict(experiment="refxy2_pair_s0_v1",mode=mode,method=s.METHOD[mode],
        execution_recipe=s.config(mode)["execution_recipe"],latest_node=end,start=s.io.read(s.node(mode,0)),end=goal,
        actual=charged,retained=retained,rollback={k:charged[k]-retained[k] for k in charged},
        effective_transitions=goal["valid"]-parent["valid"],training_clock="250us physics / 2ms servo / 20ms policy",
        resume_cwd=str(Path.cwd()),resume_format="refxy2_delta_v1",source_registration="2bbb9fec44b8014b094ac3aa065d11e413e17056",
        coverage=f"coverage_{end:06}.json",migration="migration.json",first_update="first_retained_update_observation.json",
        immutable_nodes=[0,*goal["delta_nodes"]],unqualified_bilateral_return=None))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=s.METHOD)
    p.add_argument("end",type=int)
    a=p.parse_args()
    index(a.mode,a.end)
