"""Replay nominal teacher commands from the 60 frozen free-motion development starts on CPU."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.b0.evaluate import PROTOCOL, evaluate_cases  # noqa: E402
from learning.b0.physics import make_model  # noqa: E402
from learning.b0.reference import load_episode  # noqa: E402


def replay(reference_type, source):
    episode_dir = source / reference_type
    meta = json.loads((episode_dir / 'metadata.json').read_text())
    if not (meta['held_action_replay'] and meta['finished'] and meta['success']):
        raise ValueError(f'{reference_type} lacks a complete held-action teacher recording')
    episode = load_episode(episode_dir)
    commands = episode['action_clipped']
    if commands.shape != (len(episode['qpos']) - 1, 23) or np.any(np.abs(commands) > 1):
        raise ValueError(f'{reference_type} has invalid canonical commands')

    def recorded_commands(_name, _reference):
        def command(_actual_qpos, _actual_qvel, frame):
            return commands[frame]
        return command

    # Reuse the identical native substep-audited plant, reset and trajectory scorer
    # used by the frozen Actor. Only its source of post-clamp actions changes.
    with TemporaryDirectory() as directory:
        staging = Path(directory) / reference_type
        evaluate_cases(make_model(), {reference_type: episode}, recorded_commands, staging,
                       seed=None, checkpoint='recorded teacher actions only')
        result = []
        for case in PROTOCOL['cases']:
            raw = json.loads((staging / f"{reference_type}_{case['id']}.json").read_text())
            effects, metrics = raw['observed_motion'], raw['metrics']
            result.append(dict(reference=reference_type, case=case['id'],
                               dx_m=case['dx_m'], dy_m=case['dy_m'], dyaw_deg=case['dyaw_deg'],
                               teacher_command_pass=raw['passed'], failures='|'.join(raw['failures']),
                               physics_steps=raw['physics_steps'], expected_steps=raw['expected_physics_steps'],
                               duration_s=raw['physical_duration_s'], scored_frames=raw['scored_frames'],
                               **{k: (metrics or {}).get(k) for k in (*PROTOCOL['thresholds'],
                                   'wheel_speed_rmse_rad_s', 'gripper_width_rmse_m')},
                               final_speed_xy_m_s=(effects or {}).get('final_speed_xy_m_s')))
        return result


def check_reference_keys(source, names, destination):
    """Check exact collisions in the 480 floats already visible in the O1 Actor goal."""
    windows, labels = [], []
    for name in names:
        ep = load_episode(source / name)
        frames = np.concatenate([ep['qpos'][:, 7:31], ep['qvel'][:, 6:30]], axis=1).astype(np.float32)
        # Pinned motion_goal_window: t + {0,5,...,45}, clipped to the final reference frame.
        n = len(ep['action_clipped'])
        index = np.minimum(np.arange(n)[:, None] + 5*np.arange(10), len(frames)-1)
        windows.extend(frames[index].reshape(n, -1))
        labels.extend(ep['action_clipped'])
    targets = np.asarray(labels)
    _, first, inverse, frequency = np.unique(np.asarray(windows), axis=0, return_index=True,
                                              return_inverse=True, return_counts=True)
    recovered = targets[first[inverse]]
    discrepancy = np.abs(recovered - targets).max(axis=1)
    duplicate_counts = frequency[frequency > 1]
    report = dict(source='Fixed O1 representations.motion_goal_window and B0 MotionBank ordering',
                  feature='10 clipped fixed-reference frames at offsets 0,5,...,45, 24 joint positions + 24 joint velocities per frame, float32. No case ID, world pose, or explicit clock in the key.',
                  sample_count=len(targets), unique_keys=len(first), duplicate_keys=len(duplicate_counts),
                  duplicate_key_multiplicities=duplicate_counts.tolist(), additional_duplicate_rows=int(len(targets)-len(first)),
                  conflicting_rows=int(np.sum(discrepancy != 0)),
                  max_abs_recovered_canonical_action_error=float(discrepancy.max()),
                  scope='Exact identity on these three given reference clips. No learned decoder, noise robustness or unseen-reference claim.')
    with destination.open('x') as file:
        file.write(json.dumps(report, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if mj.__version__ != '3.3.0':
        raise RuntimeError('Run with bash scripts/project_env.sh python to use native 3.3.0')
    args.output.mkdir(parents=True, exist_ok=False)
    refs = PROTOCOL['references']
    with ProcessPoolExecutor(max_workers=len(refs)) as pool:
        grouped = list(pool.map(replay, refs, [args.reference_root] * len(refs)))
    rows = [r for group in grouped for r in group]
    with (args.output / 'cases.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_reference = {}
    for name, group in zip(refs, grouped):
        metrics = {m: dict(min=min(row[m] for row in group), max=max(row[m] for row in group),
                           worst_case=max(group, key=lambda row: row[m])['case'])
                   for m in PROTOCOL['thresholds'] if all(row[m] is not None for row in group)}
        by_reference[name] = dict(teacher_command_passes=sum(row['teacher_command_pass'] for row in group),
                                  attempted=len(group), full_length=sum(row['physics_steps'] == row['expected_steps']
                                                                       for row in group),
                                  failures={row['case']:row['failures'] for row in group if row['failures']},
                                  observed_metric_ranges=metrics)
    summary = dict(test='open-loop replay of one nominal 23-channel teacher command sequence per reference',
                   backend=f'native MuJoCo {mj.__version__} CPU', reference_root=str(args.reference_root),
                   protocol=PROTOCOL['version'], split=PROTOCOL['split'], per_type_target=PROTOCOL['pass_count_per_reference'],
                   pass_thresholds=PROTOCOL['thresholds'], physics_dt_s=PROTOCOL['physics_dt_s'],
                   policy_dt_s=PROTOCOL['policy_dt_s'], initial_conditions='fixed F01-F20, original world reference unchanged',
                   inputs='Reference type and frame index only. All 20 initial conditions receive identical commands for a given type. Fixed servo/bias uses live state at 500 Hz.',
                   learning_policy_used=False, teacher_replanned=False, real_simulated_substeps=sum(r['physics_steps'] for r in rows),
                   by_reference=by_reference)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    check_reference_keys(args.reference_root, refs, args.output / 'reference_keys.json')
    for kind, stat in by_reference.items():
        print(f"{kind}: {stat['teacher_command_passes']}/{stat['attempted']}", flush=True)


if __name__ == '__main__':
    main()
