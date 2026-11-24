"""Check partial-terminal tracking rewards at the new physics times against native interpolation."""
import json
from pathlib import Path
from types import SimpleNamespace

import mujoco
import numpy as np
import torch

from learning.b0.contact_clock import ContactClock
from learning.b0.contact_model import ContactRepresentation, contact_state
from learning.b0.contact_sampling import SamplerReference
from learning.b0.model import full_state
from learning.b0.physics import make_model


@torch.no_grad()
def main():
    device = "cuda:0"
    def tensor(value):
        return torch.as_tensor(np.array(value), dtype=torch.float32, device=device)

    clock = ContactClock(.00025)
    folder = Path("results/raw_large/b0/dynamics_20261124/response/pull_0_validation_grip_hold")
    receipt = json.loads((folder/"receipt.json").read_text())
    path, frame = Path(receipt["row"]["path"]), receipt["frame"]
    model = make_model()
    model.opt.timestep = clock.physics_dt
    rep = ContactRepresentation(model, device)
    rep.reward_coordinates = "fixed_effort"
    bank = SimpleNamespace(motion_starts=torch.tensor([0],device=device),
                           motion_ends=torch.tensor([frame+2],device=device))
    sampler = SamplerReference([path],bank,device,clock)
    ticks = [1,3,8,12,48,79,80,0]
    with np.load(folder/"substeps.npz") as steps, np.load(folder/"dynamics.npz") as dynamics, np.load(folder/"start.npz") as start:
        indices = np.maximum(ticks,1)-1
        q = tensor(steps["qpos_post"][0,0,indices])
        v = tensor(steps["qvel_post"][0,0,indices])
        action = tensor(dynamics["action"][0,0]).expand(len(ticks),-1)
        previous = tensor(start["previous"]).expand_as(action)
    ref_q = np.load(path/"substeps/qpos.npy", mmap_mode="r")
    ref_v = np.load(path/"substeps/qvel.npy", mmap_mode="r")
    positions, velocities = [], []
    for tick in ticks:
        interval, part = divmod(tick,clock.servo_stride)
        i = frame*clock.reference_ticks + interval
        weight = part / clock.servo_stride
        pose = ref_q[i].astype(float)
        vel = ref_v[i]
        if part:
            tangent = np.empty(model.nv)
            mujoco.mj_differentiatePos(model,tangent,1.,pose,ref_q[i+1].astype(float))
            mujoco.mj_integratePos(model,pose,tangent,weight)
            vel = (1-weight)*vel + weight*ref_v[i+1]
        positions.append(pose)
        velocities.append(vel)
    rq, rv = tensor(positions), tensor(velocities)
    state = full_state(rq,rv)
    target = rep.fk(rq[:,:3],rq[:,3:7],rq[:,7:31],state[:,31:34],state[:,34:37],rv[:,6:30])
    measured = contact_state(q,v)
    rr = rep.represent(measured)
    complete = rep.compute_wm_reward_from_reference(rr,measured[:,:7],rep.joint_state(rr),action,previous,*target)
    stop = torch.tensor(ticks,device=device)
    actual = sampler.rewards(rep,complete,torch.full_like(stop,frame),
        torch.ones_like(stop,dtype=torch.bool),stop,q,v,action,previous)
    expected = torch.where((stop>0)&(stop<clock.policy_steps),complete*stop/clock.policy_steps,complete)
    errors = (actual-expected).abs()
    torch.testing.assert_close(actual,expected,rtol=0,atol=2e-6)
    out = Path("results/b0/standard_dynamics_20261124/partial_terminal_reward_clock.json")
    out.write_text(json.dumps(dict(source=str(path),frame=frame,physical_stop_source=str(folder),ticks=ticks,
        times_s=[t*clock.physics_dt for t in ticks],registered_reference_s=clock.servo_dt,
        recomputed_mujoco_geodesic_abs_reward_errors=errors.tolist(),max_abs_error=float(errors.max()),
        signed_dt_weighted_values=actual.tolist()),indent=2)+"\n")


if __name__ == "__main__":
    main()
