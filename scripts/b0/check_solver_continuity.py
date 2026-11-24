"""Compare four paths from a full live Warp state following a registered real prefix."""
import argparse
import dataclasses
import json
import time
from pathlib import Path

import mujoco
import mujoco_warp
import numpy as np
import torch
import warp as wp

from learning.b0.contact_warp import ContactPlant
from learning.b0.physics import make_model
from scripts.b0.training_entry_response import RAW, arr, phases, register_solver

DEVICE = "cuda:0"
OUT = Path("results/b0/standard_temporal_20261124")
COUNTERS = ("load_ticks", "lost_ticks", "slip_ticks", "sat_ticks", "saturation_time")


def buffers(obj):
    for field in dataclasses.fields(obj):
        value = getattr(obj, field.name)
        if isinstance(value, wp.array) and value.size:
            yield value
        elif dataclasses.is_dataclass(value):
            yield from buffers(value)


def vec(array):
    return torch.as_tensor(np.array(array), dtype=torch.float32, device=DEVICE)


def identity(plant):
    d = plant.sim.wp_data
    count = int(d.nacon.numpy()[0])
    worlds = d.contact.worldid.numpy()[:count]
    pairs = d.contact.geom.numpy()[:count][worlds == 0]
    nefc = int(d.nefc.numpy()[0])
    return dict(qpos=plant.data.qpos[0].cpu().tolist(), qvel=plant.data.qvel[0].cpu().tolist(),
                qfrc_bias=d.qfrc_bias.numpy()[0].tolist(), warmstart=d.qacc_warmstart.numpy()[0].tolist(),
                nefc=nefc, constraint_types=sorted(d.efc.type.numpy()[0,:nefc].tolist()),
                contact_pairs=sorted([sorted(pair.tolist()) for pair in pairs]))


def run_case(plant, side):
    folder = RAW / f"{side}_0_validation_grip_hold"
    meta = json.loads((folder/"receipt.json").read_text())
    data = Path(meta["row"]["path"])
    t = meta["frame"]
    n = plant.count
    sidebits = torch.full((n,), int(side == "push"), device=DEVICE, dtype=torch.long)
    phase = torch.as_tensor(phases(data)[(t-10)*10:(t+1)*10].reshape(11,10), device=DEVICE)
    q0, v0 = [vec(arr(data, key)[t-10]) for key in ("qpos","qvel")]
    plant.reset(q0.expand(n,-1), v0.expand(n,-1))
    for j in range(10):
        command = vec(arr(data,"action_clipped")[t-10+j]).expand(n,-1)
        ev = plant.step_contact(command, sidebits, phase[j].expand(n,-1))
        if ev["first_fail_substep"][0] or not ev["valid_full_interval"][0]:
            raise ValueError("The physical prefix failed")
    wp.synchronize()
    snapshot = [(a, wp.clone(a)) for a in buffers(plant.sim.wp_data)]
    counters = {k:getattr(plant,k).clone() for k in COUNTERS}
    warm = identity(plant)
    data_fields = np.load(folder/"start.npz")
    registered_qdiff = float(np.max(np.abs(np.array(warm["qpos"])-data_fields["qpos"])))
    oldcmd = np.load(folder/"dynamics.npz")["action"][0]
    rows = []
    for name in ("actor","ref_arm"):
        idx = meta["labels"].index(["u0",name,0,0.])
        command = vec(oldcmd[idx]).expand(n,-1)
        cases = {}
        for route in ("continuous","repeat","registration","neighbor_reset"):
            for buf, original in snapshot:
                wp.copy(buf, original)
            for k, val in counters.items():
                getattr(plant,k).copy_(val)
            wp.synchronize()
            if route == "registration":
                register_solver(plant)
            elif route == "neighbor_reset":
                plant.reset(q0[None], v0[None], torch.tensor([1],device=DEVICE))
            start = identity(plant)
            trace = plant.step_contact(command, sidebits, phase[-1].expand(n,-1), record=True)
            rec = trace["substeps"]
            cases[route] = dict(start=start, ctrl_first=rec["ctrl"][0,0].cpu().tolist(),
                mm_opening=[float((q[29]-q[30])*1000) for q in rec["qpos_post"][0]],
                q2=rec["qpos_post"][0,0].cpu().tolist(), q20=rec["qpos_post"][0,-1].cpu().tolist(),
                v2=rec["qvel_post"][0,0].cpu().tolist(), v20=rec["qvel_post"][0,-1].cpu().tolist(),
                door_force=rec["door_robot_force_N"][0].norm(dim=1).cpu().tolist(),
                warmstart20=plant.sim.wp_data.qacc_warmstart.numpy()[0].tolist(),
                first_fail=int(trace["first_fail_substep"][0]))
        diffs = {}
        ref = cases["continuous"]
        for key,c in cases.items():
            diff = {k:float(np.abs(np.array(c[k])-ref[k]).max()) for k in
                    ("ctrl_first","q2","q20","v2","v20","door_force","mm_opening","warmstart20")}
            for k in ("warmstart","qfrc_bias","qpos","qvel"):
                diff["start_"+k]=float(np.abs(np.array(c["start"][k])-ref["start"][k]).max())
            for k in ("constraint_types","nefc","contact_pairs"):
                diff["same_start_"+k]=c["start"][k]==ref["start"][k]
            diffs[key] = diff
        print(side, name, diffs, flush=True)
        rows.append(dict(side=side, branch=name, source=str(folder), command=oldcmd[idx].tolist(),
                         repeat_vs_old_start_q=registered_qdiff, paths=cases, max_abs_delta=diffs))
    return rows


@torch.no_grad()
def main(repaired):
    start=time.monotonic()
    plant=ContactPlant(make_model(),2,DEVICE,preserve_continuous_bias=repaired)
    rows=sum([run_case(plant,side) for side in ("pull","push")],[])
    OUT.mkdir(exist_ok=True)
    tag = "retest" if repaired else "before"
    result=dict(versions={"mujoco":mujoco.__version__,"warp":wp.__version__,"mujoco_warp":mujoco_warp.__version__},
                retained="All nonempty Warp Data arrays recursively, plus audit counters; restored before each route",
                worlds=2, prefix_s=.2, branches="Exactly retained u0 / u0 reference-arm first complete 23d command",
                wall_s=time.monotonic()-start, observations=rows)
    (OUT/f"solver_{tag}.json").write_text(json.dumps(result,indent=1,allow_nan=False)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repaired",action="store_true")
    main(p.parse_args().repaired)
