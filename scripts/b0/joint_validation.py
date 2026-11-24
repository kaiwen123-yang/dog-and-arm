"""Evaluate exact frozen long windows and every eligible held-out online start."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
from collections import defaultdict
from pathlib import Path
import numpy as np
import torch
from scripts.b0.dynamics_h32_pilot import DEVICE,read,write
from scripts.b0.joint_collection import RAW,OUT
from scripts.b0.score_temporal_wm import csv_file,score_long,validation_episodes
from learning.b0.contact_warp import PHASES

class Validation:
    def __init__(self,run):
        self.long={}
        for name in ("grip","multimode"):
            folder=run.cfg["wm_data_recipe"]["sources"][name]["directory"]
            self.long[name]=validation_episodes(str(Path(folder).resolve()),run.model,run.rep,DEVICE)
        self.dev=torch.load(RAW/"collection/development/state.pt",weights_only=False,map_location=DEVICE)["chunks"]
        assert len(self.dev)==1

    @torch.no_grad()
    def score(self,run,directory):
        directory.mkdir(parents=True,exist_ok=True)
        previous=torch.get_float32_matmul_precision()
        torch.set_float32_matmul_precision("highest")
        run.dyn.eval()
        try:
            longs=[]
            for name,episodes in self.long.items():
                longs.extend(score_long(name,episodes,run.model,run.rep,run.dyn,DEVICE))
            if any(i["nonfinite"] for i in longs):
                raise FloatingPointError("Nonfinite registered autoregressive probe")
            csv_file(directory/"long.csv",longs)
            vals={f"{r['side']}_{r['source']}":r["p95"] for r in longs if (r["h"],r["mode"],r["metric"])==(32,"two_finger","tcp_mm")}
            counts={f"{r['side']}_{r['source']}":r["scored"] for r in longs if (r["h"],r["mode"],r["metric"])==(32,"two_finger","tcp_mm")}
            rows=[]
            data,starts=self.dev[0]
            for h in (1,7):
                sums=defaultdict(lambda:np.zeros(6,np.float64))
                learner=run.learners[h]
                for ij in starts[h].split(256):
                    i,t=ij.T
                    ix=t[:,None]+torch.arange(h,device=DEVICE)
                    x=torch.cat([data["state"][i[:,None],ix],data["next_state"][i,ix[:,-1]][:,None]],1)
                    a=data["action"][i[:,None],ix]
                    a=torch.cat([a,a[:,-1:]],1)
                    r=run.rep.represent(x)
                    aux=run.rep.extract_aux_state(x)
                    pred,pa=learner._rollout(r[:,0],a,aux[:,0],data["sim_ctx"][i,t])
                    p=run.rep.reconstruct_full_state(pa[:,-1],pred[:,-1])
                    delta=p-x[:,-1]
                    group=torch.stack((data["sim_ctx"][i,t,0].long(),data["draw_phase"][i,t],data["draw_mode"][i,t]),dim=1)
                    for key in [None,*torch.unique(group,dim=0)]:
                        m=torch.ones_like(i,dtype=torch.bool) if key is None else (group==key).all(1)
                        loss,_=learner._compute_losses(pred[m],pa[m],r[m,1:],aux[m,1:])
                        n=int(m.sum())
                        name="all" if key is None else "/".join([("pull","push")[int(key[0])],PHASES[int(key[1])],("free","other_contact","two_finger","loss_or_slip","release")[int(key[2])]])
                        dq,dv=delta[m,24].double(),delta[m,54].double()
                        sums[name]+=np.array([n,float(loss)*n,float(dq.square().sum()),float(dv.square().sum()),float(dq.sum()),float(dv.sum())])
                for group,(n,loss,qq,vv,q,v) in sums.items():
                    row=dict(h=h,stratum=group,n=int(n),loss=loss/n,j2_q_rmse=(qq/n)**.5,j2_v_rmse=(vv/n)**.5,j2_q_bias=q/n,j2_v_bias=v/n)
                    rows.append(row)
                    if group=="all":
                        vals.update({f"H{h}_{k}":row[k] for k in ("loss","j2_q_rmse","j2_v_rmse")})
            csv_file(directory/"online.csv",rows)
            if not np.isfinite(list(vals.values())).all():
                raise FloatingPointError("Nonfinite held-out score")
            write(directory/"scores.json",dict(values=vals,long_counts=counts))
            return vals
        finally:
            torch.set_float32_matmul_precision(previous)
