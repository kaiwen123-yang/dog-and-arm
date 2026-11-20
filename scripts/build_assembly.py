#!/usr/bin/env python3
"""Build pinned M1/Piper models and a kinematic assembly preview; no hardware I/O.

The native M1 MJCF remains the dynamics source. The combined URDF is a parallel
description for kinematics/ROS inspection, not an intermediate physics format.
Run fetch_sources.py first. All generated paths remain relative to the repo.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation
import yaml

from model_parts.m1 import build_m1
from model_parts.piper import build_piper
from model_parts.rail_bridge import geometry as bridge_geometry

ROOT = Path(__file__).resolve().parents[1]


def numbers(values):
    return " ".join(f"{float(value):.16g}" for value in values)


def quaternion(rpy):
    x, y, z, w = Rotation.from_euler("xyz", rpy).as_quat()
    return numbers([w, x, y, z])


def section(root, name):
    found = root.find(name)
    return found if found is not None else ET.SubElement(root, name)


def write_xml(root, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def fixed_link(robot, parent, name, xyz, rpy):
    link = ET.SubElement(robot, "link", name=name)
    joint = ET.SubElement(robot, "joint", name=name + "_fixed", type="fixed")
    ET.SubElement(joint, "parent", link=parent)
    ET.SubElement(joint, "child", link=name)
    ET.SubElement(joint, "origin", xyz=numbers(xyz), rpy=numbers(rpy))
    return link


def urdf_shape(link, role, shape, values, xyz=(0, 0, 0), rpy=(0, 0, 0), rgba=None, name=None):
    item = ET.SubElement(link, role, {"name": name} if name else {})
    ET.SubElement(item, "origin", xyz=numbers(xyz), rpy=numbers(rpy))
    geometry = ET.SubElement(item, "geometry")
    if shape == "mesh":
        ET.SubElement(geometry, "mesh", filename=values)
    elif shape == "cylinder":
        ET.SubElement(geometry, "cylinder", radius=str(values[0]), length=str(values[1]))
    else:
        ET.SubElement(geometry, shape, size=numbers(values))
    if rgba is not None and role == "visual":
        material = ET.SubElement(item, "material", name=(name or link.get("name")) + "_material")
        ET.SubElement(material, "color", rgba=numbers(rgba))


def site(body, name, xyz, rpy, color="0.1 0.65 0.95 1"):
    return ET.SubElement(body, "site", name=name, pos=numbers(xyz), quat=quaternion(rpy),
                         size="0.003", rgba=color, group="4")


def box(body, name, xyz, rpy, size, rgba, collision=False):
    return ET.SubElement(body, "geom", name=name, type="box", pos=numbers(xyz),
        quat=quaternion(rpy), size=numbers(np.asarray(size) / 2), rgba=numbers(rgba),
        mass="0", density="0", group="3" if collision else "2",
        contype="1" if collision else "0", conaffinity="1" if collision else "0")


def add_accessories(urdf, mjcf, cfg):
    """Fixed frames in URDF; massless geoms/sites on the same rigid MJCF body."""
    ac, cam = cfg["accessories"], cfg["camera"]
    parent = ac["parent_candidate"]
    body = mjcf.find(f".//body[@name='{parent}']")
    if body is None:
        raise ValueError(f"Missing rigid accessory parent: {parent}")
    bp = ac["bracket_xyz_m"]
    br = ac["bracket_rpy_rad"]
    bracket = fixed_link(urdf, parent, "piper_camera_bracket", bp, br)
    urdf_shape(bracket, "visual", "mesh", "../" + ac["bracket_mesh"], rgba=[.12, .13, .15, 1])
    ET.SubElement(section(mjcf, "asset"), "mesh", name="piper_bracket_candidate_mesh", file=ac["bracket_mesh"])
    ET.SubElement(body, "geom", name="piper_bracket_visual", type="mesh", mesh="piper_bracket_candidate_mesh",
        pos=numbers(bp), quat=quaternion(br), rgba="0.12 0.13 0.15 1", mass="0", density="0",
        group="2", contype="0", conaffinity="0")
    site(body, "piper_camera_bracket", bp, br)
    # A whole convex hull would fill the curved bracket's empty interior.
    # Use two conservative plate proxies; no claim of exact contact geometry.
    rotation = Rotation.from_euler("xyz", br)
    for i, proxy in enumerate(ac["bracket_collision_boxes"]):
        urdf_shape(bracket, "collision", "box", proxy["size_xyz_m"], proxy["xyz_m"])
        pos = np.asarray(bp) + rotation.apply(proxy["xyz_m"])
        box(body, f"piper_bracket_collision_{i}", pos, br, proxy["size_xyz_m"], [.4, .55, .8, .35], True)

    cp, cr, dims = cam["shell_xyz_m"], cam["shell_rpy_rad"], cam["nominal_shell_size_xyz_m"]
    shell = fixed_link(urdf, parent, "piper_camera_shell", cp, cr)
    urdf_shape(shell, "visual", "box", dims, rgba=[.82, .83, .84, 1])
    urdf_shape(shell, "collision", "box", dims)
    box(body, "piper_camera_shell_visual", cp, cr, dims, [.82, .83, .84, 1])
    box(body, "piper_camera_shell_collision", cp, cr, dims, [.4, .55, .8, .35], True)
    site(body, "piper_camera_shell", cp, cr)
    shell_rot = Rotation.from_euler("xyz", cr)
    front = np.asarray(cp) + shell_rot.apply([dims[0] / 2 + .0007, 0, 0])
    box(body, "piper_camera_front_visual", front, cr, [.001, dims[1] * .94, dims[2] * .85], [.025, .03, .04, 1])

    # The optical frame uses ROS x-right/y-down/z-forward. MuJoCo looks -z
    # with +y image-up: convert these conventions explicitly at the same origin.
    op, ori = cam["optical_xyz_m"], cam["optical_rpy_rad"]
    fixed_link(urdf, parent, "piper_wrist_optical_frame", op, ori)
    site(body, "piper_wrist_optical_frame", op, ori, "0.95 0.65 0.1 1")
    mj_rotation = Rotation.from_euler("xyz", ori) * Rotation.from_rotvec([np.pi, 0, 0])
    x, y, z, w = mj_rotation.as_quat()
    ET.SubElement(body, "camera", name="wrist_rgbd", pos=numbers(op), quat=numbers([w, x, y, z]),
                  fovy=str(cam["nominal_fovy_deg"]))
    camera_lookat(body, "wrist_detail", [-.24, -.32, .33], [-.025, 0, .07], 38, up=[-1, 0, 0])


def base_settings(model, cfg):
    compiler = section(model, "compiler")
    compiler.set("angle", "radian")
    compiler.set("fusestatic", "false")
    compiler.set("inertiafromgeom", "false")
    compiler.attrib.pop("meshdir", None)
    option = section(model, "option")
    option.set("timestep", str(cfg["simulation"]["timestep_s"]))
    option.set("gravity", "0 0 -9.81")


def rebase_assets(model):
    out = copy.deepcopy(model)
    for asset in out.findall("asset/mesh"):
        asset.set("file", "../../" + asset.attrib["file"])
    return out


def camera_lookat(world, name, pos, target, fovy=45, up=(0, 0, 1)):
    z = np.asarray(pos, float) - np.asarray(target, float)
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    ET.SubElement(world, "camera", name=name, pos=numbers(pos), xyaxes=numbers([*x, *y]), fovy=str(fovy))


def scene(model, standalone_piper=False, door=False):
    out = copy.deepcopy(model)
    out.set("model", "KINEMATIC_PREVIEW_" + model.get("model", "robot") + ("_door" if door else ""))
    center = [.12, 0, .95] if not standalone_piper else [.05, 0, .4]
    ET.SubElement(out, "statistic", center=numbers(center), extent="1.8" if not standalone_piper else ".9")
    visual = section(out, "visual")
    ET.SubElement(visual, "global", offwidth="1280", offheight="720", azimuth="135", elevation="-20")
    ET.SubElement(visual, "headlight", ambient="0.35 0.35 0.35", diffuse="0.6 0.6 0.6")
    ET.SubElement(visual, "map", znear="0.005", zfar="30")
    world = section(out, "worldbody")
    ET.SubElement(world, "geom", name="preview_floor", type="plane", size="4 4 0.1", mass="0",
                  rgba="0.83 0.85 0.88 1", friction="0.9 0.005 0.0001")
    ET.SubElement(world, "light", name="preview_light", pos="-1 -2 4", dir="0.3 0.3 -1", castshadow="true")
    if standalone_piper:
        camera_lookat(world, "overview", [1.2, -1.5, .9], [.05, 0, .35])
        camera_lookat(world, "side", [.15, -1.7, .5], [.08, 0, .35])
        camera_lookat(world, "front", [1.8, 0, .5], [.08, 0, .35])
    else:
        camera_lookat(world, "overview", [2.15, -2.7, 1.8], [.12, 0, .7])
        camera_lookat(world, "side", [.1, -3.2, 1.0], [.1, 0, .72])
        camera_lookat(world, "front", [3.1, 0, 1.05], [.1, 0, .72])
    if door:
        door_root = ET.parse(ROOT / "sim/components/door_single.xml").getroot()
        world.extend(copy.deepcopy(list(door_root)))
        camera_lookat(world, "door_overview", [3.2, -3.6, 2.15], [.7, 0, .85], 52)
    return out


def save_model(model, path, home, base_z=None):
    model = rebase_assets(model)
    # Compile actual joint order; never assume qpos addresses from actuator order.
    # Keep the old scene usable by --watch until the whole replacement compiles.
    # Same-directory temporary files preserve relative asset references.
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".assembly_build_", suffix=".xml", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        write_xml(model, temporary)
        compiled = mujoco.MjModel.from_xml_path(str(temporary))
        data = mujoco.MjData(compiled)
        if base_z is not None:
            root_joint = mujoco.mj_name2id(compiled, mujoco.mjtObj.mjOBJ_JOINT, "m1_floating_base")
            adr = int(compiled.jnt_qposadr[root_joint])
            data.qpos[adr:adr + 7] = [0, 0, base_z, 1, 0, 0, 0]
        for name, value in home.items():
            joint = mujoco.mj_name2id(compiled, mujoco.mjtObj.mjOBJ_JOINT, name)
            if joint < 0:
                raise ValueError(f"Home joint not found: {name}")
            if compiled.jnt_limited[joint] and not (compiled.jnt_range[joint, 0] <= value <= compiled.jnt_range[joint, 1]):
                raise ValueError(f"Home joint outside source limits: {name}={value}")
            data.qpos[compiled.jnt_qposadr[joint]] = value
        ET.SubElement(section(model, "keyframe"), "key", name="home", qpos=numbers(data.qpos))
        write_xml(model, temporary)
        compiled = mujoco.MjModel.from_xml_path(str(temporary))
        temporary.chmod(0o644)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    data = mujoco.MjData(compiled)
    mujoco.mj_resetDataKeyframe(compiled, data, 0)
    mujoco.mj_forward(compiled, data)
    return {"file": path.relative_to(ROOT).as_posix(), "nq": compiled.nq, "nv": compiled.nv,
            "nu": compiled.nu, "neq": compiled.neq, "nbody_including_world": compiled.nbody,
            "mass_kg": float(compiled.body_mass.sum()), "home_qpos": data.qpos.tolist(),
            "contacts_at_home": int(data.ncon), "mj_step_calls": 0}


def normalize_metadata(value):
    if isinstance(value, dict):
        return {k: normalize_metadata(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_metadata(v) for v in value]
    if isinstance(value, str) and value.startswith(str(ROOT) + "/"):
        return str(Path(value).relative_to(ROOT))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["m1", "piper", "combined", "all"], default="all")
    args = parser.parse_args()
    cfg = yaml.safe_load((ROOT / "config/assembly.yaml").read_text())
    if cfg["accessories"]["accessory_payload_mode"] != "omitted" or cfg["accessories"]["geometry_mass_kg"] != 0:
        raise ValueError("This version implements omitted accessory payload only; adding real mass requires explicit inertial data.")
    if not cfg["robot"]["floating_base"]:
        raise ValueError("This builder preserves the M1 floating base; a fixed-base P4 scene is a separate next-stage model.")
    if (cfg["robot"]["base_prefix"], cfg["robot"]["arm_prefix"]) != ("m1_", "piper_"):
        raise ValueError("This dedicated assembly uses the documented m1_ and piper_ frame names.")
    if cfg["gripper"]["tcp_parent"] != "piper_gripper_base":
        raise ValueError("The nominal TCP is currently attached to piper_gripper_base; change its xyz, not the rigid parent.")
    result = {"stage": args.stage, "mujoco_version": mujoco.__version__, "mode": "KINEMATIC_PREVIEW",
              "hardware_access": False, "dynamics_validated": False, "models": []}
    arm_home = {f"piper_joint{i}": value for i, value in enumerate(cfg["preview"]["arm_home_rad"], 1)}
    width = cfg["preview"]["gripper_width_m"]
    arm_home.update(piper_gripper_joint1=width / 2, piper_gripper_joint2=-width / 2)
    need_m1, need_piper = args.stage != "piper", args.stage != "m1"
    if need_m1:
        m1 = build_m1(ROOT / "vendor/matrix_python_sdk/model/zgws/zgws.xml", ROOT)
        base_settings(m1["mjcf"], cfg)
        base_z = cfg["preview"]["m1_root_z_m"]
        m1_home = m1["initial_pose"]["standing_candidate"]["joint_positions_rad"]
        write_xml(m1["urdf"], ROOT / "description/m1_derived.urdf")
        result["models"].append(save_model(scene(m1["mjcf"]), ROOT / "sim/scenes/m1_preview.xml", m1_home, base_z))
        result["m1_notes"] = m1["notes"]
    if need_piper:
        piper = build_piper(ROOT / "vendor/agx_arm_urdf", ROOT)
        tcp = numbers(cfg["gripper"]["tcp_nominal_xyz_m"])
        piper["urdf"].find("joint[@name='piper_tcp_nominal_joint']/origin").set("xyz", tcp)
        piper["mjcf"].find(".//body[@name='piper_tcp_nominal']").set("pos", tcp)
        base_settings(piper["mjcf"], cfg)
        # Their official STL shells overlap by 6 mm at the joint. In the
        # floating assembly MuJoCo's parent filter already removes this pair;
        # explicitly match that intent for the world-fixed standalone preview.
        ET.SubElement(section(piper["mjcf"], "contact"), "exclude", name="piper_base_adjacent",
                      body1="piper_base_link", body2="piper_link1")
        add_accessories(piper["urdf"], piper["mjcf"], cfg)
        write_xml(piper["urdf"], ROOT / "description/piper_h.urdf")
        result["models"].append(save_model(scene(piper["mjcf"], standalone_piper=True), ROOT / "sim/scenes/piper_preview.xml", arm_home))
        result["piper_notes"] = piper["notes"]
        result["piper_notes"].append("Explicit base_link/link1 adjacent collision exclusion also applies when the Piper root is welded to world; source overlapping STL shells are unchanged.")
    if args.stage in ("combined", "all"):
        mount = cfg["arm_mount"]
        urdf, mjcf = copy.deepcopy(m1["urdf"]), copy.deepcopy(m1["mjcf"])
        urdf.set("name", "m1_piper_h_with_gripper_and_nominal_camera")
        mjcf.set("model", "m1_piper_h_with_gripper_and_nominal_camera")
        ET.SubElement(section(mjcf, "custom"), "text", name="mount_revision", data=mount["revision"])
        urdf.extend(copy.deepcopy(list(piper["urdf"])))
        frame = fixed_link(urdf, mount["parent_link"], "m1_arm_mount", mount["xyz_m"], mount["rpy_rad"])
        joint = ET.SubElement(urdf, "joint", name="piper_base_mount_fixed", type="fixed")
        ET.SubElement(joint, "parent", link="m1_arm_mount")
        ET.SubElement(joint, "child", link=mount["child_link"])
        ET.SubElement(joint, "origin", xyz="0 0 0", rpy="0 0 0")
        parent_body = mjcf.find(f".//body[@name='{mount['parent_link']}']")
        site(parent_body, "m1_arm_mount", mount["xyz_m"], mount["rpy_rad"])
        mesh, solids, bolts = bridge_geometry(ROOT, mount)
        ET.SubElement(section(mjcf, "asset"), "mesh", name="m1_rail_bridge_plate", file=mesh)
        mount_inv = Rotation.from_euler("xyz", mount["rpy_rad"]).inv()
        local_rpy = mount_inv.as_euler("xyz")
        for part, center, size in solids:
            name = "m1_mount_" + part
            local = mount_inv.apply(center - mount["xyz_m"])
            color = [.30, .39, .48, 1] if part == "plate" else [.19, .23, .27, 1]
            if part == "plate":
                urdf_shape(frame, "visual", "mesh", "../" + mesh, local, local_rpy, color, name=name + "_visual")
                ET.SubElement(parent_body, "geom", name=name+"_visual", type="mesh", mesh="m1_rail_bridge_plate",
                              pos=numbers(center), rgba=numbers(color), group="2", mass="0", density="0",
                              contype="0", conaffinity="0")
            else:
                urdf_shape(frame, "visual", "box", size, local, local_rpy, color, name=name + "_visual")
                box(parent_body, name+"_visual", center, [0,0,0], size, color)
            urdf_shape(frame, "collision", "box", size, local, local_rpy, name=name + "_collision")
            box(parent_body, name+"_collision", center, [0,0,0], size, color, True)
        for part, center, radius, length in bolts:
            local = mount_inv.apply(center - mount["xyz_m"])
            color = [.62,.65,.68,1]
            urdf_shape(frame, "visual", "cylinder", [radius, length], local, local_rpy, color, name="m1_mount_" + part)
            ET.SubElement(parent_body, "geom", name="m1_mount_"+part, type="cylinder", pos=numbers(center),
                          size=numbers([radius,length/2]), rgba=numbers(color), group="2",
                          mass="0", density="0", contype="0", conaffinity="0")
        arm = copy.deepcopy(piper["mjcf"].find("worldbody/body"))
        arm.set("pos", numbers(mount["xyz_m"]))
        arm.set("quat", quaternion(mount["rpy_rad"]))
        parent_body.append(arm)
        for tag in ("asset", "actuator", "sensor", "equality", "contact", "tendon"):
            src = piper["mjcf"].find(tag)
            if src is not None:
                section(mjcf, tag).extend(copy.deepcopy(list(src)))
        write_xml(urdf, ROOT / "description/m1_piper.urdf")
        home = {**m1_home, **arm_home}
        for path, model in (
            ("sim/robots/m1_piper.xml", mjcf),
            ("sim/scenes/assembly_preview.xml", scene(mjcf)),
            ("sim/scenes/assembly_with_door.xml", scene(mjcf, door=True)),
        ):
            result["models"].append(save_model(model, ROOT / path, home, base_z))
        mapping = {"floating_joint": m1["free_joint_name"], "base_joints": m1["joint_names"],
            "wheel_joints": m1["wheel_joint_names"], "arm_joints": piper["arm_joint_names"],
            "finger_joints": piper["finger_joint_names"], "gripper": piper["gripper"],
            "actuated_joints": m1["actuated_joint_names"] + piper["actuated_joint_names"],
            "actuators": m1["actuator_names"] + piper["actuator_names"],
            "actuator_input": "generalized motor forces; not position setpoints",
            "urdf_base": "fixed-root description; scene supplies floating pose in MJCF"}
        (ROOT / "description/joint_map.yaml").write_text(yaml.safe_dump(mapping, allow_unicode=True, sort_keys=False))
        result["assets"] = {"m1": m1["assets"], "piper": piper["asset_provenance"]}
        result["assumptions"] = {"mount": mount, "accessories": cfg["accessories"], "camera": cfg["camera"], "preview": cfg["preview"]}
    out = ROOT / f"reports/assembly_build_{args.stage}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(normalize_metadata(result), indent=2, ensure_ascii=False) + "\n")
    for model in result["models"]:
        print(f"{model['file']}: nq={model['nq']} nv={model['nv']} nu={model['nu']} neq={model['neq']} mass={model['mass_kg']:.9f} kg")
    print(f"KINEMATIC_PREVIEW only; wrote {out.relative_to(ROOT)}. No hardware I/O or mj_step.")


if __name__ == "__main__":
    main()
