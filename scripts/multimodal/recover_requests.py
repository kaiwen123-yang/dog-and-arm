"""Recover pre-clamp requests for cases run with the initial bounded inference endpoint."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.multimodal.actor import OnlinePolicy


def inspect(case):
    result=json.loads(case.read_text())
    episode=Path(result["raw_episode"])
    meta=json.loads((episode/"metadata.json").read_text())
    actions=np.load(episode/"action_clipped.npy")
    recorded=np.load(episode/"action_raw.npy")
    live=meta.get("policy_request_recording")=="online_preclamp_head"
    if live:
        requests=recorded
    else:
        policy=OnlinePolicy.from_checkpoint(result["checkpoint"],"cpu")
        policy.reset(meta["task_text"])
        def load(key):
            return np.load(episode/f"{key}.npy",mmap_mode="r")
        rgb,depth,valid,idx,it,t,proprio,prev=map(load,
            ("rgb","depth","depth_valid","image_index","image_t","t","proprio","previous_action"))
        requests=[]
        for k in range(len(actions)):
            j=idx[k]
            age=float(np.float32(t[k]-it[j]))
            requests.append(policy.step(rgb[j].copy(),depth[j].copy(),valid[j].copy(),
                                        proprio[k],prev[k],image_age_s=age,return_raw=True))
        requests=np.asarray(requests,dtype=np.float32)
    clipped=np.clip(requests,-1.,1.)
    error=float(np.max(np.abs(clipped-actions)))
    if not np.array_equal(clipped,actions):
        raise ValueError(f"Execution differs from head replay in {case}, max delta {error}")
    if not live:
        np.save(episode/"action_head_preclip.npy",requests,allow_pickle=False)
    info=dict(case_id=result["case_id"],physics_steps=result["physics_steps"],policy_calls=len(actions),
              preclamp_source="recorded online" if live else "recomputed on the same CPU checkpoint, observations and previous executed actions",
              preclamp_array="action_raw.npy" if live else "action_head_preclip.npy",
              raw_array_semantics="unbounded head" if live else "public bounded policy request",
              max_clipped_execution_difference=error,channel_values_clipped=int(np.count_nonzero(requests!=clipped)))
    (episode/"requested_action_provenance.json").write_text(json.dumps(info,indent=2)+"\n")
    return info


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cases",type=Path,nargs="+",required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    torch.set_num_threads(1)
    files=[f for root in a.cases for f in sorted(root.glob("*/result.json"))]
    if not files:
        raise ValueError("There are no completed, scored episodes")
    rows=[inspect(f) for f in files]
    a.out.write_text(json.dumps(rows,indent=2)+"\n")
    print(json.dumps(dict(cases=len(rows),max_error=max(x["max_clipped_execution_difference"] for x in rows))))
