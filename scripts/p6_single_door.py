#!/usr/bin/env python3
"""One MjData and one actuator write per physical step of the free-base door task."""
import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import time

import mujoco as mj
import numpy as np

from p4_fixed_door import ROOT
from p6_arm import Arm
from p6_base import BaseDrive, signed_angle
from p6_contacts import ContactMeter
from p6_scene import build, settings


def json_write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def compact(row):
    return {k: format(float(v), '.8g') if isinstance(v, (np.floating, float)) else v for k, v in row.items()}


def vector(row, prefix, fields, values):
    row.update((prefix + '_' + k, v) for k, v in zip(fields, values))


def quat(mat):
    result = np.empty(4)
    mj.mju_mat2Quat(result, mat.reshape(-1))
    return result


def run(cfg, out, live, video, hold_final, view_factory=None, step_observer=None, integrator=None, held_teacher=None, arm_factory=Arm):
    model = build(cfg)
    advance = mj.mj_step if integrator is None else integrator.step
    physics_source = 'native MuJoCo mj_step' if integrator is None else integrator.source
    revision_id = mj.mj_name2id(model, mj.mjtObj.mjOBJ_TEXT, 'mount_revision')
    if revision_id >= 0:
        start = int(model.text_adr[revision_id])
        end = start + int(model.text_size[revision_id]) - 1
        cfg['assembly_revision'] = model.text_data[start:end].decode('utf-8')
    else:
        cfg['assembly_revision'] = 'legacy_unlabeled'
    cfg["arm_root_in_m1_m"] = model.body("piper_base_link").pos.tolist()
    d = mj.MjData(model)
    mj.mj_resetDataKeyframe(model, d, model.key('home').id)
    stage, case = cfg['stage'], cfg['perturbation']
    mobile = stage in ('mobile', 'push')
    station = np.array(cfg['base_xyz_m'][:2])
    yaw = cfg['base_yaw_rad']
    parking = station - cfg['travel_m'] * np.array([np.cos(yaw), np.sin(yaw)])
    initial_yaw = yaw + np.deg2rad(case.get('yaw', 0))
    d.qpos[:2] = (parking if mobile else station) + [case.get('dx', 0), case.get('dy', 0)]
    d.qpos[3:7] = [np.cos(initial_yaw/2), 0, 0, np.sin(initial_yaw/2)]
    door_q = model.joint('door_single_hinge').qposadr[0]
    d.qpos[door_q] = np.deg2rad(case.get('door', 0))
    mj.mj_forward(model, d)
    initial_q = d.qpos.tolist()
    drive, arm = BaseDrive(model, d, cfg), arm_factory(model, d, cfg)
    meter = ContactMeter(model, 'preview_floor', 'back' if stage == 'push' else 'front',
                         cfg['contact_threshold_n'], cfg['wheel_threshold_n'])
    if live:
        if view_factory is None:
            from p6_view import DoorView as view_factory
        view = view_factory(model, d, arm.handle_id, cfg, out, video)
    else:
        view = None
    seq = (['approach_base'] if mobile else []) + ['settle', 'pregrasp']
    if stage == 'support':
        seq += ['dry_sweep', 'final']
    else:
        seq += ['approach_arm','grasp']
        if not cfg.get('hold_grasp_pose', False):
            seq.append('open')
        seq += ['hold','release','retreat_arm','post_release_hold']
        if mobile and not cfg.get('segment_end_after_retreat_hold', False):
            seq += ['stow','retreat_base','final']
    if cfg.get('arrival_only'):
        seq = ['approach_base', 'settle']
    labels = [model.joint(j).name for j in model.actuator_trnid[:, 0]]
    arm_ids = np.r_[drive.arms, drive.grip]
    arm_names = [labels[i] for i in drive.arms]
    arm_lower, arm_upper = arm.ik.bounds.T
    arm_min_q = d.qpos[arm.ik.q].copy()
    arm_min_margin = np.minimum(arm_min_q - arm_lower, arm_upper - arm_min_q)
    arm_min_time = np.full(len(arm_names), float(d.time))
    arm_min_phase = ['initial'] * len(arm_names)
    arm_dof = model.jnt_dofadr[model.actuator_trnid[arm_ids, 0]]
    all_q = model.jnt_qposadr[model.actuator_trnid[:, 0]]
    all_v = model.jnt_dofadr[model.actuator_trnid[:, 0]]
    force_limit = model.actuator_forcerange[:, 1]
    dt = model.opt.timestep
    phase_index = step = samples = 0
    phase_start = good_time = lost = unloaded = sliding = 0.
    peak_sat = sat_time = np.zeros(model.nu)
    peak_force = np.zeros(model.nu)
    peak_drift = peak_grip = peak_tilt = peak_wrench = 0.
    unexpected = {}
    phase_stats = {}
    ref_xy, ref_yaw = station.copy(), yaw
    angle = float(np.rad2deg(d.qpos[door_q]))
    raw = effective = angle
    goal = cfg['target_angle_deg']
    command = np.zeros(model.nu)
    events = []
    reason = None
    paused_s = 0.
    started = time.monotonic()
    sample_every = round(1 / (cfg['sample_hz'] * dt))
    frame_every = round(1 / (25 * dt))
    last_phase = None
    log_stream = (out/'timeseries.csv').open('w')
    points_stream = (out/'contacts.csv').open('w')
    margins_stream = (out/'joint_margins_500hz.csv').open('w')
    margin_writer = csv.writer(margins_stream, lineterminator='\n')
    margin_writer.writerow(['time_s', 'phase', *[name + '_margin_rad' for name in arm_names]])
    margin_writer.writerow([0, 'initial', *arm_min_margin])
    point_writer = csv.DictWriter(points_stream, ['time_s', 'phase', *meter.row_fields], lineterminator='\n')
    point_writer.writeheader()
    writer = None
    json_write(out/'config.json', cfg)
    try:
        while phase_index < len(seq):
            phase = seq[phase_index]
            t = float(d.time)
            elapsed = t - phase_start
            new_phase = phase != last_phase
            if new_phase:
                print(f'{t:.3f}s {phase}  door {angle:.3f} deg', flush=True)
                last_phase = phase
            fraction = min(1., elapsed / cfg['phase_ramp_s'].get(phase, 1.))
            base_mode = {'approach_base':'approach', 'retreat_base':'retreat'}.get(phase, 'hold')
            if phase in ('grasp','open','hold','release'):
                base_mode = 'grip'
            state = drive.state(d)
            at_parking = mobile and phase in ('retreat_base','final')
            destination = parking if at_parking else ref_xy
            heading = yaw if at_parking else ref_yaw
            drift = float(np.linalg.norm(state['xy'] - destination))
            heading_err = abs(math.degrees(signed_angle(state['yaw'] - heading)))
            tilt = float(np.rad2deg(max(abs(state['roll']), abs(state['pitch']))))
            slow = (state['speed'] < cfg['settle_speed_m_s'] and
                    abs(np.rad2deg(state['yaw_rate'])) < cfg['settle_yaw_rate_deg_s'])
            in_zone = drift <= cfg['position_tol_m'] and heading_err <= cfg['heading_tol_deg']
            angle = float(np.rad2deg(d.qpos[door_q]))
            width = float(d.joint('piper_gripper_joint1').qpos[0] - d.joint('piper_gripper_joint2').qpos[0])
            if phase == 'open':
                rate = cfg['angle_rate_deg_s'] * min(1., elapsed/cfg['angle_accel_ramp_s'])
                raw = min(goal, raw + dt * rate)
                if not lost and not sliding and in_zone and not np.any(sat_time):
                    effective = min(raw, angle + cfg['angle_lead_deg'], effective + dt * rate)
            elif phase in ('pregrasp','approach_arm','grasp'):
                raw = effective = angle
            # Refresh world sites/anchors from today's actual qpos before the scratch IK.
            # This updates derived transforms only. advance() is the sole state integrator.
            mj.mj_kinematics(model, d)
            if new_phase or step % 5 == 0:
                q_arm, q_finger = arm.update(d, phase, fraction, raw, effective)
            command[drive.legs] = drive.leg_commands(d)
            command[drive.wheels] = drive.wheel_commands(d, destination, heading, base_mode)
            command[arm_ids] = np.r_[q_arm, q_finger] + d.qfrc_bias[arm_dof] / model.actuator_gainprm[arm_ids, 0]
            q0 = d.qpos.copy()
            v0 = d.qvel.copy()
            if step_observer is not None or held_teacher is not None:
                # Undo the exact bias used above before mj_step replaces qfrc_bias.
                target = command.copy()
                position_ids = np.r_[drive.legs, arm_ids]
                target[position_ids] -= d.qfrc_bias[all_v[position_ids]] / model.actuator_gainprm[position_ids, 0]
                target[drive.grip] *= 2.0  # full jaw opening in metres
            if held_teacher is not None:
                # The teacher can calculate feedback at its original rate. Only the
                # command selected at a policy boundary enters the physical plant.
                target = held_teacher.select(model, step, target, arm, fraction)
                command[:] = target
                command[drive.grip] *= .5
                command[position_ids] += d.qfrc_bias[all_v[position_ids]] / model.actuator_gainprm[position_ids, 0]
            d.ctrl[:] = command
            advance(model, d)
            # Actual integrated joint positions at every physics step, including
            # extrema that fall between the 25 Hz CSV samples. Negative = outside.
            actual_arm_q = d.qpos[arm.ik.q]
            actual_margin = np.minimum(actual_arm_q - arm_lower, arm_upper - actual_arm_q)
            margin_writer.writerow([format(d.time, '.6f'), phase, *actual_margin])
            for i in np.flatnonzero(actual_margin < arm_min_margin):
                arm_min_margin[i] = actual_margin[i]
                arm_min_q[i] = actual_arm_q[i]
                arm_min_time[i] = float(d.time)
                arm_min_phase[i] = phase
            sample = step % sample_every == 0
            c = meter.measure(d, details=sample)
            if step_observer is not None:
                step_observer(model, d, t, q0, v0, target, phase, c)
            step += 1
            xyz = d.site_xpos[arm.grasp_id]
            handle_xyz = d.site_xpos[arm.handle_id]
            grip_error = float(np.linalg.norm(xyz - handle_xyz))
            tracking = float(np.linalg.norm(xyz - arm.position))
            no_contact = c.force_norm_sum <= cfg['contact_threshold_n']
            supported = bool(c.supported.all())
            slip = float(np.max(np.hypot(np.nan_to_num(c.slip_long), np.nan_to_num(c.slip_lat))))
            sat_time = np.where(np.abs(d.actuator_force) >= force_limit * cfg['sat_fraction'], sat_time+dt, 0.)
            peak_sat = np.maximum(peak_sat, sat_time)
            peak_force = np.maximum(peak_force, np.abs(d.actuator_force))
            unloaded = 0. if supported else unloaded+dt
            gripping = phase in ('open','hold')
            lost = lost+dt if gripping and not c.both else 0.
            sliding = sliding+dt if base_mode == 'grip' and slip > cfg['park_slip_limit_m_s'] else 0.
            peak_tilt = max(peak_tilt, tilt)
            if base_mode in ('grip','hold') and phase not in ('settle','final'):
                peak_drift = max(peak_drift, drift)
            if gripping:
                peak_grip = max(peak_grip, grip_error)
            door_load = float(np.linalg.norm(c.door_force))
            peak_wrench = max(peak_wrench, door_load)
            for pair, force in c.unexpected.items():
                unexpected[pair] = max(unexpected.get(pair, 0.), force)
            if phase not in phase_stats:
                phase_stats[phase] = dict(max_slip_m_s=0., max_base_speed_m_s=0., max_effector_error_m=0.,
                                          max_ik_error_m=0., min_wheel_N=[1e9]*4, max_door_norm_sum_N=0.,
                                          both_contact_s=0., max_tilt_deg=0., max_door_torque_Nm=0., max_yaw_error_deg=0.)
            ps = phase_stats[phase]
            for key, val in [('max_slip_m_s',slip),('max_base_speed_m_s',state['speed']),
                             ('max_effector_error_m',tracking),('max_ik_error_m',arm.ik_position_error),
                             ('max_tilt_deg',tilt),('max_yaw_error_deg',heading_err),
                             ('max_door_norm_sum_N',c.force_norm_sum),('max_door_torque_Nm',np.linalg.norm(c.door_torque))]:
                ps[key] = max(ps[key], float(val))
            ps['both_contact_s'] += int(c.both)*dt
            ps['min_wheel_N'] = np.minimum(ps['min_wheel_N'], c.normal).tolist()
            if sample:
                if phase in ('retreat_arm','post_release_hold','stow','retreat_base','final'):
                    clearance, pair = meter.door_clearance(d)
                    if clearance < ps.get('min_robot_door_clearance_m_25hz', math.inf):
                        ps.update(min_robot_door_clearance_m_25hz=clearance,
                                  clearance_pair=pair, clearance_time_s=t)
                row = dict(time_s=t, phase=phase, door_deg=angle, door_rate_rad_s=v0[model.joint('door_single_hinge').dofadr[0]],
                           raw_deg=arm.raw_angle_deg, effective_deg=arm.angle_deg, actual_width_m=width,
                           width_ref_m=arm.width, planar_error_m=drift, heading_error_deg=heading_err,
                           tilt_deg=tilt, tracking_m=tracking, grip_error_m=grip_error,
                           ik_m=arm.ik_position_error, ik_rad=arm.ik_rotation_error,
                           speed_ref_m_s=drive.last_speed, yaw_command_rad_s=drive.last_turn,
                           door_norm_sum_N=c.force_norm_sum, penetration_m=c.max_penetration,
                           both=int(c.both))
                for prefix, fields, values in [('root','xyz',q0[:3]),('root','wxyz',q0[3:7]),
                    ('world_v','xyz',state['linear_world']),('world_omega','xyz',state['angular_world']),
                    ('raw_pos','xyz',arm.raw_position),('eff_pos','xyz',arm.position),('actual_pos','xyz',xyz),
                    ('handle_pos','xyz',handle_xyz),('raw_quat','wxyz',quat(arm.raw_rotation)),
                    ('eff_quat','wxyz',quat(arm.rotation)),('actual_quat','wxyz',quat(d.site_xmat[arm.grasp_id])),
                    ('handle_quat','wxyz',quat(d.site_xmat[arm.handle_id])),
                    ('door_F','xyz',c.door_force),('door_M_base','xyz',c.door_torque),('hand_F','xyz',c.hand_force),
                    ('normal_N',meter.wheel_labels,c.normal),('long_slip',meter.wheel_labels,c.slip_long),
                    ('lat_slip',meter.wheel_labels,c.slip_lat),('finger_N','12',c.finger_normal),
                    ('q',labels,q0[all_q]),('dq',labels,v0[all_v]),('ctrl',labels,command),('effort',labels,d.actuator_force)]:
                    # Quaternion columns are explicitly distinguished from XYZ position columns.
                    vector(row, 'root_quat' if prefix=='root' and fields=='wxyz' else prefix, fields, values)
                # Like the existing q columns, CSV margins use step-start q0.
                sampled_arm_q = q0[arm.ik.q]
                vector(row, 'joint_margin_rad', arm_names,
                       np.minimum(sampled_arm_q - arm_lower, arm_upper - sampled_arm_q))
                if writer is None:
                    writer = csv.DictWriter(log_stream, list(row), lineterminator='\n')
                    writer.writeheader()
                writer.writerow(compact(row))
                for point in c.rows:
                    point_writer.writerow(compact(dict(time_s=t, phase=phase, **point)))
                samples += 1
            if view and (step-1) % frame_every == 0:
                view.draw('P6 / FREE_BASE / mj_step\nStage\nDoor\nBase error / tilt\nWheel loads [N]\nFinger loads [N]',
                          f"{t:.2f} s\n{phase}\n{angle:.2f} deg\n{1000*drift:.1f} mm / {tilt:.2f} deg\n"
                          + '  '.join(f'{v:.0f}' for v in c.normal) + '\n' + '  '.join(f'{v:.2f}' for v in c.finger_normal))
                if view.paused:
                    paused_s += view.handle_pause()
                if not view.running():
                    reason = 'window_closed'
                time.sleep(max(0., started + paused_s + t - time.monotonic()))
            if not np.isfinite(d.qpos).all() or any(w.number for w in d.warning):
                reason = 'nonfinite_or_solver_warning'
            elif held_teacher is not None and np.any(actual_margin < 0.):
                reason = 'arm_joint_limit:' + arm_names[int(np.argmin(actual_margin))]
            elif unexpected:
                reason = 'unexpected_contact:' + ','.join(unexpected)
            elif (stage == 'support' or phase in ('approach_base','settle','pregrasp','post_release_hold','stow','retreat_base','final')) and not no_contact:
                reason = 'door_contact_outside_manipulation'
            elif unloaded >= cfg['unloaded_limit_s'] or tilt >= cfg['tilt_limit_deg']:
                reason = 'wheel_support_or_tilt'
            elif sat_time.max() >= cfg['sat_limit_s']:
                reason = 'persistent_saturation:' + labels[int(np.argmax(sat_time))]
            elif lost >= cfg['loss_limit_s'] or sliding >= cfg['park_slip_limit_s']:
                reason = 'lost_grip' if lost else 'persistent_grip_phase_wheel_slip'
            elif gripping and (not in_zone or grip_error > cfg['grasp_error_m']):
                reason = 'grip_base_or_handle_error'
            elif phase not in ('approach_base','settle','retreat_base','final') and not in_zone:
                reason = 'operation_station_drift'
            elif gripping and door_load > cfg.get('grip_net_force_limit_n', math.inf):
                reason = 'door_force_limit'
            if reason:
                if not sample:
                    for point in meter.measure(d, details=True).rows:
                        point_writer.writerow(compact(dict(time_s=t, phase=phase, **point)))
                break
            stable = slow and in_zone and supported
            reached = abs(angle-goal) <= cfg['angle_tolerance_deg']
            near = tracking <= cfg['tracking_tol_m'] and arm.ik_position_error <= .002 and arm.ik_rotation_error <= .02
            ramp_done = fraction >= 1.
            low, high = cfg['grasp_width_range_m']
            # Predicate and required continuous time at 500 Hz for each transition.
            if phase in ('approach_base','retreat_base'):
                ready, seconds = in_zone and drift < .010 and heading_err < 1., .06
            elif phase == 'settle':
                ready, seconds = stable, cfg['settle_time_s']
            elif phase in ('pregrasp','dry_sweep','approach_arm'):
                ready, seconds = ramp_done and near, .15
            elif phase == 'grasp':
                ready, seconds = ramp_done and c.both and low <= width <= high and grip_error <= cfg['grasp_error_m'], cfg['grasp_confirm_s']
            elif phase == 'open':
                ready, seconds = raw >= goal and effective >= goal-.05 and reached and c.both, .15
            elif phase == 'hold':
                ready, seconds = reached and c.both and stable and abs(v0[model.joint('door_single_hinge').dofadr[0]]) < .01, cfg.get('grip_hold_s', .5)
            elif phase == 'release':
                ready, seconds = ramp_done and no_contact and width >= .9*cfg['open_width_m'], .15
            elif phase == 'retreat_arm':
                ready, seconds = ramp_done and no_contact and near and grip_error >= .8*cfg['retreat_distance_m'], .15
            elif phase == 'stow':
                ready, seconds = ramp_done and no_contact and np.max(np.abs(q0[arm.ik.q] - arm.home)) < .025, .15
            else:  # post-release or final physical parking window
                ready, seconds = stable and no_contact and (reached if stage != 'support' else abs(angle)<.1), cfg['post_hold_s']
                if phase == 'final' and held_teacher is not None:
                    seconds = cfg.get('final_reference_hold_s', seconds)
            good_time = good_time+dt if ready else 0.
            release_allowed = (phase != 'hold' or
                               step >= cfg.get('teacher_release_earliest_step', 0))
            if good_time+1e-10 >= seconds and release_allowed:
                events.append(dict(phase=phase, time_s=d.time, door_deg=angle, xy=state['xy'].tolist(),
                                   yaw_deg=math.degrees(state['yaw']), root_z_m=q0[2], speed_m_s=state['speed'],
                                   yaw_rate_deg_s=math.degrees(state['yaw_rate']), loads_N=c.normal.tolist(),
                                   fingers_N=c.finger_normal.tolist(), width_m=width, grip_error_m=grip_error,
                                   tracking_m=tracking, continuous_s=good_time))
                if phase == 'settle':
                    ref_xy, ref_yaw = state['xy'].copy(), state['yaw']
                phase_index += 1
                phase_start, good_time = float(d.time), 0.
            elif elapsed >= cfg['phase_timeout_s'][phase]:
                reason = 'timeout:' + phase
                break
    except Exception as exc:
        reason = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        wall = time.monotonic()-started-paused_s
        log_stream.close()
        margins_stream.close()
        points_stream.close()
        if view:
            view.finish_video()
        completed = phase_index == len(seq) and reason is None
        summary = dict(stage=stage, case=cfg['case'], script_completed=completed, task_success=completed and mobile and not cfg.get('arrival_only', False) and not cfg.get('segment_end_after_retreat_hold', False),
                       stage_pass=completed, failure=reason, last_phase=last_phase, events=events, planned_phases=seq,
                       samples=samples, frames=view.frames if view else 0, physics_steps=step, dt_s=dt,
                       assembly_revision=cfg['assembly_revision'], arm_root_in_m1_m=cfg['arm_root_in_m1_m'],
                       arm_joint_limit_min={name: dict(min_margin_rad=float(arm_min_margin[i]),
                           min_margin_deg=float(np.rad2deg(arm_min_margin[i])), time_s=float(arm_min_time[i]),
                           phase=arm_min_phase[i], q_rad=float(arm_min_q[i]),
                           lower_rad=float(arm_lower[i]), upper_rad=float(arm_upper[i]),
                           nearest_limit='lower' if arm_min_q[i]-arm_lower[i] <= arm_upper[i]-arm_min_q[i] else 'upper')
                           for i, name in enumerate(arm_names)},
                       arm_joint_limit_sampling=('initial and every post-mj_step actual qpos; signed nearest-limit margin' if integrator is None
                                                 else 'initial and every post-Warp-step actual qpos; signed nearest-limit margin'),
                       sim_time_s=d.time, wall_s=wall, realtime_factor=d.time/max(wall,.001), desktop=bool(view),
                       mujoco=mj.__version__, source=physics_source+'; step-start observations, 25 Hz point log',
                       initial_qpos=initial_q, final_qpos=d.qpos.tolist(), target_deg=goal, tolerance_deg=cfg['angle_tolerance_deg'],
                       final_deg=float(np.rad2deg(d.qpos[door_q])), max_base_drift_m=peak_drift,
                       max_tilt_deg=peak_tilt, max_grip_error_m=peak_grip, max_door_force_N=peak_wrench,
                       unexpected=unexpected, max_abs_actuator_force=dict(zip(labels,peak_force)),
                       max_contiguous_saturation_s=dict(zip(labels,peak_sat)), actuator_limits=dict(zip(labels,force_limit)),
                       phases=phase_stats, warnings=[int(w.number) for w in d.warning])
        json_write(out/'summary.json', summary)
        print(f"Saved {out} | stage_pass={completed} | {reason or 'complete'} | door={summary['final_deg']:.3f}", flush=True)
        if view:
            view.close(hold_final, reason or 'SAVED - COMPLETE')
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('support','small','pull','mobile','push'))
    parser.add_argument('--case', type=int, choices=range(1,21), default=1,
                        help='C01 is nominal; C02-C20 apply to mobile or push')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--hold-final', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if (args.video or args.hold_final) and not args.live:
        parser.error('--video and --hold-final require --live')
    if args.case != 1 and args.stage not in ('mobile', 'push'):
        parser.error('C02-C20 apply to complete mobile pull or push tasks')
    cfg = settings(args.stage, args.case)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out = args.output or ROOT/'results/p6'/f'{args.stage}_C{args.case:02}_{stamp}'
    out.mkdir(parents=True, exist_ok=False)
    return 0 if run(cfg, out, args.live, args.video, args.hold_final) else 1


if __name__ == '__main__':
    raise SystemExit(main())
