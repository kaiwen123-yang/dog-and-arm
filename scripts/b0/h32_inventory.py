"""Inspect saved seed0 recovery checkpoints, resumable cohort boundaries and raw arrays."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch


def main(a):
    records=[]
    for run in a.runs:
        if not run.is_dir():
            raise FileNotFoundError(run)
        raw=Path("results/raw_large/b0")/run.name
        entry=dict(run=str(run.resolve()),weights=[],arrays=None)
        for path in sorted(run.rglob("*.pt")):
            payload=torch.load(path,weights_only=False,map_location="cpu")
            keys=list(payload)
            if "actor" in payload:
                values=payload["actor"]
                norms=[k for k in values if "normalizer" in k]
                finite=all(torch.isfinite(values[k]).all().item() for k in norms)
            else:
                norms=[]
                finite=None
            entry["weights"].append(dict(path=str(path.resolve()),bytes=path.stat().st_size,keys=keys,
                updates=payload.get("updates"),collected=payload.get("collected"),
                actor_normalizer_tensors=len(norms),actor_normalizers_finite=finite,
                joint_resume=all(k in payload for k in ("actor","critic","dyn","optimizers","numpy_rng","cpu_rng","gpu_rng","replay","simulated")),
                optimizer_count=len(payload.get("optimizers",[])),replay_cohorts=len(payload.get("replay",[]))))
            del payload
        if raw.is_dir():
            files=sorted(raw.rglob("*.npy"))
            types={}
            size=0
            for path in files:
                arr=np.load(path,allow_pickle=False,mmap_mode="r")
                if arr.size:
                    arr.flat[0]
                    arr.flat[-1]
                size+=path.stat().st_size
                types[str(arr.dtype)]=types.get(str(arr.dtype),0)+1
            entry["arrays"]=dict(path=str(raw.resolve()),files=len(files),bytes=size,dtypes=types,
                                 inspection="memory mapped header, first and last scalar of each nonempty array")
        records.append(entry)
    a.output.parent.mkdir(exist_ok=True,parents=True)
    with a.output.open("x") as f:
        json.dump(records,f,indent=2)
        f.write("\n")
    print(f"{len(records)} runs; {sum(len(r['weights']) for r in records)} loadable weight files")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs",type=Path,nargs="+",required=True)
    p.add_argument("--output",type=Path,required=True)
    main(p.parse_args())
