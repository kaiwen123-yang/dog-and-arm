"""Collect one frozen-u0 train cohort and a separate physical development cohort."""
import os
os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import argparse
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch
from scripts.b0 import dynamics_h32_pilot as pilot
from scripts.b0.dynamics_h32_probe import rng_state
from scripts.b0.training_entry_response import phases

OUT = Path("results/b0/standard_joint_contact_20261124")
RAW = Path("results/raw_large/b0/joint_contact_20261124")
SEEDS = {"train": 112401, "development": 112402}


def dev_reset(run, stack):
    """Use held-development q/v at the matched prefix frame. The policy reference stays fixed."""
    root = Path(run.cfg["reference_directory"])
    q, v, ref_to_dev, identities = [], [], [], []
    offset = 0
    for name, start, end in zip(run.cfg["references"], run.bank.motion_starts, run.bank.motion_ends, strict=True):
        train, dev = root/name, root/name.replace("_train", "_validation")
        meta = pilot.read(dev/"metadata.json")
        assert meta["wm_split"] == "validation"
        nn = int(end-start)
        dd = int(np.load(dev/"valid_full_interval.npy").sum())+1
        def labels(path, length):
            ps = phases(path)[::10][:length-1]
            return np.r_[ps, ps[-1]]
        a, b = labels(train,nn), labels(dev,dd)
        m = np.empty(nn, np.int64)
        for label in np.unique(a):
            ii, jj = np.where(a==label)[0],np.where(b==label)[0]
            if not len(jj):
                raise ValueError(f"{dev} lacks phase {label}")
            m[ii] = jj[np.rint(np.linspace(0,len(jj)-1,len(ii))).astype(int)]
        ref_to_dev.append(m+offset)
        q.append(np.load(dev/"qpos.npy")[:dd])
        v.append(np.load(dev/"qvel.npy")[:dd])
        offset += dd
        identities.append(str(dev))
    q,v = [torch.as_tensor(np.concatenate(x),device=run.device,dtype=run.bank.qpos.dtype) for x in (q,v)]
    lookup = torch.as_tensor(np.concatenate(ref_to_dev),device=run.device)
    sample,reset = run.sampler.sample,run.plant.reset
    frame = None
    pairs = []
    def draw(n):
        nonlocal frame
        out = sample(n)
        frame = out-10
        return out
    def physical_reset(q_ref,v_ref,ids):
        assert frame is not None and torch.equal(run.bank.qpos[frame],q_ref)
        pos = lookup[frame]
        pairs.extend(torch.stack((ids,frame,pos),dim=1).cpu().tolist())
        return reset(q[pos],v[pos],ids)
    stack.enter_context(patch.object(run.sampler,"sample",draw))
    stack.enter_context(patch.object(run.plant,"reset",physical_reset))
    return identities,pairs


def collect(split):
    directory = RAW/"collection"/split
    directory.mkdir(parents=True,exist_ok=True)
    destination = directory/"state.pt"
    if destination.exists():
        raise FileExistsError(destination)
    run = pilot.build("experiment")
    if split=="train":
        pilot.load_common(run)
    shared=torch.load(pilot.SHARED/"first.pt",weights_only=False,map_location="cpu")
    assert all(torch.equal(t.cpu(),shared["actor"][k]) for k,t in run.actor.state_dict().items())
    run.cfg["freeze_actor_statistics"]=True
    run.compact_directory=directory
    torch.manual_seed(SEEDS[split])
    np.random.seed(SEEDS[split])
    with ExitStack() as stack:
        paths,pairs=(run.cfg["references"],[]) if split=="train" else dev_reset(run,stack)
        result=run.collect()
    for k,t in run.actor.state_dict().items():
        assert torch.equal(t.cpu(),shared["actor"][k]),k
    chunks=list(run.replay.chunks)
    current,starts=chunks[-1]
    ix=starts[1]
    terminal=int(current["terminated"][ix[:,0],ix[:,1]].sum())
    assert result["valid_transitions"]==len(ix) and len(starts[7])>0
    payload=dict(chunks=chunks,tail=run.replay.tail,rng=rng_state(),sampler=run.sampler.state_dict(),
                 schedule=run.schedule.state_dict(),total=run.total,simulated=run.simulated,
                 last_episode=run.last_episode,lanes=run.lanes,
                 counters={k:t.clone() for k,t in vars(run.plant).items() if torch.is_tensor(t) and
                           (k in pilot.COUNTERS or "bias" in k and k!="bias_gain")})
    if split=="train":
        with patch.object(pilot,"SHARED",directory):
            pilot.solver_snapshot(run,False)
    pilot.atomic_torch(payload,destination)
    pilot.write(OUT/"collection"/(split+".json"),dict(split=split,seed=SEEDS[split],collector=result,
        h1=len(ix),h7=len(starts[7]),terminal_first=terminal,chunks_in_file=len(chunks),
        training_replay=(split=="train"),freeze_all_actor_parameters_and_buffers_verified=True,
        coordinates="128 lanes, 40 policy ticks, 80 physics ticks per interval, including 10-tick real prefixes",
        initial_qv_source=paths,reference_paths=run.cfg["references"],physical_dev_reset_log=pairs,
        dev_frame_mapping="Within-phase relative progress on held source, unchanged policy reference clock and original 200ms reference prefix",
        raw=str(destination),shared_source=str(pilot.SHARED/"first.pt"),physics_dt=run.model.opt.timestep))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("split",choices=SEEDS)
    collect(p.parse_args().split)
