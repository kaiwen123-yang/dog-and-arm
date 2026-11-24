"""Verify the contact training timebase on a real archived prefix and held command."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_events import FrozenDoorReference, ContactEvents
from learning.b0.contact_warp import ContactPlant
from learning.b0.physics import make_model, settings
from scripts.b0.register_contact_dev import SEGMENTS
from scripts.b0.training_entry_response import arr, phases

RAW = Path("results/raw_large/b0/temporal_entries_v1")
OUT = Path("results/b0/standard_dynamics_20261124")


@torch.no_grad()
def verify(dt, side):
    model = make_model()
    model.opt.timestep = dt
    plant = ContactPlant(model, 2, "cuda:0", preserve_continuous_bias=True)
    clock, data = plant.clock, plant.data
    folder = RAW / f"{side}_0_validation_grip_hold"
    meta = json.loads((folder/"receipt.json").read_text())
    path, frame = Path(meta["row"]["path"]), meta["frame"]
    def vector(row):
        return torch.as_tensor(np.array(row), dtype=torch.float32, device=plant.device)
    def duplicate(row):
        return vector(row).expand(2,-1)
    def phase(j):
        return torch.as_tensor(labels[j*10:j*10+10],device=plant.device).expand(2,-1)
    labels = phases(path)
    sides = torch.full((2,), int(side=="push"),device=plant.device,dtype=torch.long)
    plant.reset(duplicate(arr(path,"qpos")[frame-10]), duplicate(arr(path,"qvel")[frame-10]))
    prefix_failures = []
    for j in range(frame-10,frame):
        obs = plant.step_contact(duplicate(arr(path,"action_clipped")[j]), sides, phase(j))
        prefix_failures.append(int(obs["first_fail_substep"][0]))
    external = data.qfrc_bias if plant.servo_bias is None else plant.servo_bias
    prior = external[:].clone()
    # Reset just the other world. The continuous lane must keep its controller input.
    other = torch.tensor([1],device=plant.device)
    plant.reset(duplicate(arr(path,"qpos")[frame-10])[:1], duplicate(arr(path,"qvel")[frame-10])[:1], other)
    external = data.qfrc_bias if plant.servo_bias is None else plant.servo_bias
    torch.testing.assert_close(external[0],prior[0],rtol=0,atol=0)
    with np.load(folder/"dynamics.npz") as f:
        action = duplicate(f["action"][0,0])
    target = (action*plant.scale+plant.offset)*plant.finger_factor
    solve = plant.sim.step
    solved = []
    def observe():
        solve()
        solved.append(data.qfrc_bias[0].clone())
    plant.sim.step = observe
    t0=float(data.time[0])
    result=plant.step_contact(action,sides,phase(frame),record=True)
    plant.sim.step = solve
    ctrl=result["substeps"]["ctrl"][0][:,plant.actuator_ids]
    bias=torch.stack(solved)
    stride=clock.servo_stride
    used=torch.cat((prior[0:1],bias[::stride][:-1]),0)[:,plant.dof]
    predicted=(target[0]+used*plant.bias_gain).repeat_interleave(stride,dim=0)
    torch.testing.assert_close(ctrl,predicted,atol=2e-6,rtol=2e-6)
    torch.testing.assert_close(ctrl,ctrl[::stride].repeat_interleave(stride,0),rtol=0,atol=0)
    n=int(result["physics_steps"][0])
    elapsed=float(data.time[0])-t0
    assert n==clock.policy_steps==len(solved) and abs(elapsed-.02)<3e-5
    row=meta["row"]
    ref=FrozenDoorReference.from_episode(row["formal_ref"],model)
    ph=SEGMENTS[row["segment"]][1]
    judge=ContactEvents(model,settings("push" if side=="push" else "mobile",1),side,ref,phases=ph,
        start_step=row["formal_start"],score_until_step=ref.phase_bounds[ph[-1]][1]-row["formal_start"])
    assert judge.ticks(.2)==10*n and judge.offset==stride*row["formal_start"]
    return dict(side=side,**clock.metadata(),physical_time_20ms=elapsed,ticks=n,
        prefix_fail_substeps=prefix_failures,prefix_accepted=not any(prefix_failures),
        measured_first_fail_substep=int(result["first_fail_substep"][0]),ctrl_max_abs_error=float((predicted-ctrl).abs().max()),
        all_intermediate_ctrl_bitwise_held=True,neighbor_reset_external_bias_bitwise_preserved=True,
        internal_bias_max_change_within_policy=float((bias[1:]-bias[:-1]).abs().max()),
        six_newton_threshold_n=plant.cfg["grip_net_force_limit_n"])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dt",type=float,nargs="+",required=True)
    args=parser.parse_args()
    for dt in args.dt:
        checks=[verify(dt,s) for s in ("pull","push")]
        tag=round(dt*1e6)
        (OUT/f"training_clock_{tag}us.json").write_text(json.dumps(checks,indent=2,allow_nan=False)+"\n")
        print(tag,[(x["ctrl_max_abs_error"],x["prefix_accepted"]) for x in checks],flush=True)
