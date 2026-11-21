"""Short native controlled experiments on the first no-contact reference window."""
import csv
import json
from pathlib import Path

import numpy as np

from .evaluate import ErrorMeasures
from .physics import NativePlant


GROUPS = dict(leg=slice(0, 12), wheel=slice(12, 16), arm=slice(16, 22), jaw=slice(22, 23))


def diagnose_initial_actions(model, ref, substep_q, policy_factory, output_dir, raw_dir):
    # The first 0.8 s of support is nominal stationary hold before the extension ramp.
    duration = 0.8
    dt = float(model.opt.timestep)
    expected = round(duration / dt)
    reference_q = np.asarray(substep_q[:expected + 1])
    compare = ErrorMeasures(model)
    tcp_ref = compare.tcp_world(reference_q)
    modes = ['closed_loop', 'hold_first_output', 'all_home',
             *['hold_' + g for g in GROUPS], *['only_' + g for g in GROUPS]]
    home = ref['action_clipped'][0]
    if np.max(np.abs(ref['action_clipped'][:round(duration / .02)] - home)) > 1.e-9:
        raise ValueError('This ablation requires a stationary reference-command segment')
    summary, origins = [], {}
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=False, parents=True)
    raw_dir.mkdir(exist_ok=False, parents=True)
    with (raw_dir / 'per_substep.csv').open('w') as f:
        timeseries = csv.writer(f)
        timeseries.writerow(['mode', 'time_s', 'supported_wheels', 'min_wheel_normal_N', 'tilt_deg',
                             'min_arm_margin_rad', 'max_effort_fraction', 'tcp_error_m'])
        for mode in modes:
            plant = NativePlant(model)
            plant.reset(ref['qpos'][0].copy(), ref['qvel'][0].copy())
            mapping = plant.mapping
            actor = policy_factory('support', ref)
            first = actor(plant.data.qpos.copy(), plant.data.qvel.copy(), 0)
            physical_first = mapping.scale * first + mapping.offset
            physical_home = mapping.scale * home + mapping.offset
            if len(origins) == 0:
                for g, sl in GROUPS.items():
                    origins[g] = dict(joints=mapping.names[sl], unit=dict(leg='rad', wheel='rad/s',
                                    arm='rad', jaw='m total opening')[g],
                                    normalized_actor=first[sl].tolist(), normalized_home=home[sl].tolist(),
                                    physical_actor=physical_first[sl].tolist(), physical_home=physical_home[sl].tolist(),
                                    physical_delta=(physical_first[sl] - physical_home[sl]).tolist())
            step = 0
            first_unloaded = first_support = first_sat = first_tilt = None
            unloaded = max_unloaded = peak_effort = max_tilt = max_tcp_err = 0.
            sat_time = np.zeros(model.nu)
            max_saturated = 0.
            end_err = 0.
            max_departure = np.zeros(4)
            failure = None

            def record(d, c):
                nonlocal step, first_unloaded, first_support, first_sat, first_tilt
                nonlocal unloaded, max_unloaded, peak_effort, max_tilt, max_tcp_err, max_saturated, end_err
                step += 1
                t = step * dt
                count = int(c.supported.sum())
                unloaded = unloaded + dt if count != 4 else 0.
                if count != 4 and first_unloaded is None:
                    first_unloaded = t
                if count == 4 and first_support is None:
                    first_support = t
                max_unloaded = max(unloaded, max_unloaded)
                effort = np.abs(d.actuator_force) / plant.limit
                saturating = effort >= .98
                sat_time[:] = np.where(saturating, sat_time + dt, 0.)
                max_saturated = max(max_saturated, sat_time.max())
                if saturating.any() and first_sat is None:
                    first_sat = t
                peak_effort = max(peak_effort, effort.max())
                w, x, y, z = d.qpos[3:7]
                roll = np.arctan2(2*(w*x+y*z), 1-2*(x*x+y*y))
                pitch = np.arcsin(np.clip(2*(w*y-z*x), -1., 1.))
                tilt = float(np.rad2deg(max(abs(roll), abs(pitch))))
                if tilt >= 5 and first_tilt is None:
                    first_tilt = t
                max_tilt = max(max_tilt, tilt)
                arm = d.qpos[mapping.q[16:22]]
                lo, hi = plant.arm_range.T
                margin = np.minimum(arm-lo, hi-arm).min()
                tcp = compare.tcp_world(d.qpos[None])[0]
                end_err = float(np.linalg.norm(tcp - tcp_ref[step]))
                max_tcp_err = max(max_tcp_err, end_err)
                timeseries.writerow([mode, t, count, c.normal.min(), tilt, margin, effort.max(), end_err])

            for k in range(round(duration / .02)):
                if mode == 'all_home':
                    actual = home.copy()
                elif mode == 'hold_first_output':
                    actual = first.copy()
                else:
                    # For masked-policy runs the Actor still observes its measured
                    # states. Feed back the command actually applied on the last tick.
                    actual = first.copy() if k == 0 else actor(plant.data.qpos.copy(), plant.data.qvel.copy(), k)
                    if mode.startswith('hold_'):
                        sl = GROUPS[mode.removeprefix('hold_')]
                        actual[sl] = home[sl]
                    if mode.startswith('only_'):
                        sl = GROUPS[mode.removeprefix('only_')]
                        frozen = home.copy()
                        frozen[sl] = actual[sl]
                        actual = frozen
                difference = (actual - home) * mapping.scale
                max_departure = np.maximum(max_departure, [abs(difference[sl]).max() for sl in GROUPS.values()])
                if mode not in ('all_home', 'hold_first_output'):
                    actor.applied(actual)
                result = plant.step(actual, record)
                failure = result['failure_reason']
                if failure:
                    break
            summary.append(dict(mode=mode, steps=step, physical_duration_s=step*dt, first_failure=failure,
                                wheel_first_unloaded_s=first_unloaded, wheel_first_all_loaded_s=first_support,
                                longest_underloaded_s=max_unloaded, tilt_first_5deg_s=first_tilt, max_tilt_deg=max_tilt,
                                first_saturation_s=first_sat, longest_single_actuator_saturation_s=max_saturated,
                                peak_effort_fraction=peak_effort, max_tcp_error_m=max_tcp_err, end_tcp_error_m=end_err,
                                max_abs_command_departure_per_group=dict(zip(GROUPS, max_departure.tolist()))))
    (output_dir/'initial_action.json').write_text(json.dumps(origins, indent=2) + '\n')
    (output_dir/'results.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    with (output_dir/'results.csv').open('w') as f:
        fields = [key for key in summary[0] if key != 'max_abs_command_departure_per_group']
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(summary)


def record_action_coverage(references, result_dir, policy_data):
    """Compare initial issued commands with teacher support and actual replay windows."""
    teacher = np.concatenate([ep['physical_target'] for ep in references.values()])
    lo, hi = teacher.min(axis=0), teacher.max(axis=0)
    initial = json.loads((result_dir / 'initial_action.json').read_text())
    grouped = {}
    for group, sl in GROUPS.items():
        values = initial[group]
        command = np.asarray(values['physical_actor'])
        outside = (command < lo[sl] - 1.e-6) | (command > hi[sl] + 1.e-6)
        grouped[group] = dict(outside_teacher_range_joints=[name for name, out in
                              zip(values['joints'], outside) if out],
                              zero_teacher_range_count=int(np.sum((hi - lo)[sl] < 1.e-6)),
                              lo=lo[sl].tolist(), hi=hi[sl].tolist())
    report = dict(teacher_unique_transitions=len(teacher), initial_action_vs_teacher=grouped)
    segments = sorted(policy_data.glob('policy_transitions_*'))[:2]
    if segments:
        ids, dones = [], []
        next_offset = 0
        for path in segments:
            if int(path.name.rsplit('_', 1)[-1]) != next_offset:
                break
            episode_id = np.load(path / 'episode_id.npy')
            ids.append(episode_id)
            dones.append(np.load(path / 'terminated.npy') | np.load(path / 'truncated.npy'))
            next_offset += episode_id.size
        if ids:
            ids = np.concatenate(ids)
            windows = (np.lib.stride_tricks.sliding_window_view(ids, 8, axis=0) if len(ids) >= 8
                       else np.empty((0, ids.shape[1], 8), dtype=ids.dtype))
            report['first_contiguous_online_data'] = dict(
                policy_steps_per_lane=len(ids), physical_transitions=int(ids.size),
                episode_ids=int(np.unique(ids).size), ended_episodes=int(np.concatenate(dones).sum()),
                complete_8_state_windows=int(np.all(windows == windows[:, :, :1], axis=-1).sum()),
                all_8_state_start_slots=int(windows.shape[0]*windows.shape[1]))
    (result_dir / 'teacher_coverage.json').write_text(json.dumps(report, indent=2) + '\n')
