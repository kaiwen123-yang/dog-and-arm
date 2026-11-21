"""Compare GPU contact reductions with native P6 measurement on the same solved data."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

import mujoco as mj
import mujoco_warp as mjw
from mjlab.sim import Simulation
import numpy as np
import torch

from learning.b0.physics import ContactMeter, make_model
from learning.b0.research_env import ResearchPlant
from learning.b0.warp_audit import WarpFreeAudit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    m = make_model()
    plant = ResearchPlant(m, 3, "cuda:0")
    audit = WarpFreeAudit(m, plant.sim)
    q = np.tile(m.key("home").qpos, (3, 1))
    q[1, 2] += 0.8
    q[2, 2] = 0.12
    q[2, 3:7] = [0, 1, 0, 0]
    initial = torch.as_tensor(q, device="cuda", dtype=torch.float32)
    plant.reset(initial, initial.new_zeros((3, m.nv)))
    audit.reset()
    meter = ContactMeter(m, "preview_floor")
    copied = mj.MjData(m)
    frames = []
    max_wheel_error = max_door_error = 0.
    # Keep the actual initial targets. These checks intentionally include failed worlds.
    for step in range(1, 76):
        plant.data.ctrl[:, plant.actuator_ids] = (
            initial[:, plant.mapping.q] + plant.data.qfrc_bias[:, plant.dof] * plant.bias_gain
        )
        plant.sim.step()
        audit.step()
        if step not in (1, 21, 49, 50, 51, 75):
            continue
        worlds = []
        for i in range(3):
            mjw.get_data_into(copied, m, plant.sim.wp_data, world_id=i)
            solved = meter.measure(copied)
            wheels = audit.wheel_loads_n[i].cpu().numpy()
            max_wheel_error = max(max_wheel_error, np.abs(wheels - solved.normal).max())
            max_door_error = max(max_door_error,
                                 abs(float(audit.door_force_norm_sum_n[i]) - solved.force_norm_sum))
            worlds.append(dict(world=i, wheel_loads_n=wheels.tolist(),
                               host_solved_wheels_n=solved.normal.tolist(),
                               unexpected=list(solved.unexpected),
                               peak_other_normal_n=float(audit.peak_other_normal_n[i]),
                               overflow_bits=int(audit.overflow_bits[i]),
                               unloaded_steps=int(audit.unloaded_steps[i]),
                               failed=bool(audit.invalid[i])))
        frames.append(dict(step=step, worlds=worlds))

    # Force a real capacity warning in a separate diagnostic solver. The production
    # model and production solver capacities do not change.
    small = Simulation(1, replace(plant.sim.cfg, nconmax=20, njmax=62), model=make_model())
    small_audit = WarpFreeAudit(small.mj_model, small)
    small.reset()
    low = initial[:1].clone()
    low[:, 2] = -.3
    small.data.qpos[:] = low
    small.forward()
    small.step()
    small_audit.step()
    overflow = dict(nacon=int(small.data.nacon[0]), naconmax=small.wp_data.naconmax,
                    ncollision=int(small.data.ncollision[0]), nefc=int(small.data.nefc[0]),
                    njmax=small.wp_data.njmax, overflow_bits=int(small_audit.overflow_bits[0]),
                    failed=bool(small_audit.invalid[0]))
    record = dict(mujoco=mj.__version__, worlds=3, physical_steps=75, timestep_s=m.opt.timestep,
                  comparison="same solved Warp contacts copied into MjData for native mj_contactForce",
                  initial_poses=["nominal", "root z+0.8m", "root inverted z=0.12m"],
                  max_wheel_load_absolute_difference_n=float(max_wheel_error),
                  max_door_force_norm_sum_absolute_difference_n=float(max_door_error),
                  frames=frames, forced_overflow=overflow)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, indent=2) + "\n")
    if (max_wheel_error > .001 or not overflow["overflow_bits"] or not overflow["failed"]
            or frames[2]["worlds"][1]["failed"] or not frames[3]["worlds"][1]["failed"]
            or "nonwheel_ground" not in frames[0]["worlds"][2]["unexpected"]
            or not frames[0]["worlds"][2]["failed"]):
        raise RuntimeError(f"Contact audit comparison failed, see {args.output}")


if __name__ == "__main__":
    main()
