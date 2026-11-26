"""Common native-forward H7 replay, opened only after C method selection."""
from functools import lru_cache
from pathlib import Path
import json

import numpy as np
import torch


class SharedForwardReplay:
    def __init__(self, run_root, device):
        self.device=torch.device(device)
        root=Path(run_root)/"C"
        if not (root/"selection.json").is_file():
            raise ValueError("Freeze C method comparison before training on its added native transitions")
        self.files=[]
        self.weights=[]
        for ledger in sorted((root/"CF32").glob("seed*/applications.jsonl")):
            # Repeated optimizer draws after recovery are additional actual physics and are identified separately.
            for line in ledger.read_text().splitlines():
                record=json.loads(line)
                path=Path(record["shared_native_replay"])
                with np.load(path,allow_pickle=False) as data:
                    mask=data["valid"]
                    if np.any(np.diff(mask.astype(np.int8),axis=1)>0):
                        raise ValueError(f"{path}: H7 windows may not cross a terminal")
                    length=mask.sum(1)
                count=int(np.maximum(length-6,0).sum())
                if count:
                    self.files.append(path)
                    self.weights.append(count)
        self.count=int(np.sum(self.weights))
        self.probabilities=np.asarray(self.weights,dtype=float)/self.count if self.count else None

    @lru_cache(maxsize=4)
    def load(self, file_id):
        with np.load(self.files[file_id],allow_pickle=False) as source:
            d={key:source[key] for key in source.files}
        windows=[]
        by_slot={}
        for slot,mask in enumerate(d["valid"]):
            indices=np.flatnonzero(d["slot"]==slot)
            if not np.array_equal(d["tick"][indices],np.arange(mask.sum())):
                raise ValueError(f"{self.files[file_id]}: mismatched native execution order")
            by_slot[slot]=indices
            windows.extend((slot,tick) for tick in range(max(0,len(indices)-6)))
        return d,windows,by_slot

    def sample(self, batch_size, rng):
        """Each H7 start has equal marginal probability. Up to four file draws amortize I/O."""
        if not self.count or batch_size<1:
            raise ValueError("No positive H7 replay batch available")
        batch={k:[] for k in ("p","o","a","prev","prev_contact","contact","vision","fresh","history","previous_history")}
        for group in np.array_split(np.arange(batch_size),min(4,batch_size)):
            file_id=int(rng.choice(len(self.files),p=self.probabilities))
            d,windows,by_slot=self.load(file_id)
            for idx in rng.integers(0,len(windows),size=len(group)):
                slot,tick=windows[int(idx)]
                seq=by_slot[slot]
                prior=np.concatenate((d["previous_history"][slot],d["action"][seq]),axis=0)
                proprio=np.concatenate((d["p_history"][slot],d["p"][seq]),axis=0)
                last=tick+9
                batch["history"].append(proprio[tick:last+1])
                batch["previous_history"].append(prior[tick:last+1])
                batch["p"].append(proprio[last:last+8])
                batch["prev"].append(prior[last:last+8])
                # The final boundary is a successor with no action/contact label in this window.
                ix=seq[tick:tick+7]
                batch["a"].append(np.concatenate((d["action"][ix],np.zeros((1,23),np.float32))))
                batch["contact"].append(np.concatenate((d["contact"][ix],np.zeros((1,3),np.float32))))
                before=seq[tick-1] if tick else None
                for out,first,column in (("o","object0","o"),("vision","vision0","vision"),("prev_contact","contact0","contact")):
                    v=d[first][slot] if before is None else d[column][before]
                    batch[out].append(np.concatenate((v[None],d[column][ix])))
                if before is not None:
                    fresh0=d["fresh"][before]
                elif "fresh0" in d:
                    fresh0=d["fresh0"][slot]
                else:
                    # Early MM03 batches store the absolute time of the first actual successor.
                    anchor_tick=round(float(d["clock"][seq[0]])/.02)-1
                    fresh0=anchor_tick%5==0
                batch["fresh"].append(np.r_[fresh0,d["fresh"][ix]].astype(bool))
        return {k:torch.as_tensor(np.stack(values),device=self.device) for k,values in batch.items()}
