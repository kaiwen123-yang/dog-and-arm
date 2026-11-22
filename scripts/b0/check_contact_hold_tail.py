"""Diagnose a truncated teacher hold by integrating its last command on the same Warp world."""
import argparse
import json
from pathlib import Path

import numpy as np

from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from learning.b0.physics import ActionMap, build
from scripts.b0.eval_contact_segments import SEGMENTS, WarpSingleWorld, ZERO, dump
from scripts.b0.register_contact_dev import prefix_history, valid_initial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--references', type=Path, default=Path('results/raw_large/b0/contact_held_r1'))
    args = parser.parse_args()
    original = json.loads(args.result.read_text())
    if original['passed'] or original['first_failure']['reason'] != 'reference_exhausted':
        parser.error('Supply a truncated teacher positive-control result')
    if original['backend'] != 'warp' or 'teacher' not in original['action_source']:
        parser.error('This check diagnoses the Warp fixed-action teacher control')
    _, phases = SEGMENTS[original['segment']]
    if original['first_failure']['phase'] != 'hold' or phases[-1] != 'hold' or original['perturbation'] != ZERO:
        parser.error('Supply a nominal control truncated during its final three-second grip hold')
    side = original['side']
    folder = args.references / original['episode']
    cfg = json.loads((folder / 'config.json').read_text())
    model = build(cfg)
    ref = FrozenDoorReference.from_episode(folder, model)
    start, stop = original['start_substep'], original['reference_phase_end_substep']
    judge = ContactEvents(model, cfg, side, ref, phases=phases, hold_seconds=3., start_step=start)
    plant = WarpSingleWorld(model, 'cuda:0')
    data, _, initial = prefix_history(model, cfg, folder, side, start, ZERO, integrator=plant)
    if not valid_initial(initial, original['segment'], cfg):
        raise ValueError('Physical contact reconstruction failed')
    mapping = ActionMap(model)
    actions = np.load(folder/'action_clipped.npy', mmap_mode='r')
    at_cut = None
    tail = []
    while not judge.passed and judge.failure is None:
        sub = start + judge.step
        # Preserve the previous nominal action even when the cut falls between
        # two policy boundaries. No frame from release or another clip is used.
        frame = min(sub, stop-1) // 10
        servo = (mapping.offset + mapping.scale * actions[frame]) * mapping.finger_factor
        q0 = data.qpos.copy()
        v0 = data.qvel.copy()
        plant.step(data, servo)
        judge.observe(data, None, q0, v0)
        if sub + 1 == stop:
            at_cut = dict(good=judge.good, best=judge.peak_ready_steps.get(phases[-1], 0),
                          last_not_ready=judge.last_not_ready.get(phases[-1]),
                          door_deg=float(np.rad2deg(data.qpos[judge.hinge_q])))
        if sub >= stop:
            tail.append(dict(step=judge.step, frame_index=frame, **judge.latest))
    if at_cut is None:
        raise ValueError('Repeat terminated before the original cut')
    if (abs(at_cut['door_deg'] - original['final_door_deg']) > .001
            or at_cut['good'] != original['first_failure']['readiness']['current']):
        raise ValueError('Before-cut replay disagrees with the frozen teacher control')
    out=dict(source=str(args.result),episode=original['episode'],side=side,segment=original['segment'],
             use='separate physical timing diagnostic; original fixed-reference score is unchanged',
             nominal_prefix_substeps=100,dt_s=.002,required_hold_steps=1500,
             hold_phase_timeout_s=cfg['phase_timeout_s'][phases[-1]],
             reference_cut_absolute_step=stop,original_good_at_cut=original['first_failure']['readiness']['current'],
             repeated_cut=at_cut,extra_steps=len(tail),extra_seconds=.002*len(tail),
             passed_extended_physical_hold=judge.passed,first_physical_failure=judge.failure,
             observations_after_cut=tail,capacity=plant.capacity())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    dump(args.output,out)


if __name__ == '__main__':
    main()
