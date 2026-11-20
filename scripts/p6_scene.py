"""Compose the free-root door experiment and freeze each initial condition."""
from copy import deepcopy
import xml.etree.ElementTree as ET
import numpy as np
import mujoco as mj
import yaml

from build_assembly import numbers, write_xml, camera_lookat
from build_doors import component
from p4_fixed_door import ROOT, configure_position_servos

CASES = {
    1: {}, 2: {'dx': .05}, 3: {'dx': -.05}, 4: {'dy': .05}, 5: {'dy': -.05},
    6: {'yaw': 5}, 7: {'yaw': -5}, 8: {'door': 2}, 9: {'door': 5},
    10: {'wheel_mu': .8}, 11: {'wheel_mu': 1.2}, 12: {'finger_mu': .8}, 13: {'finger_mu': 1.2},
    14: {'hinge_friction': .5}, 15: {'hinge_friction': 1.5},
    16: {'hinge_damping': .5}, 17: {'hinge_damping': 1.5},
    18: {'dx': .05, 'yaw': 5, 'wheel_mu': .8},
    19: {'dy': -.05, 'finger_mu': .8, 'hinge_friction': 1.5},
    20: {'dx': -.05, 'yaw': -5, 'door': 5, 'hinge_damping': 1.5},
}


def settings(stage, case):
    def load(name):
        return yaml.safe_load((ROOT / 'config' / name).read_text())
    cfg = load('p4_push.yaml' if stage == 'push' else 'p4_pull_60.yaml')
    cfg.update(load('p5.yaml'))
    cfg.update(load('p6_pull.yaml'))
    for old_key in ('scene_file', 'phase_duration_s', 'arm_excursion_deg'):
        cfg.pop(old_key, None)
    cfg.update(stage=stage, case=case, perturbation=deepcopy(CASES[case]))
    if stage == 'small':
        cfg['target_angle_deg'] = cfg['small_angle_deg']
    return cfg


def build(cfg, scene_path=None):
    root = ET.parse(ROOT / 'sim/scenes/assembly_preview.xml').getroot()
    root.set('model', 'P6_FREE_BASE_mj_step')
    root.find('option').attrib.update(integrator='implicitfast', iterations='100', timestep=str(cfg['timestep_s']))
    root.find('option').attrib.update(cone=cfg['cone'], impratio=str(cfg['impratio']), tolerance=str(cfg['solver_tolerance']))
    configure_position_servos(root, cfg)
    for actuator in root.find('actuator'):
        if actuator.get('joint').endswith('FOOT_JOINT'):
            actuator.tag = 'velocity'
            del actuator.attrib['kp']
            actuator.set('kv', str(cfg['wheel_speed_kv']))
    gripper = root.find(".//body[@name='piper_gripper_base']")
    ET.SubElement(gripper, 'site', name='p4_grasp', pos=numbers(cfg['grasp_local_xyz_m']), size='.003', group='4')
    world = root.find('worldbody')
    door = yaml.safe_load((ROOT / 'config/door.yaml').read_text())
    door['handle']['height'] = cfg['door_handle_height_m']
    world.extend(list(component(door, double=False)))
    root.find('.//key[@name="home"]').attrib['qpos'] += ' 0'
    back = cfg['stage'] == 'push'
    camera_lookat(world, 'p6_overview', [3.8 if back else -1.15, 2.6, 1.65],
                  [1.4 if back else 1.0, .04, .89], 39)
    # Generated XML is optional. Use the original scene directory for relative meshes.
    if scene_path:
        write_xml(root, scene_path)
    assets = root.find('compiler')
    assetdir = ROOT / 'sim/scenes'
    for elem in root.findall('.//asset/mesh'):
        elem.set('file', str((assetdir / assets.get('meshdir', '') / elem.get('file')).resolve()))
    model = mj.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'))
    case = cfg['perturbation']
    joint = model.joint('door_single_hinge')
    model.dof_damping[joint.dofadr] *= case.get('hinge_damping', 1.)
    model.dof_frictionloss[joint.dofadr] *= case.get('hinge_friction', 1.)
    for i in range(model.ngeom):
        geom = model.geom(i)
        body = model.body(model.geom_bodyid[i]).name
        # Scale both partners of the actual pair, preserving MuJoCo's mixing rules.
        if geom.name == 'preview_floor' or body.endswith('FOOT_LINK'):
            geom.friction[0] *= case.get('wheel_mu', 1.)
        if body in ('piper_gripper_link1', 'piper_gripper_link2') or 'handle_' in geom.name:
            geom.friction[0] *= case.get('finger_mu', 1.)
    free = np.flatnonzero(model.jnt_type == mj.mjtJoint.mjJNT_FREE)
    if (len(free) != 1 or model.joint(free[0]).name != 'm1_floating_base' or
            model.nu != 23 or model.neq != 1 or model.eq_type[0] != mj.mjtEq.mjEQ_JOINT or
            joint.id in model.actuator_trnid[:, 0] or sum(model.geom_type == mj.mjtGeom.mjGEOM_PLANE) != 1):
        raise ValueError('P6 free root, passive hinge, one floor or coupled gripper invariant failed')
    return model
