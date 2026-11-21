"""Physical tracking and open-loop prediction scores for the free-motion gate."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import mujoco as mj
import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = json.loads((ROOT / 'config/b0/eval_cases.json').read_text())


def case_initial_qpos(model, qpos, case):
    """Change only the initial free-root XY and heading, in world coordinates."""
    initial = np.array(qpos, dtype=np.float64, copy=True)
    root = int(model.joint('m1_floating_base').qposadr[0])
    initial[root:root + 2] += [case['dx_m'], case['dy_m']]
    half_angle = np.deg2rad(case['dyaw_deg']) / 2
    yaw_quat = np.array([np.cos(half_angle), 0., 0., np.sin(half_angle)])
    orientation = np.empty(4)
    mj.mju_mulQuat(orientation, yaw_quat, initial[root + 3:root + 7])
    initial[root + 3:root + 7] = orientation
    return initial


class ErrorMeasures:
    def __init__(self, model):
        self.model = model
        self.fk_data = mj.MjData(model)
        self.tcp = model.site('p4_grasp').id
        self.root = int(model.joint('m1_floating_base').qposadr[0])
        self.root_dof = int(model.joint('m1_floating_base').dofadr[0])
        mapping = yaml.safe_load((ROOT / 'description/joint_map.yaml').read_text())
        self.legs = [name for name in mapping['base_joints'] if name not in mapping['wheel_joints']]
        self.angles = self.legs + mapping['arm_joints']
        hinge_ids = [model.joint(name).id for name in self.angles]
        self.q = model.jnt_qposadr[hinge_ids]
        self.dof = model.jnt_dofadr[hinge_ids]
        self.ranges = np.diff(model.jnt_range[hinge_ids], axis=1).ravel()
        self.wheels = [int(model.joint(name).dofadr[0]) for name in mapping['wheel_joints']]
        self.fingers = [int(model.joint(name).qposadr[0]) for name in mapping['finger_joints']]
        self.door_q = int(model.joint('door_single_hinge').qposadr[0])
        self.door_v = int(model.joint('door_single_hinge').dofadr[0])

    def tcp_world(self, qpos):
        """Recompute the p4_grasp TCP from the state at the named boundary."""
        result = np.empty((len(qpos), 3))
        for i, position in enumerate(qpos):
            self.fk_data.qpos[:] = position
            mj.mj_kinematics(self.model, self.fk_data)
            result[i] = self.fk_data.site_xpos[self.tcp]
        return result

    def compare(self, est_q, est_v, ref_q, ref_v, est_tcp=None, ref_tcp=None):
        est_q, est_v, ref_q, ref_v = (np.asarray(x, dtype=np.float64) for x in
                                      (est_q, est_v, ref_q, ref_v))
        if (not len(ref_q) or est_q.shape != ref_q.shape or est_v.shape != ref_v.shape
                or est_q.shape != (len(ref_q), self.model.nq)
                or est_v.shape != (len(ref_q), self.model.nv)):
            raise ValueError('Actual and target qpos/qvel must be equal length, in model order')
        if est_tcp is None:
            est_tcp = self.tcp_world(est_q)
        if ref_tcp is None:
            ref_tcp = self.tcp_world(ref_q)
        est_tcp, ref_tcp = np.asarray(est_tcp), np.asarray(ref_tcp)
        if ref_tcp.shape != (len(ref_q), 3) or est_tcp.shape != ref_tcp.shape:
            raise ValueError('Expected world-frame p4_grasp XYZ at every sampled boundary')
        if not all(np.isfinite(a).all() for a in (est_q, est_v, ref_q, ref_v, est_tcp, ref_tcp)):
            raise ValueError('Nonfinite state or FK in error calculation')

        def rmse(x):
            return float(np.sqrt(np.mean(np.square(x))))

        def distance_rmse(x):
            return rmse(np.linalg.norm(x, axis=-1))

        qerr, verr = est_q - ref_q, est_v - ref_v
        p, v = self.root, self.root_dof
        eq = est_q[:, p + 3:p + 7]
        rq = ref_q[:, p + 3:p + 7]
        qnorms = np.linalg.norm(eq, axis=1) * np.linalg.norm(rq, axis=1)
        if np.any(qnorms < 1e-12):
            raise ValueError('Zero quaternion in error calculation')
        cosine = np.abs(np.einsum('ij,ij->i', eq, rq)) / qnorms
        angle = 2 * np.arccos(np.clip(cosine, 0., 1.))
        normalized = np.sqrt(np.mean(np.square(qerr[:, self.q] / self.ranges), axis=0))
        nlegs = len(self.legs)
        return {
            'root_position_rmse_m': distance_rmse(qerr[:, p:p + 3]),
            'root_orientation_rmse_deg': rmse(np.rad2deg(angle)),
            'root_linear_velocity_rmse_m_s': distance_rmse(verr[:, v:v + 3]),
            'root_body_angular_velocity_rmse_rad_s': distance_rmse(verr[:, v + 3:v + 6]),
            'tcp_position_rmse_m': distance_rmse(est_tcp - ref_tcp),
            'max_joint_range_normalized_rmse': float(normalized.max()),
            'per_joint_range_normalized_rmse': dict(zip(self.angles, normalized.tolist())),
            'leg_position_rmse_rad': rmse(qerr[:, self.q[:nlegs]]),
            'arm_position_rmse_rad': rmse(qerr[:, self.q[nlegs:]]),
            'finite_joint_velocity_rmse_rad_s': rmse(verr[:, self.dof]),
            'wheel_speed_rmse_rad_s': rmse(verr[:, self.wheels]),
            'gripper_width_rmse_m': rmse(qerr[:, self.fingers[0]] - qerr[:, self.fingers[1]]),
            'finger_equality_residual_rmse_m': rmse(qerr[:, self.fingers].sum(axis=-1)),
            'door_angle_rmse_deg': rmse(np.rad2deg(qerr[:, self.door_q])),
            'door_rate_rmse_rad_s': rmse(verr[:, self.door_v]),
        }


def score_tracking(model, observed, reference, *, physics_steps, failure_reason, measures=None):
    """Score only actual boundary samples. The caller supplies the first substep failure."""
    count = len(observed['qpos'])
    duration = len(reference['qpos']) - 1
    if not 1 <= count <= duration + 1:
        raise ValueError('Physical rollout frame count is inconsistent with reference')
    aligned_time = (len(observed['t']) == count and np.allclose(
        np.subtract(observed['t'], observed['t'][0]),
        np.subtract(reference['t'][:count], reference['t'][0]), rtol=0, atol=1e-6))
    measures = ErrorMeasures(model) if measures is None else measures
    # A substep failure can leave a terminal state at a fractional policy boundary.
    # Keep its timing/count but do not compare it with a later reference frame.
    aligned_count = count if aligned_time else count - 1
    if aligned_count < 1 or not np.allclose(
            np.subtract(observed['t'][:aligned_count], observed['t'][0]),
            np.subtract(reference['t'][:aligned_count], reference['t'][0]), rtol=0, atol=1e-6):
        raise ValueError('Reference and physical sample timestamps are misaligned')
    actual = slice(0, aligned_count)
    measured = None
    if all(np.isfinite(observed[k][actual]).all() for k in ('qpos', 'qvel', 'tcp_world')):
        measured = measures.compare(observed['qpos'][actual], observed['qvel'][actual],
                                    reference['qpos'][actual], reference['qvel'][actual],
                                    observed['tcp_world'][actual], reference['tcp_world'][actual])
    failures = [failure_reason] if failure_reason else []
    if not aligned_time:
        failures.append('partial_or_misaligned_final_interval')
    expected_steps = round(duration * PROTOCOL['policy_dt_s'] / PROTOCOL['physics_dt_s'])
    if count != duration + 1 or physics_steps != expected_steps:
        failures.append('incomplete_episode')
    if measured is None:
        failures.append('nonfinite_state')
    else:
        failures.extend(name for name, limit in PROTOCOL['thresholds'].items() if measured[name] > limit)
    q, v = observed['qpos'], observed['qvel']
    effect = None
    if np.isfinite(q).all() and np.isfinite(v).all():
        speed = np.linalg.norm(v[:, :2], axis=1)
        arm = q[:, measures.q[len(measures.legs):]]
        jaw_width = q[:, measures.fingers[0]] - q[:, measures.fingers[1]]
        tail = np.asarray(observed['t']) >= observed['t'][-1] - 1. - 1e-9
        # qvel[3:6] is body angular velocity. Match the native P6 world-z rate.
        w, x, y, z = q[:, 3:7].T
        world_z_rate = (2 * (x*z-w*y)*v[:, 3] + 2 * (y*z+w*x)*v[:, 4]
                        + (1 - 2*(x*x+y*y))*v[:, 5])
        effect = dict(root_displacement_xy_m=(q[-1, :2] - q[0, :2]).tolist(),
                      peak_arm_excursion_deg=np.rad2deg(np.max(np.abs(arm - arm[0]), axis=0)).tolist(),
                      final_arm_excursion_deg=np.rad2deg(arm[-1] - arm[0]).tolist(),
                      jaw_range_m=[float(jaw_width.min()), float(jaw_width.max())],
                      peak_speed_xy_m_s=float(speed.max()), final_speed_xy_m_s=float(speed[-1]),
                      final_window_s=min(1., float(observed['t'][-1] - observed['t'][0])),
                      final_window_peak_speed_m_s=float(speed[tail].max()),
                      final_window_peak_abs_world_yaw_rate_deg_s=float(np.rad2deg(abs(world_z_rate[tail])).max()))
    return {'observed_motion': effect, 'passed': not failures, 'failures': failures, 'physics_steps': int(physics_steps),
            'expected_physics_steps': expected_steps, 'scored_frames': aligned_count,
            'physical_duration_s': float(observed['t'][-1] - observed['t'][0]),
            'metrics': measured}


def model_diagnostics(model, episode, actions, rollout, *, episode_id, train_episode_ids,
                      max_starts=None, trace_directory=None):
    """Predict 32 physical transitions from each held-out start with no state refresh.

    Set rollout=None to score only the two numerical baselines.

    rollout receives (qpos, qvel, executed_clipped_actions) batched by start.
    It returns (qpos, qvel) of the H successors in *native* order. Pass the
    predictor for this episode's static scene and do not pass future states.
    """
    if episode_id in train_episode_ids:
        raise ValueError(f'{episode_id} occurs in WM training data')
    q = np.asarray(episode['qpos'])
    v = np.asarray(episode['qvel'])
    t = np.asarray(episode['t'])
    actions = np.asarray(actions)
    horizons = PROTOCOL['model_diagnostics']['horizons']
    n = len(q) - 1
    available = [h for h in horizons if h <= n]
    hmax = max(available, default=0)
    if (v.shape != (n + 1, model.nv) or q.shape != (n + 1, model.nq)
            or t.shape != (n + 1,) or actions.shape != (n, model.nu)):
        raise ValueError('Expected N transitions, N+1 true states, and one episode')
    if not np.all(np.isfinite(actions)) or np.any(np.abs(actions) > 1 + 1e-6):
        raise ValueError('Model diagnostics require actual post-clamp policy-space actions')
    for key in ('terminated', 'truncated'):
        if key in episode and np.asarray(episode[key])[:-1].any():
            raise ValueError(f'Interior {key} boundary in episode')
    if not np.allclose(np.diff(t), PROTOCOL['policy_dt_s'], rtol=0., atol=1e-6):
        raise ValueError('Nonuniform transition interval in held-out episode')
    if max_starts is None:
        max_starts = PROTOCOL['model_diagnostics']['max_starts_per_episode']
    if max_starts < 1:
        raise ValueError('At least one start must be requested')
    complete = min(n - hmax + 1, max_starts)
    if not hmax:
        return {'episode_id': episode_id, 'num_transitions': n, 'num_starts': 0,
                'status': 'no_complete_transition', 'results': []}
    starts = np.linspace(0, n - hmax, num=complete, dtype=int)
    if rollout is not None:
        world_q, world_v = rollout(q[starts].copy(), v[starts].copy(),
                                   actions[starts[:, None] + np.arange(hmax)])
        world_q, world_v = np.asarray(world_q), np.asarray(world_v)
        if world_q.shape != (complete, hmax, model.nq) or world_v.shape != (complete, hmax, model.nv):
            raise ValueError('WM rollout must return H consecutive successor states per start')
    if trace_directory is not None:
        trace_directory = Path(trace_directory)
        trace_directory.mkdir(parents=True, exist_ok=False)
        # Uncompressed numerical arrays, separate from summary metrics.
        np.save(trace_directory / 'start_policy_step.npy', starts)
        if rollout is not None:
            np.save(trace_directory / 'predicted_qpos.npy', world_q)
            np.save(trace_directory / 'predicted_qvel.npy', world_v)
        real = starts[:, None] + np.arange(1, hmax + 1)
        np.save(trace_directory / 'actual_qpos.npy', q[real])
        np.save(trace_directory / 'actual_qvel.npy', v[real])
    measures = ErrorMeasures(model)
    results = []
    for h in available:
        ref_q, ref_v = q[starts + h], v[starts + h]
        cv_q = np.array(q[starts], dtype=np.float64, copy=True)
        for i, qi in enumerate(cv_q):
            mj.mj_integratePos(model, qi, np.ascontiguousarray(v[starts[i]], dtype=np.float64),
                               h * PROTOCOL['policy_dt_s'])
        candidates = [('persistence', q[starts], v[starts]),
                      ('constant_velocity', cv_q, v[starts])]
        if rollout is not None:
            candidates.insert(0, ('wm', world_q[:, h - 1], world_v[:, h - 1]))
        for method, predicted_q, predicted_v in candidates:
            finite = np.isfinite(predicted_q).all(axis=1) & np.isfinite(predicted_v).all(axis=1)
            row = dict(horizon=h, method=method, num_starts=complete, nonfinite=int((~finite).sum()))
            # A divergent WM gets a failed horizon; survivors never stand in for the entire batch.
            row['metrics'] = (measures.compare(predicted_q, predicted_v, ref_q, ref_v,
                                               ref_tcp=episode['tcp_world'][starts + h])
                              if np.all(finite) else None)
            results.append(row)
    return {'episode_id': episode_id, 'num_transitions': n, 'num_starts': complete,
            'starts': starts.tolist(), 'status': 'evaluated', 'model_evaluated': rollout is not None,
            'unavailable_horizons': [h for h in horizons if h not in available], 'results': results}


def evaluate_cases(model, references, policy_factory, output_dir, *, seed, checkpoint,
                   plant_factory=None, cases=None, trace_directory=None):
    """Evaluate each frozen condition independently, driven only by policy actions.

    policy_factory(reference_id, episode) initializes/drops the ten-frame history
    for that trial and returns action(qpos, qvel, frame). The plant must report
    the first physical audit failure in each interval and actual substep count.
    """
    if plant_factory is None:
        from .physics import NativePlant
        plant_factory = NativePlant
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    measures = ErrorMeasures(model)
    cases = PROTOCOL['cases'] if cases is None else cases
    rows = []
    for reference_id, reference in references.items():
        for case in cases:
            plant = plant_factory(model)
            initial = case_initial_qpos(model, reference['qpos'][0], case)
            plant.reset(initial, reference['qvel'][0].copy())
            action = policy_factory(reference_id, reference)
            q, v, times = [plant.data.qpos.copy()], [plant.data.qvel.copy()], [float(plant.data.time)]
            total_steps = 0
            reason = None
            for frame in range(len(reference['qpos']) - 1):
                cmd = np.asarray(action(q[-1], v[-1], frame), dtype=float)
                if cmd.shape != (model.nu,) or not np.isfinite(cmd).all():
                    reason = 'invalid_policy_action'
                    break
                info = plant.step(np.clip(cmd, -1., 1.))
                total_steps += info['physics_steps']
                q.append(plant.data.qpos.copy())
                v.append(plant.data.qvel.copy())
                times.append(float(plant.data.time))
                reason = info['failure_reason']
                if reason:
                    break
            q, v = np.asarray(q), np.asarray(v)
            observed = dict(qpos=q, qvel=v, t=np.asarray(times), tcp_world=measures.tcp_world(q))
            score = score_tracking(model, observed, reference, physics_steps=total_steps,
                                   failure_reason=reason, measures=measures)
            score.update(reference_id=reference_id, case=case['id'], seed=seed, checkpoint=str(checkpoint))
            rows.append(score)
            stem = f"{reference_id}_{case['id']}"
            (output_dir / f'{stem}.json').write_text(json.dumps(score, indent=2, allow_nan=False) + '\n')
            if trace_directory is not None:
                dest = Path(trace_directory) / stem
                dest.mkdir(parents=True, exist_ok=False)
                for key, value in observed.items():
                    np.save(dest / f'{key}.npy', value)
    summary = {}
    for reference_id in references:
        by_ref = [row for row in rows if row['reference_id'] == reference_id]
        passed = sum(row['passed'] for row in by_ref)
        protocol_cases = {case['id'] for case in PROTOCOL['cases']}
        complete = cases == PROTOCOL['cases'] and set(row['case'] for row in by_ref) == protocol_cases
        summary[reference_id] = dict(passed=passed, attempted=len(by_ref), complete_manifest=complete,
                                     gate_passed=complete and passed >= PROTOCOL['pass_count_per_reference'])
    (output_dir / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    columns = ['reference_id', 'case', 'seed', 'checkpoint', 'passed', 'failures', 'physics_steps',
               'expected_physics_steps', 'scored_frames', 'physical_duration_s',
               *PROTOCOL['thresholds'], 'wheel_speed_rmse_rad_s', 'gripper_width_rmse_m']
    with (output_dir / 'cases.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, **(row['metrics'] or {}), 'failures': '|'.join(row['failures'])})
    return summary


def audit_native_replay(directory, output_dir):
    """Replay true held commands to check action/time mapping before learning."""
    from .physics import NativePlant, make_model
    from .reference import load_episode
    model = make_model()
    measures = ErrorMeasures(model)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    names = PROTOCOL['references'] + ['moving_arm_wm_validation']
    report = {}
    for name in names:
        path = Path(directory) / name
        metadata = json.loads((path / 'metadata.json').read_text())
        if not metadata['held_action_replay']:
            raise ValueError(f'{name} has substep-varying inputs')
        ep = load_episode(path)
        plant = NativePlant(model)
        plant.reset(ep['qpos'][0], ep['qvel'][0])
        q, v, times = [plant.data.qpos.copy()], [plant.data.qvel.copy()], [float(plant.data.time)]
        substeps = 0
        failure = None
        for command in ep['action_clipped']:
            result = plant.step(command)
            substeps += result['physics_steps']
            q.append(plant.data.qpos.copy())
            v.append(plant.data.qvel.copy())
            times.append(float(plant.data.time))
            failure = result['failure_reason']
            if failure:
                break
        obs = dict(qpos=np.asarray(q), qvel=np.asarray(v), tcp_world=measures.tcp_world(q), t=np.asarray(times))
        report[name] = score_tracking(model, obs, ep, physics_steps=substeps,
                                      failure_reason=failure, measures=measures)
        report[name]['input_source'] = 'recorded teacher commands at original initial condition'
    (output_dir / 'teacher_replay.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    held_out = names[-1]
    ep = load_episode(Path(directory) / held_out)
    diagnostics = model_diagnostics(model, ep, ep['action_clipped'], None, episode_id=held_out,
                                    train_episode_ids=names[:-1])
    (output_dir / 'held_out_baselines.json').write_text(json.dumps(diagnostics, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Audit the time and action mapping using recorded native commands.')
    parser.add_argument('reference_dir', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    audit_native_replay(args.reference_dir, args.output_dir)
