"""Registered dynamics-only sources for measured H1/H7 windows."""
from collections import Counter
import json
from pathlib import Path

import numpy as np
import torch
from tensordict import TensorDict

from .contact_model import contact_context
from .contact_policy import DoorMotions
from .contact_replay import ContactEpisode, ContactWindows
from .contact_warp import PHASES, PHASE_ID


def native_episodes(paths, device):
    episodes=[]
    for path in paths:
        ep=ContactEpisode.read(path,device)
        if ep.split!="train":
            raise ValueError(f"Non-training teacher: {path}")
        names=json.loads((path/"metadata.json").read_text())["phases"]
        ep.phase=np.array([PHASE_ID[p] for p in names])[np.load(path/"substeps/phase.npy")[np.load(path/"physics_step.npy")[:-1]]]
        episodes.append(ep)
    return episodes


def warp_episodes(directory,model,rep,device):
    from scripts.b0.h32_fit_recovery_wm import load_cohorts
    reg=json.loads((directory/"registration.json").read_text())
    refs=json.loads((Path(reg["anchor"]).parent/"actual_config.json").read_text())["cfg"]["references"]
    paths=[Path(reg["reference_directory"])/name for name in refs]
    rows=[r for r in json.loads((directory/"cohorts.json").read_text()) if r["split"]=="train"]
    alloc=reg["allocation"]
    if len(set(s for _,s in alloc))!=len(alloc) or [r["seed"] for r in rows]!=[s for sp,s in alloc if sp=="train"]:
        raise ValueError("Training rows differ from registration")
    episodes,details=load_cohorts(rows,paths,DoorMotions(paths,rep,device),model,device)
    for ep,detail in zip(episodes,details,strict=True):
        ep.phase=detail["phase"]
    return episodes


def response_episodes(source,model,device):
    rows=json.loads(Path(source["registration"]).read_text())["starts"]
    episodes=[]
    for row in rows:
        if row["split"]!="train":
            continue
        folder=Path(source["raw"])/row["id"]
        receipt=json.loads((folder/"receipt.json").read_text())
        if row!=receipt["row"] or json.loads((Path(row["path"])/"metadata.json").read_text())["wm_split"]!="train":
            raise ValueError("Unexpected response trajectory identity")
        if receipt.get("rejected"):
            continue
        with np.load(folder/"dynamics.npz") as data, np.load(folder/"substeps.npz") as sub:
            state=torch.as_tensor(data["state"],device=device)
            act=torch.as_tensor(data["action"],device=device)
            valid=data["valid"]
            fail=data["fail"]
            phase=sub["training_phase"]
            force=sub["finger_load_N"]>.01
        for lane,label in enumerate(receipt["labels"]):
            # Same-command repeats measure numerical noise and do not add training weight.
            if label[1]=="repeat":
                continue
            n=int(valid[:,lane].sum())
            if not n:
                continue
            if not valid[:n,lane].all() or valid[n:,lane].any() or fail[:n-1,lane].any():
                raise ValueError("Response window crosses a failure")
            fg=force[:n,lane]
            modes=np.full(n,"free",dtype="<U18")
            modes[fg.any((1,2))]="other_contact"
            modes[fg.all((1,2))]="two_finger"
            modes[(np.isin(phase[:n],[PHASE_ID["open"],PHASE_ID["hold"]]) & ~fg.all(-1)).any(1)]="loss_or_slip"
            modes[np.isin(phase[:n],[PHASE_ID["release"],PHASE_ID["retreat_arm"]]).any(1)]="release"
            ep=ContactEpisode(folder,row["id"]+f"/b{lane}","train",row["side"],state[:n+1,lane],
                act[:n,lane],contact_context(model,row["side"],device),np.ones(n,bool),modes)
            ep.phase=phase[:n,0]
            episodes.append(ep)
    return episodes


class SourceWindows(ContactWindows):
    def __init__(self, episodes, steps, lane_age=True):
        super().__init__(episodes,steps)
        self.lane_age=lane_age
        self.episodes=episodes
        counts=torch.tensor([len(e.starts(steps)) for e in episodes],device=self.starts.device)
        self.eligible=torch.where(counts>0)[0]
        self.counts=counts
        self.begin=counts.cumsum(0)-counts
        self.base=np.cumsum([0]+[len(e.state) for e in episodes])[:-1]
        self.phase=np.concatenate([np.r_[e.phase,-1] for e in episodes])
        self.mode=np.concatenate([np.r_[e.modes,np.array(["unused"])] for e in episodes])
        self.sides=np.array([e.side for e in episodes])

    def draw(self,count):
        device=self.starts.device
        if self.lane_age:
            lane=self.eligible[torch.randint(len(self.eligible),(count,),device=device)]
            age=(torch.rand(count,device=device)*self.counts[lane]).long()
            picks=self.begin[lane]+age
        else:
            picks=torch.randint(len(self.starts),(count,),device=device)
            lane=torch.searchsorted(self.begin+self.counts,picks,right=True)
        first=self.starts[picks]
        ix=first[:,None]+self.offset
        ep=lane.cpu().numpy()
        step=first.cpu().numpy()
        stats=dict(split="train",samples=count,episodes=int(len(np.unique(ep))),
            trajectories=len({self.episodes[i].group.split("/b")[0] for i in ep}),
            side_phase_mode=dict(Counter(f"{s}/{PHASES[p]}/{m}" for s,p,m in zip(self.sides[ep],self.phase[step],self.mode[step]))))
        return TensorDict(dict(state=self.state[ix],action=self.action[ix],sim_ctx=self.context[ix]),batch_size=ix.shape),stats


class RegisteredWM:
    def __init__(self,cfg,model,rep,native,device):
        self.recipe=cfg["wm_data_recipe"]
        groups={"native":native}
        for name,source in self.recipe["sources"].items():
            groups[name]=(response_episodes(source,model,device) if "raw" in source else
                          warp_episodes(Path(source["directory"]),model,rep,device))
        self.pools={}
        self.inventory={}
        for name,eps in groups.items():
            if len(set(e.group for e in eps))!=len(eps):
                raise ValueError("Repeated identities within "+name)
            self.inventory[name]=dict(episodes=len(eps),horizons={})
            for h in (1,7):
                total=sum(len(e.starts(h)) for e in eps)
                self.inventory[name]["horizons"][h]=total
                if total:
                    self.pools[name,h]=SourceWindows(eps,h,lane_age=name!="native")
        self.rows=[]

    def draw(self,h,index,size,replay=None):
        key="warm" if replay is None else "joint"
        native=self.recipe[key][f"h{h}_native"]
        warp=self.recipe[key][f"h{h}_warp"]
        online=size-warp-native
        parts=[]
        counts={}
        if online:
            batch=replay.windows(h,online)
            if batch is not None:
                parts.append(batch)
                counts["online"]=replay.last_draw
            else:
                # Backfill the unavailable online share using the inherited offline rule.
                extra_native=online//2 if h==7 else online
                warp+=online-extra_native
                native+=extra_native
        eligible=[name for name in self.recipe["sources"] if (name,h) in self.pools]
        if not eligible:
            raise ValueError("No registered training source has legal windows")
        shares={name:warp//len(eligible) for name in eligible}
        for i in range(warp%len(eligible)):
            shares[eligible[(index+i)%len(eligible)]]+=1
        for name,count in {"native":native,**shares}.items():
            if count:
                batch,counts[name]=self.pools[name,h].draw(count)
                parts.append(batch)
        result=torch.cat(parts)
        if len(result)!=size:
            raise ValueError("WM batch size mismatch")
        self.rows.append(dict(index=index,h=h,stored=size*(h+1),successors=size*h,sources=counts))
        return result,counts.get("online",{}).get("samples",0)
