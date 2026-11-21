"""Integrate the passive-door scene on both CPU and pinned mjlab, on identical commands."""
import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
import torch

from learning.b0.physics import NativePlant, make_model
from learning.b0.research_env import ResearchPlant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worlds', type=int, default=4)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    m = make_model()
    robot = NativePlant(m)
    q = m.key('home').qpos.copy()
    v = np.zeros(m.nv)
    robot.reset(q, v)
    a = robot.mapping
    initial = q[a.q].copy()
    initial[-1] *= 2
    initial[12:16] = 0
    spec = dict(mujoco=mujoco.__version__, worlds=args.worlds, nq=m.nq, nv=m.nv,
                nu=m.nu, neq=m.neq, timestep=m.opt.timestep, mapping=a.describe(m), stages=[])
    args.output.write_text(json.dumps(spec, indent=2))
    try:
        gpu = ResearchPlant(make_model(), args.worlds, 'cuda:0')
        tensor = lambda x: torch.as_tensor(x, device='cuda', dtype=torch.float32).expand(args.worlds, -1)
        gpu.reset(tensor(q), tensor(v))
        for phase in ('stand', 'extend_and_close', 'roll', 'brake_and_open'):
            failed = False
            for i in range(50):
                target = initial.copy()
                if phase in ('extend_and_close', 'roll'):
                    target[17] += .12 * (min(1, i / 30) if phase == 'extend_and_close' else 1)
                    target[-1] = .02
                if phase == 'roll':
                    target[12:16] = [.6, .6, -.6, -.6]
                action = ((target - a.offset) / a.scale).clip(-1, 1)
                status = robot.step(action)
                bad = gpu.step(tensor(action))
                failed |= bool(bad.any())
                if status['failure_reason']:
                    break
            w = gpu.data.qpos[0].cpu().numpy()
            spec['stages'].append(dict(phase=phase, steps=i+1, native_end=robot.data.qpos.tolist(),
                         warp_end=w.tolist(), root_difference_m=float(np.linalg.norm(w[:3]-robot.data.qpos[:3])),
                         warp_invalid=failed, native_failure=status['failure_reason']))
            if status['failure_reason'] or failed:
                break
    except Exception as exc:
        spec['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        args.output.write_text(json.dumps(spec, indent=2)+'\n')


if __name__ == '__main__':
    main()
