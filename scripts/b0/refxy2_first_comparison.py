"""Reduce first-collection and first-retained-update arrays on identical row order."""
import json
from pathlib import Path
import numpy as np

ROOT=Path("results/b0/refxy2_pair_20261125")


def read(p):
    return json.loads(p.read_text())


def stat(arr):
    a=np.asarray(arr).astype(np.float64)
    return dict(max_abs=float(np.max(abs(a))),l2=float(np.linalg.norm(a.ravel())),
                nonzero=int(np.count_nonzero(a)),elements=int(a.size))


def compare(a,b):
    assert a.shape==b.shape and a.dtype==b.dtype
    exact=np.array_equal(a,b)
    d=a.astype(np.float64)-b.astype(np.float64)
    return dict(exact=bool(exact),different_elements=int(np.count_nonzero(d)),max_abs=float(np.max(abs(d))))


def main():
    result={}
    for label in ("first_collection_observation","first_retained_update_observation"):
        z,m=(read(ROOT/s/(label+".json")) for s in ("zero","measured"))
        row={"branches":{}, "paired_arrays":{}}
        if label=="first_collection_observation":
            keys=("frame","prefix","noisy_history","original_goal","raw_before_noise","applied","physical")
        else:
            keys=sorted(k for k in z["array_metadata"] if k.startswith("draw_") or k.startswith("sample_"))
            keys+=["imagined_initial_goal540","imagined_initial_noisy_history","first_imagined_clipped_command"]
        with np.load(z["arrays"]) as a,np.load(m["arrays"]) as b:
            for key in keys:
                row["paired_arrays"][key]=compare(a[key],b[key])
            if label=="first_retained_update_observation":
                # Later physical ticks can diverge before the first Ratio threshold.
                # An inherited row at the same sampled index must remain exact.
                parent_clock=read(ROOT/"zero"/"node_000000.json")["clock"]
                ij=a["draw_actor"]
                old=ij[:,1]<parent_clock
                row["actor_samples_by_origin"]=dict(parent_clock=parent_clock,
                    sampled_inherited=int(old.sum()),sampled_after_restore=int((~old).sum()),
                    fields={})
                for key in ("sample_state","sample_history","sample_prev_action","imagined_initial_goal540",
                            "imagined_initial_noisy_history","first_imagined_clipped_command"):
                    left,right=a[key],b[key]
                    delta=np.abs(left-right).reshape(len(ij),-1).max(1)
                    row["actor_samples_by_origin"]["fields"][key]={
                        "different_inherited":int(np.count_nonzero(delta[old])),
                        "different_after_restore":int(np.count_nonzero(delta[~old])),
                        "maximum_abs_inherited":float(delta[old].max(initial=0)),
                        "maximum_abs_after_restore":float(delta[~old].max(initial=0))}
            for name,file,info in (("zero",a,z),("measured",b,m)):
                side={k:info[k] for k in ("statistics_before","statistics_after")}
                if label=="first_retained_update_observation":
                    horizon=info["horizon_calls"]
                    assert len(horizon)==32 and info["draw_count"]==11
                    assert [q["step"] for q in horizon]==list(range(32))
                    side.update(grad_before_global_clip=stat(file["gradient_before_clip"]),
                                grad_after_global_and_value_clip=stat(file["gradient_after_clip"]),
                                new_exp_avg=stat(file["exp_avg_tail"]),new_exp_avg_sq=stat(file["exp_avg_sq_tail"]),
                                new_column_update=stat(file["weight_tail_after"]-file["weight_tail_before"]),
                                maximum_measured_feature_discrepancy=max(q["measured_max_error"] for q in horizon),
                                max_abs_feature=max(q["tail_abs_max"] for q in horizon),
                                connected_predicted_aux_steps=sum(q["aux_requires_grad"] for q in horizon),
                                adam_shared_step=info["adam_shared_step"])
                    updates=map(json.loads,(ROOT/name/"updates.jsonl").read_text().splitlines())
                    retained=next(r for r in updates if r["update"]==1)
                    side["full_actor_preclip_norm"]=retained["metrics"]["Policy/grad_norm"]
                row["branches"][name]=side
            if label=="first_retained_update_observation":
                assert row["branches"]["zero"]["new_column_update"]["nonzero"]==0
                assert row["branches"]["measured"]["maximum_measured_feature_discrepancy"]<1e-4
        result[label]=row
    target=ROOT/"first_update_paired_comparison.json"
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(target,flush=True)


if __name__=="__main__":
    main()
