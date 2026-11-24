"""Locate the measured states driving large normalized inputs, retaining data/terminal identity."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_model import ContactRepresentation, contact_state
from learning.b0.contact_replay import ContactEpisode
from learning.b0.contact_sources import warp_episodes
from learning.b0.physics import make_model
from scripts.b0.score_temporal_wm import BASE, OUT, RAW, REG, load_wm, validation_episodes


def labels(rep):
    xyz=list("xyz")
    joint=list(rep.fk.joint_names)
    return (["root_height_m"]+[f"body_down_{k}" for k in xyz]+[f"root_linear_{k}_m_s" for k in xyz]+
            [f"root_angular_{k}_rad_s" for k in xyz]+
            [j+("_m" if i>=22 else "_rad") for i,j in enumerate(joint)]+
            [j+("_m_s" if i>=22 else "_rad_s") for i,j in enumerate(joint)]+
            ["passive_hinge_rad","passive_hinge_rad_s"]+
            [f"{p}_{k}" for p in ("hinge_in_base_m","front_handle_in_tcp_m","back_handle_in_tcp_m","hinge_axis_in_tcp","face_normal_in_tcp") for k in xyz])


def summarise(rows,names,norm,device):
    if not rows:
        return {"n":0}
    rep=torch.cat([v[0] for v in rows])
    z=norm(rep).abs()
    maximum,at=z.max(0)
    values=rep[at,torch.arange(rep.shape[1],device=device)]
    steps=np.cumsum([0]+[len(row[0]) for row in rows])
    high=[]
    for j in maximum.argsort(descending=True)[:5].tolist():
        ix=int(at[j])
        row=np.searchsorted(steps[1:],ix,side="right")
        ident=rows[row][1]
        sample=rows[row][2][ix-steps[row]]
        physical_source=sample.tolist() if hasattr(sample,"tolist") else sample
        high.append(dict(channel=j,name=names[j],abs_z=float(maximum[j]),physical_value=float(values[j]),
            mean=float(norm._mean[0,j]),std=float(norm._std[0,j]),eps=float(norm.eps),
            physical_min=float(rep[:,j].min()),physical_max=float(rep[:,j].max()),
            p99_abs_z=float(torch.quantile(z[:,j],.99)),rows_abs_z_gt100=int((z[:,j]>100).sum()),
            source=ident,index=physical_source))
    vmax=z.amax(1)
    return dict(n=len(rep),p95_row_max_abs_z=float(torch.quantile(vmax,.95)),
        p99_row_max_abs_z=float(torch.quantile(vmax,.99)),rows_max_abs_z_gt100=int((vmax>100).sum()),
        nonfinite_rows=int((~rep.isfinite().all(-1)).sum()),largest_channels=high)


@torch.no_grad()
def main(history_root):
    device="cuda:0"
    model=make_model()
    rep=ContactRepresentation(model,device)
    wm,_=load_wm(BASE/"response_wm_v1/wm_000000.pt",model,rep,device)
    norm=wm.state_normalizer
    names=labels(rep)
    assert len(names)==75
    def push(groups,name,state,ident,indices):
        if len(state):
            groups.setdefault(name,[]).append((rep.represent(state),ident,indices))
    groups={}
    verified=0
    held=json.loads((BASE/"contact_s0_wm_held_r2/config.json").read_text())
    native_epochs=[ContactEpisode.read(history_root / row["path"],device) for row in held["sources"]]
    for ep in native_epochs:
        ix=np.flatnonzero(ep.valid)
        push(groups,"native_"+ep.split,ep.state[:-1][ix],ep.group,ix)
    native=torch.cat([r[0] for r in groups["native_train"]])
    reconstructed=dict(count=len(native),checkpoint_count=int(norm.count),max_abs_mean_difference=float((native.mean(0)-norm._mean).abs().max()),
        max_abs_std_difference=float((native.std(0,unbiased=False)-norm._std).abs().max()))
    historical_checkpoints = [
        history_root/"results/b0/contact_s0_wm_held_r1/wm_000000.pt",
        history_root/"results/b0/contact_s0_wm_held_r2/wm_002000.pt", BASE/"lanes_wm_v1/wm_001000.pt"]
    reconstructed["state_and_action_normalizers_equal"] = {}
    for path in historical_checkpoints:
        old = torch.load(path, map_location="cpu", weights_only=False)["dyn"]
        reconstructed["state_and_action_normalizers_equal"][str(path)] = all(
            torch.equal(t.cpu(),old[k]) for k,t in wm.state_dict().items() if "normalizer." in k)
    for source in ("recovery_b_grip_challenge_r1","lanes_modes_v1"):
        for split,eps in [("train",warp_episodes(BASE/source,model,rep,device)),("validation",validation_episodes(source,model,rep,device))]:
            for ep in eps:
                ix=np.flatnonzero(ep.valid)
                push(groups,source+"_"+split,ep.state[:-1][ix],ep.group,ix)
    raw_online=Path("results/raw_large/b0/response_s0_v1/cohort_000001")
    def get(k): return np.load(raw_online/(k+".npy"))
    valid=get("valid"); stop=get("first_fail_substep")>0
    for name,mask in [("first_terminal",valid&stop),("nonterminal",valid&~stop)]:
        ix=np.column_stack(np.where(mask))
        q,v=[get(k)[mask] for k in ("qpos","qvel")]
        state=contact_state(torch.as_tensor(q,device=device),torch.as_tensor(v,device=device))
        push(groups,"online_cohort1_"+name,state,str(raw_online),ix)
        # For the solver's non-root actuated coordinates check representation against raw storage.
        rr=rep.represent(state).cpu().numpy()
        np.testing.assert_array_equal(rr[:,10:34],q[:,7:31]); np.testing.assert_array_equal(rr[:,34:58],v[:,6:30])
        verified+=len(q)
    for tag,reg,raw in [("historical",REG,RAW),("corrected",BASE/"standard_temporal_20261124/registration.json",RAW.parent/"temporal_entries_v1")]:
        for row in json.loads(reg.read_text())["starts"]:
            folder=raw/row["id"]
            receipt=json.loads((folder/"receipt.json").read_text())
            if receipt.get("rejected"): continue
            with np.load(folder/"dynamics.npz") as d, np.load(folder/"substeps.npz") as sub:
                st=d["state"]; valid=d["valid"]; fail=d["fail"]>0
                qp=sub["qpos_post"][:,:,-1]; qv=sub["qvel_post"][:,:,-1]
            gt=contact_state(torch.as_tensor(qp,device=device),torch.as_tensor(qv,device=device))
            np.testing.assert_allclose(gt.cpu().numpy(),st[1:],rtol=2e-5,atol=1e-6)
            rr=rep.represent(gt).cpu().numpy()
            np.testing.assert_array_equal(rr[:,:,10:34],qp[:,:,7:31]);np.testing.assert_array_equal(rr[:,:,34:58],qv[:,:,6:30])
            verified+=len(qp)*qp.shape[1]
            included=np.array([lab[1]!="repeat" for lab in receipt["labels"]])
            for name,mask in [("valid_nonterminal",valid&~fail),("valid_first_terminal",valid&fail),("postterminal_or_invalid",~valid)]:
                ix=np.column_stack(np.where(mask&included))
                if not len(ix):continue
                t,b=ix.T
                for k,what in [(0,"input"),(1,"target")]:
                    state=torch.as_tensor(st[t+k,b],device=device)
                    push(groups,f"{tag}_{row['split']}_{name}_{what}",state,row["id"],ix)
    result=dict(definition="Fixed feature z=(measured represented state-archived mean)/(archived std+epsilon); maxima include finite outliers. No updates. Threshold 100 only inventories magnitude.",
        scope="All registered non-repeat branches, candidate predictor never supplied. Valid complete first failure included. State after the terminal interval can be a target but is excluded from all later legal input windows.",
        source_indices="response [20ms transition index, branch]; online [transition, lane]; old long/teacher [local transition]",
        physical_validation="Hinge and finger coordinate and velocity blocks compared elementwise (zero tolerance) to original recorded qpos[:,7:31] and qvel[:,6:30] for complete response successors plus first online inputs. Full-state 63 fields also checked for all response successors.",
        raw_state_rows_checked=verified,feature_names=names,
        stats_lineage=dict(native_training_sources=[e.group for e in native_epochs if e.split=="train"],
             held1="contact_s0_wm_held_r1 initialized from B0-03 compatible layers; fit_contact_model.py updates normalization from valid training inputs only",
             held2="contact_s0_wm_held_r2 resume of held_r1 u200 through 2000",
             lanes="lanes_wm_v1 initialized at held_r2 2000, fixed_initializer_statistics=true, then 1000 batches",
             response="response_wm_v1 +0 copies lanes +1000; historical u1 RMS buffers and paired C20/T2 initial buffers frozen",
             recompute_with_original_native_teacher_inputs=reconstructed),
        groups={k:summarise(v,names,norm,device) for k,v in groups.items()})
    (OUT/"input_support.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    for k,v in result["groups"].items():
        m=v["largest_channels"][0]
        print(k,v["n"],round(v["p99_row_max_abs_z"],1),m["name"],round(m["abs_z"],1),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history-root",type=Path,required=True)
    main(parser.parse_args().history_root)
