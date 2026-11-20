#!/usr/bin/env python3
"""P4 fixed-base, finite-actuator contact experiment; no hardware access.

Only initialise physical qpos once, then integrate mj_step. The passive door
has no actuator, prescribed state, handle weld or applied force. IK uses a
separate scratch MjData and never changes the physical simulation state.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import mujoco as mj
import numpy as np
from scipy.spatial.transform import Rotation
import yaml
from build_assembly import camera_lookat, numbers, quaternion, write_xml
from build_doors import component

ROOT = Path(__file__).resolve().parents[1]
ARM = [f'piper_joint{i}' for i in range(1, 7)]


def build(cfg):
    root = ET.parse(ROOT / 'sim/robots/m1_piper.xml').getroot()
    root.set('model', 'P4_FIXED_BASE_CONTACT_PULL')
    option = root.find('option')
    option.set('timestep', str(cfg['timestep_s']))
    option.set('integrator', 'implicitfast')
    option.set('iterations', '100')
    base = root.find(".//body[@name='m1_base_link']")
    free = base.find("freejoint")
    if free is None:
        free = base.find("joint[@type='free']")
    base.remove(free)
    base.set('pos', numbers(cfg['base_xyz_m']))
    base.set('quat', quaternion([0, 0, cfg['base_yaw_rad']]))
    root.remove(root.find('keyframe'))
    gripper = root.find(".//body[@name='piper_gripper_base']")
    ET.SubElement(gripper, 'site', name='p4_grasp', pos=numbers(cfg['grasp_local_xyz_m']),
                  size='.003', group='4', rgba='0 1 0 1')
    for actuator in root.find('actuator'):
        joint = actuator.get('joint')
        actuator.tag = 'position'
        actuator.attrib.pop('ctrlrange', None)
        actuator.set('ctrllimited', 'false')
        if joint in ARM:
            i = ARM.index(joint)
            kp, kv, limit = cfg['arm_kp'][i], cfg['arm_kv'][i], cfg['arm_torque_limit_nm'][i]
        elif joint == 'piper_gripper_joint1':
            kp, kv, limit = cfg['gripper_kp'], cfg['gripper_kv'], cfg['gripper_force_limit_n']
        else:
            kp, kv = cfg['base_joint_kp'], cfg['base_joint_kv']
            limit = cfg['base_wheel_torque_limit_nm'] if 'FOOT' in joint else cfg['base_leg_torque_limit_nm']
        actuator.set('kp', str(kp)); actuator.set('kv', str(kv))
        actuator.set('forcelimited', 'true'); actuator.set('forcerange', numbers([-limit, limit]))
    world = root.find('worldbody')
    door_cfg = yaml.safe_load((ROOT/'config/door.yaml').read_text())
    door_cfg['handle']['height'] = cfg['door_handle_height_m']
    world.extend(list(component(door_cfg, double=False)))
    ET.SubElement(world, 'geom', name='p4_floor', type='plane', size='4 4 .1', mass='0', rgba='.8 .83 .86 1', friction='.9 .005 .0001')
    ET.SubElement(world, 'light', pos='0 -2 4', dir='.2 .3 -1', castshadow='true')
    camera_lookat(world, 'p4_overview', [-.4, 2.7, 2.1], [1.1, 0, .9], 48)
    camera_lookat(world, 'p4_contact', [1.0, 1.5, 1.5], [1.25, .1, 1.0], 40)
    ET.SubElement(root, 'statistic', center='1.1 0 .95', extent='2.4')
    visual = ET.SubElement(root, 'visual')
    ET.SubElement(visual, 'global', offwidth='1280', offheight='720', azimuth='135', elevation='-20')
    ET.SubElement(visual, 'headlight', ambient='.35 .35 .35', diffuse='.6 .6 .6')
    ET.SubElement(visual, 'map', znear='.005', zfar='30')
    path = ROOT / cfg.get('scene_file', 'sim/scenes/p4_fixed_pull.xml')
    write_xml(root, path)
    return path


class IK:
    def __init__(self, model):
        self.m = model
        self.d = mj.MjData(model)
        self.q = np.array([model.joint(n).qposadr[0] for n in ARM])
        self.v = np.array([model.joint(n).dofadr[0] for n in ARM])
        self.bounds = np.array([model.joint(n).range for n in ARM])
        self.site = model.site('p4_grasp').id

    def solve(self, position, rotation, seed, iterations=100):
        self.d.qpos[self.q] = seed
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        for _ in range(iterations):
            mj.mj_kinematics(self.m, self.d); mj.mj_comPos(self.m, self.d)
            epos = position - self.d.site_xpos[self.site]
            erot = Rotation.from_matrix(rotation @ self.d.site_xmat[self.site].reshape(3,3).T).as_rotvec()
            if np.linalg.norm(epos) < 2e-5 and np.linalg.norm(erot) < 2e-4:
                break
            mj.mj_jacSite(self.m, self.d, jp, jr, self.site)
            J = np.vstack([jp[:, self.v], .2 * jr[:, self.v]])
            error = np.r_[epos, .2 * erot]
            dq = J.T @ np.linalg.solve(J @ J.T + np.eye(6)*1e-5, error)
            self.d.qpos[self.q] = np.clip(self.d.qpos[self.q] + np.clip(dq, -.12, .12), self.bounds[:,0], self.bounds[:,1])
        mj.mj_kinematics(self.m, self.d); mj.mj_comPos(self.m, self.d)
        error = np.linalg.norm(position - self.d.site_xpos[self.site])
        rot_error = Rotation.from_matrix(rotation @ self.d.site_xmat[self.site].reshape(3,3).T).magnitude()
        return self.d.qpos[self.q].copy(), float(error), float(rot_error)


def smooth(x):
    x = np.clip(x, 0, 1)
    return x*x*x*(10 - 15*x + 6*x*x)


def target(cfg, phase, fraction, hinge, local_handle):
    angle = math.radians(cfg['target_angle_deg'])
    theta = angle * smooth(fraction) if phase == 'pull' else (angle if phase in ('hold','release','retreat','final') else 0.)
    Rz = Rotation.from_euler('z', theta).as_matrix()
    # Tool +Z approaches the front handle along the panel inward normal;
    # tool +Y closes across the vertical bar; tool +X points downwards.
    yaw_start = math.radians(cfg.get('tool_yaw_start_deg', 0.))
    tool_yaw = yaw_start + cfg.get('tool_yaw_door_ratio', 1.) * theta
    rotation = Rotation.from_euler('z', tool_yaw).as_matrix() @ np.array([[0,0,1],[0,1,0],[-1,0,0]], float)
    position = hinge + Rz @ local_handle
    retreat = 0.
    if phase == 'settle': retreat = cfg['pregrasp_distance_m']
    if phase == 'approach': retreat = cfg['pregrasp_distance_m'] * (1-smooth(fraction))
    if phase == 'retreat': retreat = cfg['retreat_distance_m'] * smooth(fraction)
    if phase == 'final': retreat = cfg['retreat_distance_m']
    position = position - retreat * rotation[:,2]
    if phase in ('retreat', 'final'):
        position[2] += cfg.get('retreat_lift_m', 0.) * (smooth(fraction) if phase == 'retreat' else 1.)
        yaw_end = math.radians(cfg.get('retreat_yaw_deg', 0.))
        yaw = tool_yaw + (yaw_end-tool_yaw)*smooth(fraction) if phase == 'retreat' else yaw_end
        rotation = Rotation.from_euler('z', yaw).as_matrix() @ np.array([[0,0,1],[0,1,0],[-1,0,0]], float)
    width = cfg['open_width_m']
    if phase == 'grip': width += smooth(fraction) * (cfg['closed_command_width_m'] - width)
    if phase in ('pull','hold'): width = cfg['closed_command_width_m']
    if phase == 'release': width = cfg['closed_command_width_m'] + smooth(fraction) * (width-cfg['closed_command_width_m'])
    return position, rotation, width, theta


def plan(model, cfg):
    ik = IK(model)
    mj.mj_forward(model, ik.d)
    hinge = ik.d.xpos[model.body('door_single_leaf').id].copy()
    local_handle = ik.d.site_xpos[model.site(cfg['handle_site']).id] - hinge
    seed = np.array(cfg.get('ik_seed_rad', [0., .8, -1.4, 0., .6, 0.]))
    targets, phases, positions, angles, errors, rot_errors = [], [], [], [], [], []
    for phase, duration in cfg['phase_duration_s'].items():
        # Plan at 100 Hz; interpolate joint commands during physical stepping.
        for i in range(round(duration * 100)):
            position, rotation, width, theta = target(cfg, phase, i/(duration*100), hinge, local_handle)
            seed, pe, re = ik.solve(position, rotation, seed)
            targets.append(np.r_[seed, width/2]); phases.append(phase)
            positions.append(position); angles.append(theta); errors.append(pe); rot_errors.append(re)
    return {'targets': np.asarray(targets), 'phases': phases, 'positions': np.asarray(positions),
            'angles': np.asarray(angles), 'max_position_error_m': max(errors), 'max_rotation_error_rad': max(rot_errors),
            'worst_position_error_phase': phases[int(np.argmax(errors))]}


def run(model, cfg, trajectory, out, live=False, video=False, hold_final=False):
    data = mj.MjData(model)
    source = mj.MjModel.from_xml_path(str(ROOT/'sim/robots/m1_piper.xml'))
    initial = mj.MjData(source); mj.mj_resetDataKeyframe(source, initial, 0)
    for j in range(model.njnt):
        name = model.joint(j).name
        if name.startswith('m1_'):
            data.qpos[model.jnt_qposadr[j]] = initial.qpos[source.joint(name).qposadr[0]]
    arm_q = [model.joint(n).qposadr[0] for n in ARM]
    data.qpos[arm_q] = trajectory['targets'][0,:6]
    f1, f2 = [model.joint(n).qposadr[0] for n in ('piper_gripper_joint1','piper_gripper_joint2')]
    data.qpos[[f1,f2]] = [trajectory['targets'][0,6], -trajectory['targets'][0,6]]
    mj.mj_forward(model, data)
    actuator_joints = model.actuator_trnid[:,0]
    aq = model.jnt_qposadr[actuator_joints]; av = model.jnt_dofadr[actuator_joints]
    rest = data.qpos[aq].copy()
    arm_a = [model.actuator(n+'_motor').id for n in ARM]
    grip_a = model.actuator('piper_gripper_joint1_motor').id
    hinge_q = model.joint('door_single_hinge').qposadr[0]
    grasp = model.site('p4_grasp').id
    baseline_q = data.qpos.copy()
    viewer = None; renderer = None; writer = None
    if live:
        import mujoco.viewer
        viewer = mujoco.viewer.launch_passive(model, data, show_left_ui=False, show_right_ui=False)
        with viewer.lock():
            viewer.opt.geomgroup[3] = 0
            viewer.cam.type = mj.mjtCamera.mjCAMERA_FIXED; viewer.cam.fixedcamid = model.camera('p4_overview').id
    if video:
        import imageio.v2 as imageio
        renderer = mj.Renderer(model, height=720, width=1280)
        writer = imageio.get_writer(out/'contact.mp4', fps=25, codec='libx264', quality=7)
    opt = mj.MjvOption(); opt.geomgroup[3] = 0
    start = time.monotonic(); dt = model.opt.timestep
    next_sample, next_frame, next_view = 0., 0., 0.
    records=[]; phases_seen=[]; max_force=0.; max_penetration=0.; max_torques=np.zeros(model.nu)
    contact_steps=0; min_angle=0.; max_angle=0.; stopped=False; pair_forces={}; self_forces={}
    contact_force = np.zeros(6)
    failure = None
    step = -1
    try:
        for step in range(round(len(trajectory['targets'])/100/dt)):
            t = step*dt; index = min(int(t*100),len(trajectory['targets'])-1)
            next_index = min(index+1,len(trajectory['targets'])-1); f = t*100-index
            command = (1-f)*trajectory['targets'][index] + f*trajectory['targets'][next_index]
            phase = trajectory['phases'][index]
            if not phases_seen or phases_seen[-1] != phase:
                phases_seen.append(phase); print(f'{t:.2f}s {phase}: door={math.degrees(data.qpos[hinge_q]):.2f} deg', flush=True)
            data.ctrl[:] = rest
            data.ctrl[arm_a] = command[:6]; data.ctrl[grip_a] = command[6]
            # Gravity compensation is inside the same force-limited actuators.
            data.ctrl += data.qfrc_bias[av]/model.actuator_gainprm[:,0]
            mj.mj_step(model, data)
            if not np.isfinite(data.qpos).all() or any(w.number for w in data.warning):
                raise RuntimeError('Nonfinite state or MuJoCo warning during contact experiment')
            robot_door_contacts=0; total_force=0.
            for ci in range(data.ncon):
                c=data.contact[ci]; names=[model.body(model.geom_bodyid[g]).name for g in (c.geom1,c.geom2)]
                if all(n.startswith(('piper_', 'm1_')) for n in names):
                    mj.mj_contactForce(model, data, ci, contact_force)
                    force = float(np.linalg.norm(contact_force[:3]))
                    if force > 1e-6:
                        key = ' / '.join(names)
                        self_forces[key] = max(self_forces.get(key, 0.), force)
                if 'door_single_leaf' in names and any(n.startswith(('piper_','m1_')) for n in names):
                    mj.mj_contactForce(model,data,ci,contact_force)
                    force=float(np.linalg.norm(contact_force[:3]))
                    if force > 1e-6: robot_door_contacts += 1
                    total_force += force
                    max_penetration=max(max_penetration,-float(c.dist))
                    key=' / '.join(model.geom(g).name or model.body(model.geom_bodyid[g]).name for g in (c.geom1,c.geom2))
                    pair_forces[key]=max(pair_forces.get(key,0.),force)
            if robot_door_contacts: contact_steps+=1
            max_force=max(max_force,total_force); max_torques=np.maximum(max_torques,np.abs(data.actuator_force))
            angle=float(data.qpos[hinge_q]); min_angle=min(min_angle,angle); max_angle=max(max_angle,angle)
            if t+1e-9>=next_sample:
                records.append([float(data.time),phase,math.degrees(angle),math.degrees(trajectory['angles'][index]),
                                float(data.qvel[model.joint('door_single_hinge').dofadr[0]]),
                                float(data.qpos[f1]-data.qpos[f2]),robot_door_contacts,total_force,
                                float(np.linalg.norm(data.site_xpos[grasp]-trajectory['positions'][index])),
                                *data.qpos[arm_q],*data.actuator_force[arm_a],float(data.actuator_force[grip_a])])
                next_sample+=1/cfg['sample_hz']
            if writer and t+1e-9>=next_frame:
                renderer.update_scene(data, camera='p4_overview', scene_option=opt)
                from PIL import Image, ImageDraw, ImageFont
                frame = Image.fromarray(renderer.render())
                draw = ImageDraw.Draw(frame); font = ImageFont.load_default(size=22)
                draw.rectangle((0,0,1280,70), fill=(16,20,25))
                draw.text((16,8), f'P4 FIXED BASE | mj_step | {data.time:.2f} s | {phase}', font=font, fill='white')
                draw.text((16,38), f'Door {math.degrees(angle):.2f} deg | contact force sum {total_force:.2f} N', font=font, fill='white')
                writer.append_data(np.asarray(frame)); next_frame+=1/25
            if viewer and t+1e-9>=next_view:
                if not viewer.is_running(): stopped=True; break
                viewer.sync(); next_view+=1/60
                time.sleep(max(0, start+t-time.monotonic()))
        if hold_final and viewer and not stopped:
            print('FINAL_STATE_REVIEW: dynamics finished; close viewer to save and exit.', flush=True)
            while viewer.is_running():
                viewer.sync()
                time.sleep(1/30)
    except Exception as exc:
        failure = f'{type(exc).__name__}: {exc}'
    finally:
        if writer: writer.close(); renderer.close()
        if viewer:
            from live_assembly import close_viewer
            close_viewer(viewer)
    with (out/'timeseries.csv').open('w') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['time_s', 'phase', 'door_angle_deg', 'planned_angle_deg', 'door_speed_rad_s',
                    'width_m', 'robot_door_contacts', 'contact_force_norm_sum_n', 'tcp_error_m',
                    *[n+'_rad' for n in ARM], *[n+'_torque_nm' for n in ARM], 'gripper_force_n'])
        w.writerows(records)
    summary={'mode':'P4_FIXED_BASE_CONTACT_PULL','config':cfg,'mujoco_version':mj.__version__,
             'failure':failure, 'nq':model.nq,'nv':model.nv,'nu':model.nu,'neq':model.neq,'steps':step+1,'simulation_time_s':float(data.time),
             'initial_qpos':baseline_q.tolist(),'final_qpos':data.qpos.tolist(),'door_min_angle_deg':math.degrees(min_angle),
             'door_max_angle_deg':math.degrees(max_angle),'door_final_angle_deg':math.degrees(data.qpos[hinge_q]),
             'robot_door_contact_steps':contact_steps,'max_contact_force_norm_sum_n':max_force,
             'max_robot_door_penetration_m':max_penetration,'contact_pair_max_force_n':pair_forces,'actuator_max_abs_forces':max_torques.tolist(),
             'actuator_force_limits':model.actuator_forcerange.tolist(),'stopped_by_window_close':stopped,
             'door_actuated':bool(model.joint('door_single_hinge').id in actuator_joints),
             'floating_joint_count':int(np.sum(model.jnt_type == mj.mjtJoint.mjJNT_FREE)),
             'door_state_writes_after_initialization':0,
             'handle_weld':bool(np.any(model.eq_type == mj.mjtEq.mjEQ_WELD)),
             'robot_self_contact_max_force_n': self_forces,
             'force_limits_respected': bool(np.all(max_torques <= np.max(np.abs(model.actuator_forcerange), axis=1)+1e-8)),
             'mujoco_warning_counts': [int(w.number) for w in data.warning],
             'ik_max_position_error_m':trajectory['max_position_error_m'],'ik_max_rotation_error_rad':trajectory['max_rotation_error_rad']}
    summary['completed_planned_duration'] = failure is None and not stopped and step+1 == round(len(trajectory['targets'])/100/dt)
    summary['reached_60deg_once']=summary['door_max_angle_deg']>=60 and contact_steps>0
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('config','initial_qpos','final_qpos','actuator_force_limits')},indent=2))
    if failure:
        raise RuntimeError(f'{failure}; partial records saved in {out}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/p4.yaml')
    parser.add_argument('--output',type=Path,default=None)
    parser.add_argument('--live',action='store_true');parser.add_argument('--video',action='store_true');parser.add_argument('--plan-only',action='store_true')
    parser.add_argument('--hold-final', action='store_true', help='keep the live final state visible until the viewer is closed')
    args=parser.parse_args();cfg=yaml.safe_load(args.config.read_text())
    if args.output is None:
        args.output = ROOT/'results/p4'/datetime.now(timezone.utc).strftime('pull_%Y%m%dT%H%M%SZ')
    args.output.mkdir(parents=True,exist_ok=True)
    model=mj.MjModel.from_xml_path(str(build(cfg)));trajectory=plan(model,cfg)
    (args.output/'plan.json').write_text(json.dumps({k:v for k,v in trajectory.items() if k.startswith('max_') or k.startswith('worst_')},indent=2)+'\n')
    print('IK:',trajectory['max_position_error_m'],trajectory['max_rotation_error_rad'],trajectory['worst_position_error_phase'],flush=True)
    if trajectory['max_position_error_m']>.002 or trajectory['max_rotation_error_rad']>.02:
        raise RuntimeError('Planned target exceeds IK tolerance; physical simulation not started')
    if not args.plan_only:run(model,cfg,trajectory,args.output,args.live,args.video,args.hold_final)
    print(f'Saved {args.output}', flush=True)

if __name__=='__main__':main()
