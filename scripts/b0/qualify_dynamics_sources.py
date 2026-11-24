"""Validate the regenerated Warp sources and count their independent starts and usable windows."""
import json
from pathlib import Path

import numpy as np
import yaml

OUT = Path("results/b0/standard_dynamics_20261124")
RAW = Path("results/raw_large/b0/dynamics_20261124")
OLD = Path("results/b0/standard_temporal_20261124")
CFG = Path("config/b0/standard_dynamics_v1.yaml")


def read(path):
    return json.loads(path.read_text())


def windows(valid, failure):
    if (np.diff(valid.astype(np.int8),axis=0) > 0).any():
        raise ValueError("A lane resumed after a missing/terminal transition")
    if (valid[1:] & (failure[:-1] != 0)).any():
        raise ValueError("Replay crossed a physical terminal")
    lengths = valid.sum(0)
    return dict(lanes=int(valid.shape[1]), nonempty=int((lengths>0).sum()),
                h1=int(lengths.sum()), h7=int(np.maximum(lengths-6,0).sum()),
                h32=int(np.maximum(lengths-31,0).sum()), terminal_h1=int((valid & (failure>0)).sum()))


def verify():
    cfg=yaml.safe_load(CFG.read_text())
    sources=cfg["wm_data_recipe"]["sources"]
    dt=cfg["physics_dt"]
    n=round(.02/dt)
    assert n==80
    groups={}
    def cohort(name):
        root=Path(sources[name]["directory"])
        spec=read(root/"registration.json")
        clock=spec["contact_clock"]
        assert (clock["physics_dt"],clock["substep_coeff"],clock["physical_prefix_steps"])==(dt,(n+1)/(2*n),10*n)
        rows=read(root/"cohorts.json")
        assert spec["allocation"]==[[r["split"],r["seed"]] for r in rows]
        prior=Path("results/b0")/("lanes_modes_v1" if name=="multimode" else "recovery_b_grip_challenge_r1")
        assert spec["allocation"]==read(prior/"registration.json")["allocation"]
        receipts=[]
        for r in rows:
            d=Path(r["path"])
            v=np.load(d/"valid.npy")
            f=np.load(d/"first_fail_substep.npy")
            load=np.load(d/"sub_finger_load_N.npy",mmap_mode="r")
            force=np.load(d/"sub_door_robot_force_N.npy",mmap_mode="r")
            assert load.shape==(*v.shape,n,2) and force.shape==(*v.shape,n,3)
            assert v.shape==(spec["steps"],spec["worlds"])
            assert not (f>n).any() and np.isfinite(load).all() and np.isfinite(force).all()
            r0=dict(split=r["split"],seed=r["seed"],prefix_accepted=r["prefix_accepted"],**windows(v,f))
            assert r0["h1"]==r["valid"]
            receipts.append(r0)
        return receipts
    for name in ("grip","multimode"):
        groups[name]=cohort(name)
    spec=read(Path(sources["response"]["registration"]))
    original=read(OLD/"registration.json")
    assert spec["starts"]==original["starts"] and spec["prefix_ticks"]==10*n
    groups["response"]=[]
    for row in spec["starts"]:
        d=Path(sources["response"]["raw"])/row["id"]
        receipt=read(d/"receipt.json")
        assert receipt["row"]==row
        item=dict(start=row["id"],split=row["split"],side=row["side"],source_trajectory=row["path"],
                  prefix_attempts=len(receipt["attempts"]),rejected=receipt.get("rejected",False))
        if not item["rejected"]:
            with np.load(d/"dynamics.npz") as dyn, np.load(d/"substeps.npz") as sub:
                valid,fail=dyn["valid"],dyn["fail"]
                phase=sub["training_phase"]
                assert phase.shape==(32,n) and sub["finger_load_N"].shape==(*valid.shape,n,2)
                assert not (fail>n).any() and np.array_equal(phase[:,::8].repeat(8,axis=1),phase)
                legal=np.array([label[1]!="repeat" for label in receipt["labels"]])
                item.update(windows(valid[:,legal],fail[:,legal]))
                item["all_branch_valid_h1"]=int(valid.sum())
        groups["response"].append(item)
    tables={}
    for name,rows in groups.items():
        tables[name]={}
        for split in sorted({r["split"] for r in rows}):
            selected=[r for r in rows if r["split"]==split]
            tables[name][split]={k:sum(r.get(k,0) for r in selected) for k in
                ("lanes","nonempty","h1","h7","h32","terminal_h1")}
            tables[name][split]["cohorts_or_starts"]=len(selected)
    native=read(OLD/"native_wrist_draws_3.16.0.json")
    return dict(physics_id=cfg["training_physics_id"],clock=spec["contact_clock"],
        original_formal_backend="2 ms Warp and native MuJoCo 3.3.0",
        native_source_qualification="Unchanged native training trajectories and split, see archived actual-draw saturation audit.",
        native_actual_draw_audit=str(OLD/"native_wrist_draws_3.16.0.json"),
        native_actual_draw_fields=list(native), source_totals=tables,rows=groups,
        validation_use="model scoring only",repeats_excluded=True,
        rules="H1 includes a finite complete first failed policy interval, H7 and H32 stop at lane termination. Records after the first terminal are diagnostics.")


if __name__=="__main__":
    result=verify()
    (OUT/"data_qualification.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps(result["source_totals"],indent=2))
