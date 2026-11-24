"""Decompose the measured relapse around the sole passing block on the fixed two-finger windows."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import numpy as np
import torch
from scripts.b0 import dynamics_h32_pilot as pilot
from scripts.b0.joint_adapt import ck
from scripts.b0.joint_validation import Validation
from scripts.b0.joint_collection import OUT
from scripts.b0.score_temporal_wm import csv_file

@torch.no_grad()
def main():
    run=pilot.build("experiment")
    val=Validation(run)
    torch.set_float32_matmul_precision("highest")
    rows=[]
    for n in (0,840,850,860,990):
        run.dyn.load_state_dict(torch.load(ck(n),weights_only=False,map_location="cpu")["dyn"])
        run.dyn.eval()
        for name,eps in val.long.items():
            for side in ("pull","push"):
                windows=[(e,int(t)) for e in eps if e.side==side for t in e.starts(32) if e.modes[t]=="two_finger"]
                assert len(windows)<=512
                truth=torch.stack([e.state[t:t+33] for e,t in windows])
                act=torch.stack([e.action[t:t+32] for e,t in windows])
                ctx=torch.stack([e.context for e,t in windows])
                q=truth[:,0]
                r=run.rep.represent(q)
                a=run.rep.extract_aux_state(q)
                for j in range(1,33):
                    a,r=run.dyn(r,act[:,j-1],a,ctx)
                    if j not in (1,7,16,32):continue
                    y=run.rep.reconstruct_full_state(a,r)
                    x=truth[:,j]
                    def tcp(base,joints):return run.rep.tcp_pose(base[:,:7],joints[:,7:31])[0]
                    real,mixed,pred=tcp(x,x),tcp(y,x),tcp(y,y)
                    rec=dict(n=n,source=name,side=side,horizon=j,windows=len(windows))
                    for key,t in dict(total_tcp_mm=(pred-real).norm(dim=1)*1000,base_mm=(mixed-real).norm(dim=1)*1000,
                        joint_mm=(pred-mixed).norm(dim=1)*1000,j2_q_rad=y[:,24]-x[:,24],j2_v_rad_s=y[:,54]-x[:,54]).items():
                        ar=t.double().cpu().numpy()
                        rec[key+"_mean"]=float(np.mean(ar))
                        rec[key+"_abs_p95"]=float(np.percentile(np.abs(ar),95))
                    rows.append(rec)
    csv_file(OUT/"adapt/relapse_components.csv",rows)

if __name__=="__main__":
    main()
