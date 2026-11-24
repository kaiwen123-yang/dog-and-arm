"""Run the originally registered ten formal simulated cases for a frozen policy."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import argparse
from unittest.mock import patch
import torch
from scripts.b0 import dynamics_h32_pilot as pilot, dynamics_h32_score as scoring
from scripts.b0.joint_collection import OUT,RAW

def evaluate(n):
    (OUT/"h32").mkdir(parents=True,exist_ok=True)
    path=(pilot.RAW/"h32"/"experiment"/"checkpoint_000000.pt" if n==0 else RAW/"main"/f"checkpoint_{n:06}.pt")
    if n==0:
        source=torch.load(pilot.SHARED/"first.pt",map_location="cpu",weights_only=False)
        candidate=torch.load(path,map_location="cpu",weights_only=False)
        for k,t in source["actor"].items():
            assert torch.equal(t,candidate["actor"][k])
    tag=f"seed0_u{n}"
    with patch.multiple(scoring,OUT=OUT,RAW=RAW,nodes=lambda:[(tag,"seed0",n)],
                        check_u0=lambda:path,ck=lambda arm,u:path):
        scoring.formal(tag)
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("update",type=int)
    evaluate(p.parse_args().update)
