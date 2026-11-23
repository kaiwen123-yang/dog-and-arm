"""Contrast replay minibatches on one completed contact checkpoint, without learning."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from learning.b0.contact_replay_draw import LaneAgeIndex
from learning.b0.contact_training import OnlineContactReplay
from learning.b0.physics import settings


def summary(values):
    q = np.quantile(values, [.05,.5,.95])
    return dict(mean=float(np.mean(values)),p05=float(q[0]),median=float(q[1]),p95=float(q[2]))


def audit(directory, batches, seed):
    state = torch.load(directory/"cohort_state.pt",mmap=True,map_location="cpu",weights_only=False)
    cfg = state["cfg"]
    chunks = state["replay"]
    old = OnlineContactReplay(len(chunks),"cpu")
    new = OnlineContactReplay(len(chunks),"cpu","official_lane_age")
    old.chunks.extend(chunks)
    new.chunks.extend(chunks)
    by_id = {id(d):c for c,(d,_) in enumerate(chunks)}
    paths=[Path(cfg["reference_directory"])/name for name in cfg["references"]]
    ends, wanted = [], []
    for path in paths:
        n = int(np.load(path/"valid_full_interval.npy").sum())
        meta=json.loads((path/"metadata.json").read_text())
        labels=np.asarray(meta["phases"])[np.load(path/"substeps/phase.npy")[:n*10:10]]
        wanted.extend(np.r_[np.isin(labels,["open","hold"]),False])
        ends.append(len(wanted))
    ends = torch.as_tensor(ends)
    ref_grip = torch.as_tensor(wanted)
    f=directory/"cohorts.jsonl"
    ledger=[json.loads(s) for s in (f if f.exists() else directory/"updates.jsonl").read_text().splitlines()]
    kept=[i for i,r in enumerate(ledger,1) if r["valid_transitions"]][-len(chunks):]
    fields = (len(chunks),cfg["worlds"],cfg["cohort_steps"])
    motion = torch.full(fields,-1,dtype=torch.long)
    grip = torch.zeros(fields,dtype=torch.bool)
    force = torch.full(fields,-1,dtype=torch.int8)
    touched = torch.zeros(fields,dtype=torch.bool)
    threshold=settings("mobile",1)["contact_threshold_n"]
    measured = []
    for c,((data,_),k) in enumerate(zip(chunks,kept,strict=True)):
        t=data["motion_time"].long()
        motion[c,:,:t.shape[1]]=torch.searchsorted(ends,t)
        grip[c,:,:t.shape[1]]=ref_grip[t]
        folder=Path("results/raw_large/b0")/directory.name/f"cohort_{k:06d}"
        if (folder/"sub_finger_load_N.npy").exists():
            loads=np.load(folder/"sub_finger_load_N.npy",mmap_mode="r")
            if not np.array_equal(t.T.numpy(),np.load(folder/"frame.npy")):
                raise ValueError("Raw force clock does not match replay chunk")
            force[c,:,:t.shape[1]]=torch.as_tensor((loads>threshold).all(axis=(-1,-2)).T.copy())
            touched[c,:,:t.shape[1]]=torch.as_tensor((loads>threshold).any(axis=(-1,-2)).T.copy())
            measured.append(k)
    blocks = {}
    for key,steps,batch in (("H7_WM_online",7,3*cfg["wm_batch"]//4),
                            ("H1_WM_online",1,cfg["wm_batch"]),("H32_Actor_starts",1,cfg["actor_batch"])):
        index=LaneAgeIndex(chunks,steps)
        table=index.table
        cc,ll,tt=table.T
        eligible_force=force[cc,ll,tt]
        old_weight=torch.full((len(table),),1/len(table),dtype=torch.float64)
        new_weight=1/(index.counts[ll].double()*(index.counts>0).sum())
        draws={}
        for name,weights in (("single_cohort",old_weight),("official_lane_age",new_weight)):
            torch.manual_seed(seed)
            np.random.seed(seed)
            detail=[]
            for _ in range(batches):
                if name=="single_cohort":
                    data,l,t=old.pick(steps,batch)
                    c=torch.full_like(l,by_id[id(data)])
                else:
                    c,l,t=index.draw(batch).T
                h=grip[c,l,t]
                known=force[c,l,t]
                episode=c*cfg["worlds"]+l
                detail.append(dict(unique_cohorts=len(c.unique()),unique_lane_ids=len(l.unique()),
                    unique_physical_episodes=len(episode.unique()),unique_motion_ids=len(motion[c,l,t].unique()),
                    reference_open_hold_starts=int(h.sum()),unique_reference_open_hold_episodes=len(episode[h].unique()),
                    measured_force_known_starts=int((known>=0).sum()),both_fingers_loaded_starts=int((known==1).sum()),
                    any_finger_contact_starts=int(touched[c,l,t].sum()),
                    unique_observed_finger_contact_episodes=len(episode[touched[c,l,t]].unique()),
                    contains_observed_two_finger=int((known==1).any())))
            draws[name] = dict(per_minibatch={k:summary([r[k] for r in detail]) for k in detail[0]},
                exact_motion_probability=torch.bincount(motion[cc,ll,tt],weights=weights,minlength=len(ends)).tolist(),
                exact_reference_open_hold_probability=float(weights[grip[cc,ll,tt]].sum()),
                exact_known_physical_two_finger_probability=float(weights[eligible_force==1].sum()),
                exact_known_any_finger_contact_probability=float(weights[touched[cc,ll,tt]].sum()),
                exact_force_label_coverage=float(weights[eligible_force>=0].sum()))
        # Exercise the actual WM and Actor entry points, with the same seeded draw.
        torch.manual_seed(seed)
        expected=index.draw(batch)
        torch.manual_seed(seed)
        sample=new.initial(batch) if key=="H32_Actor_starts" else new.windows(steps,batch)
        for c in expected[:,0].unique().tolist():
            select=expected[:,0]==c
            _,l,t=expected[select].T
            data=chunks[c][0]
            if key=="H32_Actor_starts":
                for field in ("state","history","prev_action","motion_time","sim_ctx"):
                    torch.testing.assert_close(sample[field][select],data[field][l,t],rtol=0,atol=0)
            else:
                for offset in range(steps):
                    torch.testing.assert_close(sample["action"][select,offset],data["action"][l,t+offset],rtol=0,atol=0)
                    torch.testing.assert_close(sample["state"][select,offset],data["state"][l,t+offset],rtol=0,atol=0)
                torch.testing.assert_close(sample["state"][select,-1],data["next_state"][l,t+steps-1],rtol=0,atol=0)
        blocks[key]=dict(batch_size=batch,legal_windows=len(table),eligible_envs=int((index.counts>0).sum()),
            reference_open_hold_legal_starts=int(grip[cc,ll,tt].sum()),force_known_legal_starts=int((eligible_force>=0).sum()),
            known_any_finger_contact_legal_starts=int(touched[cc,ll,tt].sum()),
            known_sustained_two_finger_legal_starts=int((eligible_force==1).sum()),
            windows_per_lane_min_max=[int(index.counts.min()),int(index.counts.max())],draws=draws,
            exact_entry_data_match=True)
    return dict(run=directory.name,updates=state["updates"],stored_cohorts=kept,raw_force_labelled_cohorts=measured,
                seed=seed,batches_per_mode=batches,references=cfg["references"],blocks=blocks,
                physical_contact_definition=f"both finger loads >{threshold} N on all 10 physical substeps of the start interval",
                unknown_contact="only retained raw cohorts support physical forces; remaining rows have known reference phase labels",
                history="H32 starts carry the measured 10-frame clean sensor history and preceding clipped command; unchanged")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    parser.add_argument("--batches",type=int,default=256)
    parser.add_argument("--seed",type=int,default=301)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.run,args.batches,args.seed)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x") as f:
        json.dump(result,f,indent=2)
        f.write("\n")
