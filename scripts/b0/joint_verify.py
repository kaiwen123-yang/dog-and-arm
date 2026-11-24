"""Reload the tightest pass, its two neighbours, and the endpoint in a fresh process."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import torch
from scripts.b0 import dynamics_h32_pilot as pilot
from scripts.b0.joint_adapt import ck
from scripts.b0.joint_collection import OUT,RAW
from scripts.b0.joint_validation import Validation

def main():
    run=pilot.build("experiment")
    validation=Validation(run)
    rows=[]
    for n in (840,850,860,980,990):
        st=torch.load(ck(n),weights_only=False,map_location="cpu")
        run.dyn.load_state_dict(st["dyn"])
        values=validation.score(run,RAW/"verify"/f"node_{n:06}")
        old=pilot.read(OUT/"adapt"/f"node_{n:06}"/"scores.json")["values"]
        diff={k:abs(old[k]-v) for k,v in values.items()}
        if max(diff.values())>1e-6:raise ValueError((n,diff))
        rows.append(dict(n=n,abs_differences=diff,max_abs=max(diff.values())))
    pilot.write(OUT/"adapt/independent_reload.json",dict(nodes=rows,independent_process=True,
        extra_WM_updates=0,extra_physics_steps=0))
if __name__=="__main__":main()
