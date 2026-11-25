"""Strict RefXY2 packages with a shared immutable u10000 replay and lossless ring deltas."""
from pathlib import Path
from unittest.mock import patch
import shutil
import zipfile
import numpy as np
import torch
import yaml
from scripts.b0 import official_flow as flow
from scripts.b0.dynamics_h32_probe import restore_rng, rng_state

io = flow.io
LIGHT = Path("results/b0/refxy2_pair_20261125")
RAW = Path("results/raw_large/b0/refxy2_pair_20261125")
PARENT = Path("results/b0/standard_official_flow_continuation_20261125/node_010000.json")
WEIGHT = "encoders.motion.0.weight"
METHOD = {"measured": "SuperMimic-M1Piper-RefXY2-v1", "zero": "SuperMimic-M1Piper-RefXY2-zero-v1"}


def config(mode):
    base = yaml.safe_load(flow.CONFIG.read_text())
    assert base["execution_recipe"] == "official_flow_s0_v1"
    return base | dict(actor_goal_schema="refxy2_" + mode, method_id=METHOD[mode],
                       feature_mode=mode, feature_scale_m=0.05, experiment_id="refxy2_pair_s0_v1")


def read_pt(path, device="cpu"):
    return torch.load(path, weights_only=False, map_location=device, mmap=True)


def node(mode, u):
    return LIGHT / mode / f"node_{u:06}.json"


def checkpoint(mode, u):
    return RAW / mode / f"checkpoint_{u:06}.pt"


def state_dir(mode, u):
    return RAW / mode / f"resume_{u:06}"


def expand(value):
    assert value.shape == (2048, 540)
    result = torch.nn.functional.pad(value, (0, 2))
    assert torch.equal(result[:, :540], value) and result[:, 540:].count_nonzero() == 0
    return result


def prepare(mode):
    if node(mode, 0).exists():
        raise FileExistsError(node(mode, 0))
    parent = io.read(PARENT)
    assert parent["update"] == 10000 and parent == io.read(PARENT.parent / "recovery.json")
    c = config(mode)
    run, _ = flow.build(c)
    source = read_pt(parent["checkpoint"])
    assert source["cfg"] == yaml.safe_load(flow.CONFIG.read_text())
    archive = read_pt(Path(parent["state"]) / "state.pt")
    assert archive["total"] == parent["valid"] and archive["schedule"] == parent["ratio"]
    changed = []
    checks = {}
    for name in ("actor", "critic", "dyn"):
        module = getattr(run, name)
        assert module.state_dict().keys() == source[name].keys()
        state = dict(source[name])
        if name == "actor":
            state[WEIGHT] = expand(state[WEIGHT])
            changed.append("actor." + WEIGHT)
        module.load_state_dict(state, strict=True)
        for key, value in module.state_dict().items():
            assert torch.equal(value.cpu(), state[key]), (name, key)
            checks[f"{name}.{key}"] = list(value.shape)
    optimizers = archive["optimizer"]
    live_weight = dict(run.actor.named_parameters())[WEIGHT]
    hits = []
    for index, (optimizer, saved) in enumerate(zip(run.optimizer_list(), optimizers, strict=True)):
        for group_idx, (actual, stored) in enumerate(zip(optimizer.param_groups, saved["param_groups"], strict=True)):
            for param, pid in zip(actual["params"], stored["params"], strict=True):
                if param is live_weight:
                    assert isinstance(optimizer, torch.optim.Adam)
                    moment = saved["state"][pid]
                    assert set(moment) == {"exp_avg", "exp_avg_sq", "step"}
                    for key in ("exp_avg", "exp_avg_sq"):
                        moment[key] = expand(moment[key])
                        changed.append(f"optimizer.{index}.{pid}.{key}")
                    hits.append(dict(optimizer=index, group=group_idx, parameter_id=pid, step=moment["step"].item(),
                        hyperparameters={k: v.item() if torch.is_tensor(v) else v for k,v in stored.items() if k != "params"}))
        optimizer.load_state_dict(saved)
        loaded = optimizer.state_dict()
        for pid, values in saved["state"].items():
            for key, value in values.items():
                if torch.is_tensor(value):
                    assert torch.equal(loaded["state"][pid][key].cpu(), value.cpu())
                    checks[f"optimizer.{index}.{pid}.{key}"] = list(value.shape)
        for a,b in zip(loaded["param_groups"], saved["param_groups"], strict=True):
            assert a.keys()==b.keys()
            assert all(torch.equal(a[k].cpu(),b[k].cpu()) if torch.is_tensor(b[k]) else a[k]==b[k] for k in b)
    assert len(hits) == 1 and hits[0]["step"] == 10000
    directory = state_dir(mode, 0)
    directory.mkdir(parents=True, exist_ok=True)
    model = dict(source, cfg=c, actor=run.actor.state_dict(), updates=0)
    io.atomic_torch(model, checkpoint(mode,0))
    io.atomic_torch(optimizers, directory / "optimizers.pt")
    receipt = dict(parent, update=0, parent_receipt=str(PARENT), checkpoint=str(checkpoint(mode,0)),
                   state=str(directory), parent_clock=parent["clock"], mode=mode, storage_format="refxy2_delta_v1")
    io.write(node(mode,0).parent/"migration.json",dict(method=METHOD[mode], changed_tensors=changed,
             verified_tensor_shapes=checks, adam=hits[0], shared_boundary=parent, stats=flow.stats(run),
             unchanged_full_state_source=str(Path(parent["state"])/"state.pt"), solver_source=parent["state"],
             new_tail_mean_variance="fixed physical scale; original motion buffers retain width 540"))
    io.write(node(mode,0),receipt)


def tensors_to(value, device):
    if torch.is_tensor(value):
        return value.to(device)
    if isinstance(value, list):
        return [tensors_to(v,device) for v in value]
    if isinstance(value, tuple):
        return tuple(tensors_to(v,device) for v in value)
    if isinstance(value, dict):
        return {k:tensors_to(v,device) for k,v in value.items()}
    return value


def save_delta(run, start, dest):
    # Store only slots written since the previous published boundary. Each row
    # is a bit-exact snapshot, including history, with no statistical encoding.
    delta = dest / "replay_delta.npz"
    with zipfile.ZipFile(delta.with_suffix(".tmp"),"w",compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for tick in range(start,run.replay.clock):
            page, offset=divmod(tick % run.replay.capacity, run.replay.page_size)
            for key, field in run.replay.pages[page].items():
                with z.open(f"{tick}/{key}.npy","w") as stream:
                    np.lib.format.write_array(stream, field[offset].cpu().numpy(), allow_pickle=False)
    delta.with_suffix(".tmp").replace(delta)


def apply_delta(run, start, end, directory):
    with np.load(directory/"replay_delta.npz", allow_pickle=False) as data:
        for tick in range(start,end):
            page, offset=divmod(tick % run.replay.capacity,run.replay.page_size)
            for key,field in run.replay.pages[page].items():
                field[offset].copy_(torch.from_numpy(data[f"{tick}/{key}"]))


def restore(run, mode, u):
    receipt = io.read(node(mode,u))
    assert run.cfg == config(mode) and receipt["mode"] == mode
    package = read_pt(receipt["checkpoint"])
    assert package["cfg"] == run.cfg and package["updates"] == u
    for name in ("actor","critic","dyn"):
        getattr(run,name).load_state_dict(package[name], strict=True)
    parent = io.read(PARENT)
    assert receipt["parent_receipt"] == str(PARENT)
    base = read_pt(Path(parent["state"]) / "state.pt")
    run.replay.pages = tensors_to(base["replay"]["pages"],run.device)
    current = parent["clock"]
    deltas = receipt.get("delta_nodes",[])
    for i in deltas:
        step = io.read(node(mode,i))
        assert step["previous_clock"] == current
        apply_delta(run,current,step["clock"],state_dir(mode,i))
        current = step["clock"]
    assert current == receipt["clock"]
    if u == 0:
        data = base
        opts = read_pt(state_dir(mode,0)/"optimizers.pt")
        solver = Path(parent["state"])
    else:
        solver = state_dir(mode,u)
        data = read_pt(solver/"state.pt")
        opts = data["optimizer"]
    for opt,saved in zip(run.optimizer_list(),opts,strict=True):
        opt.load_state_dict(tensors_to(saved,run.device))
        assert all(not torch.is_tensor(g["lr"]) or g["lr"].device == next(iter(g["params"])).device for g in opt.param_groups)
    run.sampler.load_state_dict(tensors_to(data["sampler"],run.device))
    run.schedule.load_state_dict(data["schedule"])
    for k in ("total","simulated","last_episode"):
        setattr(run,k,data[k])
    for k,v in data["replay"].items():
        if k != "pages":
            setattr(run.replay,k,tensors_to(v,run.device))
    run.lanes=tensors_to(data["lanes"],run.device)
    with patch.object(io,"SHARED",solver):
        io.solver_snapshot(run,True)
    for key,value in data["counters"].items():
        getattr(run.plant,key).copy_(value)
    restore_rng(data["rng"])
    assert io.optimizer_steps(run) == receipt["steps"] and flow.stats(run) == receipt["stats"]
    assert run.schedule.state_dict()==receipt["ratio"]
    assert (run.total,run.simulated,run.replay.clock)==(receipt["valid"],receipt["simulated"],receipt["clock"])
    return receipt


def save(run, mode, u, previous):
    dest = state_dir(mode,u)
    if not dest.exists() and (mode == "zero" or shutil.disk_usage(dest.parent).free < 4*1024**3):
        backing = Path("/root/autodl-fs/dog-and-arm/refxy2_pair_20261125") / mode / dest.name
        if shutil.disk_usage(backing.parents[3]).free >= 2*1024**3:
            backing.mkdir(parents=True,exist_ok=True)
            dest.symlink_to(backing,target_is_directory=True)
    dest.mkdir(parents=True,exist_ok=True)
    assert not node(mode,u).exists()
    io.atomic_torch(io.package(run,u),checkpoint(mode,u))
    state = dict(optimizer=[opt.state_dict() for opt in run.optimizer_list()], rng=rng_state(),
        schedule=run.schedule.state_dict(),sampler=run.sampler.state_dict(),total=run.total,simulated=run.simulated,
        last_episode=run.last_episode,lanes=run.lanes,
        replay={k:v for k,v in vars(run.replay).items() if k not in ("pages","receipt","index")},
        counters={k:getattr(run.plant,k) for k in (*io.COUNTERS,"servo_bias")})
    io.atomic_torch(state,dest/"state.pt")
    with patch.object(io,"SHARED",dest):
        io.solver_snapshot(run,False)
    save_delta(run,previous["clock"],dest)
    receipt = dict(mode=mode,update=u,storage_format="refxy2_delta_v1",checkpoint=str(checkpoint(mode,u)),
        state=str(dest),parent_receipt=str(PARENT),parent_clock=previous["parent_clock"],
        delta_nodes=previous.get("delta_nodes",[])+[u],previous_clock=previous["clock"],
        clock=run.replay.clock,valid=run.total,simulated=run.simulated,steps=io.optimizer_steps(run),
        stats=flow.stats(run),ratio=run.schedule.state_dict())
    assert read_pt(dest/"state.pt")["total"] == run.total
    assert read_pt(checkpoint(mode,u))["cfg"]==run.cfg
    for name in ("solver.npz","replay_delta.npz"):
        with zipfile.ZipFile(dest/name) as z:
            assert z.testzip() is None
    io.write(node(mode,u),receipt)
    return receipt
