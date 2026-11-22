"""Compare the contact collector against P6's CPU reading of identical solved Warp contacts."""
import argparse
import json
from pathlib import Path

import mujoco as mj
import mujoco_warp as mjw
import numpy as np
import torch

from learning.b0.contact_warp import ContactPlant, PHASE_ID, REASONS
from learning.b0.physics import ContactMeter, make_model


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--worlds', type=int, default=128)
    args=p.parse_args()
    if args.output.exists() or args.worlds < 2:
        p.error('New output file and at least two worlds required')
    m = make_model()
    plant = ContactPlant(m, args.worlds, 'cuda:0')
    copies = [mj.MjData(m) for _ in range(2)]
    meters = [ContactMeter(m,'preview_floor',name) for name in ('front','back')]
    data = []
    for side in ('pull','push'):
        folder = args.data / (side+'_5_train')
        phase = np.load(folder / 'phase.npy')
        names = json.loads((folder / 'metadata.json').read_text())['phases']
        k = np.flatnonzero(phase == names.index('hold'))[10]
        data.append((np.load(folder/'qpos.npy')[k], np.load(folder/'qvel.npy')[k],
                     np.load(folder/'action_clipped.npy')[k:k+5], int(k)))
    def lanes(values):
        arr = torch.tensor(np.stack(values), device='cuda', dtype=torch.float32)
        return arr[bits.long()]
    bits = torch.arange(args.worlds, device='cuda') % 2
    phases = torch.full_like(bits, PHASE_ID['hold'])
    plant.reset(lanes([d[0] for d in data]), lanes([d[1] for d in data]))
    actions = lanes([d[2] for d in data])
    errors = {k:0. for k in ('finger_N','wheel_N','force_vector_N','norm_sum_N','wheel_slip_m_s')}
    values, failures = [], []
    overflows = set()
    for step in range(5):
        r = plant.step_contact(actions[:,step], bits, phases, record=True)
        traces = r['substeps']
        overflows.update(r['overflow'].unique().tolist())
        failures.append(dict(step=step+1, counts=torch.bincount(r['reason'].long(),minlength=len(REASONS)).tolist()))
        for w, (host, meter) in enumerate(zip(copies,meters)):
            mjw.get_data_into(host,m,plant.sim.wp_data,world_id=w)
            measure = meter.measure(host)
            def arr(name):
                return traces[name][w,-1].cpu().numpy()
            ref_slip = np.max(np.hypot(np.nan_to_num(measure.slip_long), np.nan_to_num(measure.slip_lat)))
            comparison = dict(finger_N=(arr('finger_load_N'),measure.finger_normal),wheel_N=(arr('wheel_load_N'),measure.normal),
                              force_vector_N=(arr('door_robot_force_N'),measure.door_force),
                              norm_sum_N=(arr('door_force_norm_sum_N'),measure.force_norm_sum),
                              wheel_slip_m_s=(arr('wheel_slip_m_s'),ref_slip))
            for name, (gpu,cpu) in comparison.items():
                errors[name] = max(errors[name],float(np.max(np.abs(gpu-cpu))))
            values.append(dict(world=w,step=step+1,side=('pull','push')[w],gpu_finger_N=arr('finger_load_N').tolist(),
                               cpu_finger_N=measure.finger_normal.tolist(),net_door_force_N=arr('door_robot_force_N').tolist()))
    outcome=dict(worlds=args.worlds,policy_steps=5,world_substeps=args.worlds*50,
                 comparison='two representatives at each final substep, CPU meter on same solved constraints',
                 init=[d[3] for d in data],dt=.002,buffer_overflow_bits=sorted(overflows),
                 reason_order=list(REASONS),failures=failures,max_abs=errors,comparisons=values)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outcome,indent=2)+'\n')
    if any(v>1e-3 for v in errors.values()) or overflows!={0} or not any(all(f>0.01 for f in row['cpu_finger_N']) for row in values):
        raise RuntimeError(f'Mixed-side contact audit failed. See {args.output}')
    print(errors, flush=True)


if __name__=='__main__':
    main()
