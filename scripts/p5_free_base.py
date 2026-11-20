#!/usr/bin/env python3
"""Run the assembled M1 and Piper on four wheels using bounded joint actuators."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from build_assembly import write_xml, camera_lookat
from p4_fixed_door import ARM, ROOT, configure_position_servos, smooth
from live_assembly import close_viewer


# Segment durations are simulation seconds. Ramps are included in each segment.
SEGMENTS = [('settle', 2), ('stand', 2), ('straight', 6), ('brake', 2),
            ('turn', 7), ('brake_turn', 2), ('arm_extend', 3), ('carry', 4),
            ('arm_return', 3), ('park', 2)]


def build(cfg):
    root = ET.parse(ROOT/'sim/scenes/assembly_preview.xml').getroot()
    root.set('model', 'P5_FREE_BASE_WHEEL_CONTROL')
    root.find('option').set('integrator', 'implicitfast')
    configure_position_servos(root, cfg)
    for actuator in root.find('actuator'):
        if 'FOOT_JOINT' in actuator.get('joint'):
            actuator.tag = 'velocity'
            del actuator.attrib['kp']
            actuator.set('kv', str(cfg['wheel_speed_kv']))
    world = root.find('worldbody')
    # Ten-centimetre floor markings make slow motion visible in the fixed camera.
    for index in range(-4, 11):
        ET.SubElement(world, 'geom', name=f'p5_tick_{index+4}', type='box',
                      pos=f'{index/10:.2f} -0.31 0.001', size='0.002 0.028 0.0005',
                      rgba='.24 .34 .39 1', mass='0', contype='0', conaffinity='0')
    camera_lookat(world, 'p5_overview', [1.7, -2.25, 1.4], [.24, 0, .62], 37)
    path = ROOT/'sim/scenes/p5_free_base.xml'
    write_xml(root, path)
    return mj.MjModel.from_xml_path(str(path))


def experiment(model, cfg, out, live, video, hold_final):
    data = mj.MjData(model)
    mj.mj_resetDataKeyframe(model, data, model.key('home').id)
    mj.mj_forward(model, data)
    joints = model.actuator_trnid[:, 0]
    names = [model.joint(j).name for j in joints]
    wheels = np.array([i for i, name in enumerate(names) if name.endswith('FOOT_JOINT')])
    arms = [names.index(n) for n in ARM]
    held = np.array([i for i in range(model.nu) if i not in wheels])
    q = model.jnt_qposadr[joints]
    dof = model.jnt_dofadr[joints]
    home = data.qpos[q].copy()
    wheel_joints = joints[wheels]
    axes = data.xaxis[wheel_joints].copy()
    if np.min(np.abs(axes[:, 1])) < .99:
        raise ValueError('Home wheel axes do not align with lateral Y')
    lateral = data.xanchor[wheel_joints, 1].copy()
    ground = model.geom('preview_floor').id
    wheel_bodies = model.jnt_bodyid[wheel_joints].tolist()
    wheel_labels = [names[i].split('_')[1] for i in wheels]
    dt = model.opt.timestep
    frame_every = round(1/(25*dt))
    sample_every = round(1/(50*dt))
    cam = 'p5_overview'
    viewer = renderer = writer = None
    opt = mj.MjvOption()
    opt.geomgroup[3] = 0
    rows = []
    stats = {}
    peak = np.zeros(model.nu)
    other_ground = set()
    jac = np.zeros((3, model.nv))
    force = np.zeros(6)
    status = 'completed'
    header = ['time_s','phase','x_m','y_m','z_m','roll_deg','pitch_deg','yaw_deg',
              'vx_m_s','vy_m_s','vz_m_s','yaw_rate_rad_s','v_ref_m_s','yaw_ref_rad_s',
              'wheel_supports', *[f'normal_{n}_N' for n in wheel_labels],
              *[f'slip_{n}_m_s' for n in wheel_labels],
              *[f'q_{n}' for n in names], *[f'dq_{n}' for n in names], *[f'effort_{n}' for n in names],
              *[f'slip_long_{n}_m_s' for n in wheel_labels], *[f'slip_lat_{n}_m_s' for n in wheel_labels], 'yaw_target_deg']
    keep_view = False
    try:
        if live:
            import mujoco.viewer
            viewer = mujoco.viewer.launch_passive(model, data, show_left_ui=False, show_right_ui=False)
            with viewer.lock():
                viewer.opt.geomgroup[3] = 0
                viewer.cam.type = mj.mjtCamera.mjCAMERA_FIXED
                viewer.cam.fixedcamid = model.camera(cam).id
        if video:
            import imageio.v2 as imageio
            from PIL import Image, ImageDraw, ImageFont
            font = ImageFont.load_default(size=21)
            renderer = mj.Renderer(model, height=720, width=1280)
            writer = imageio.get_writer(out/'motion.mp4', fps=25, codec='libx264', quality=7)
        wall = time.monotonic()
        for phase, duration in SEGMENTS:
            heading_control = phase == 'turn' and 'turn_angle_deg' in cfg
            if heading_control:
                duration = cfg['turn_duration_s']
            start = data.qpos[:3].copy()
            start_yaw = Rotation.from_quat(data.qpos[[4,5,6,3]]).as_euler('xyz', degrees=True)[2]
            yaw_integral = 0.
            heading_stopped = False
            print(f'{data.time:.1f} s  {phase}', flush=True)
            for i in range(round(duration/dt)):
                t = i*dt
                envelope = smooth(min(t, duration-t)/.8)
                speed = cfg['straight_speed_m_s']*envelope if phase in ('straight','carry') else 0.
                desired_yaw = cfg['yaw_rate_rad_s']*envelope if phase == 'turn' else 0.
                target_yaw_deg = np.nan
                if heading_control:
                    target_yaw_deg = start_yaw + cfg['turn_angle_deg']*smooth(t/cfg['turn_target_ramp_s'])
                    measured_yaw = Rotation.from_quat(data.qpos[[4,5,6,3]]).as_euler('xyz', degrees=True)[2]
                    error_deg = (target_yaw_deg-measured_yaw+180.) % 360. - 180.
                    rate_limit = cfg['yaw_rate_rad_s']
                    desired_yaw = np.clip(cfg['heading_gain_per_s']*np.deg2rad(error_deg), -rate_limit, rate_limit)
                    if t >= cfg['turn_target_ramp_s'] and abs(error_deg) <= cfg['heading_tolerance_deg']:
                        heading_stopped = True
                yaw_error = desired_yaw - data.qvel[5]
                yaw_request = desired_yaw
                if phase == 'turn':
                    yaw_integral = np.clip(yaw_integral + yaw_error*dt, -.25, .25)
                    limit = cfg['max_differential_yaw_command_rad_s']
                    yaw_request = np.clip(desired_yaw + cfg['yaw_rate_kp']*yaw_error
                                          + cfg['yaw_rate_ki']*yaw_integral, -limit, limit)*envelope
                if heading_stopped:
                    desired_yaw = yaw_request = 0.
                arm_fraction = {'carry': 1., 'arm_extend': smooth(t/duration),
                                'arm_return': 1.-smooth(t/duration)}.get(phase, 0.)
                data.ctrl[:] = home
                data.ctrl[arms] += np.deg2rad(cfg['arm_excursion_deg'])*arm_fraction
                data.ctrl[held] += data.qfrc_bias[dof[held]]/model.actuator_gainprm[held,0]
                data.ctrl[wheels] = axes[:,1]*(speed-lateral*yaw_request)/cfg['rolling_radius_m']
                mj.mj_step(model, data)
                if not np.isfinite(data.qpos).all() or any(w.number for w in data.warning):
                    raise RuntimeError('MuJoCo warning or nonfinite state during free-base experiment')
                peak = np.maximum(peak, np.abs(data.actuator_force))
                angles = Rotation.from_quat(data.qpos[[4,5,6,3]]).as_euler('xyz', degrees=True)
                # Measure velocity at each loaded contact point against the stationary plane.
                normal = np.zeros(4)
                slip = np.full(4, np.nan)
                slip_long = np.full(4, np.nan)
                slip_lat = np.full(4, np.nan)
                for ci, contact in enumerate(data.contact):
                    if ground not in (contact.geom1, contact.geom2):
                        continue
                    geom = contact.geom2 if contact.geom1 == ground else contact.geom1
                    body = model.geom_bodyid[geom]
                    mj.mj_contactForce(model, data, ci, force)
                    if force[0] <= 1e-5:
                        continue
                    if body not in wheel_bodies:
                        other_ground.add(model.body(body).name)
                        continue
                    wi = wheel_bodies.index(body)
                    normal[wi] += force[0]
                    if i % sample_every == 0:
                        mj.mj_jac(model, data, jac, None, contact.pos, body)
                        velocity_xy = (jac @ data.qvel)[:2]
                        point_speed = np.linalg.norm(velocity_xy)
                        if np.isnan(slip[wi]) or point_speed > slip[wi]:
                            slip[wi] = point_speed
                            axle = data.xaxis[wheel_joints[wi], :2]
                            axle = axle / np.linalg.norm(axle)
                            slip_lat[wi] = velocity_xy @ axle
                            slip_long[wi] = velocity_xy @ np.array([axle[1], -axle[0]])
                if i % sample_every == 0:
                    rows.append([float(data.time),phase,*data.qpos[:3],*angles,*data.qvel[:3],
                                 data.qvel[5],speed,desired_yaw,int(np.count_nonzero(normal)),
                                 *normal,*slip,*data.qpos[q],*data.qvel[dof],*data.actuator_force,*slip_long,*slip_lat,target_yaw_deg])
                if i % frame_every == 0:
                    if writer:
                        renderer.update_scene(data, camera=cam, scene_option=opt)
                        image = Image.fromarray(renderer.render())
                        draw = ImageDraw.Draw(image)
                        draw.rectangle((0,0,1280,42),fill='#17242d')
                        draw.text((14,7),f'FREE BASE   {data.time:5.2f} s   {phase}   |   x {data.qpos[0]:.3f} m    yaw {angles[2]:.1f} deg    wheels loaded {np.count_nonzero(normal)}/4',font=font,fill='white')
                        writer.append_data(np.asarray(image))
                    if viewer:
                        if not viewer.is_running():
                            status = 'window_closed'
                            break
                        viewer.sync()
                        time.sleep(max(0.,wall+data.time-time.monotonic()))
            stats[phase] = dict(displacement_xyz_m=(data.qpos[:3]-start).tolist(),
                                yaw_change_deg=float(angles[2]-start_yaw),
                                end_speed_xy_m_s=float(np.linalg.norm(data.qvel[:2])))
            if status != 'completed':
                break
        keep_view = hold_final and viewer and status == 'completed'
    finally:
        if writer: writer.close()
        if renderer: renderer.close()
        if viewer and not keep_view: close_viewer(viewer)
    with (out/'timeseries.csv').open('w') as f:
        csvout = csv.writer(f, lineterminator='\n')
        csvout.writerow(header)
        csvout.writerows(rows)
    samples = np.array([r[2:15] for r in rows], dtype=float)
    slips = np.array([r[19:23] for r in rows], dtype=float)
    summary = dict(status=status,simulation_time_s=data.time,steps=round(data.time/dt),
                   sample_rate_hz=50,mujoco_version=mj.__version__,
                   free_joints=int(np.sum(model.jnt_type==mj.mjtJoint.mjJNT_FREE)),welds=int(np.count_nonzero(model.eq_type==mj.mjtEq.mjEQ_WELD)),
                   wheel_labels=wheel_labels,initial_wheel_world_axes=axes.tolist(),
                   segments=stats, max_sample_abs_roll_pitch_deg=np.max(np.abs(samples[:,3:5]),axis=0).tolist(),
                   min_sample_z_m=samples[:,2].min(),max_sample_slip_m_s=float(np.nanmax(slips)),
                   other_ground_bodies=sorted(other_ground),max_abs_actuator_efforts=dict(zip(names,peak)),
                   actuator_limits_respected=bool(np.all(peak<=model.actuator_forcerange[:,1]+1e-8)),
                   warning_counts=[int(w.number) for w in data.warning], config=cfg)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(status, out, flush=True)
    if keep_view:
        print('Final pose on screen. Data saved. Close the window to exit.', flush=True)
        try:
            while viewer.is_running():
                viewer.sync()
                time.sleep(.1)
        finally:
            close_viewer(viewer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'config/p5.yaml')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--hold-final', action='store_true', help='keep the completed live view open after saving')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.hold_final and not args.live:
        parser.error('--hold-final requires --live')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    out = args.output or ROOT/'results/p5'/stamp
    out.mkdir(parents=True, exist_ok=False)
    arm_settings = yaml.safe_load((ROOT/'config/p4.yaml').read_text())
    cfg = {k: v for k, v in arm_settings.items() if k.startswith(('arm_', 'gripper_'))}
    cfg.update(yaml.safe_load((ROOT/'config/p5.yaml').read_text()))
    cfg.update(yaml.safe_load(args.config.read_text()))
    experiment(build(cfg),cfg,out,args.live,args.video,args.hold_final)


if __name__ == '__main__':
    main()
