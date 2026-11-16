"""Derive the Piper H + official parallel gripper model without ROS/xacro.

``build_piper`` returns ElementTree roots for a mountable URDF and MJCF.
It copies the official collision STL files into ``assets/converted`` and uses
those same shapes for a deliberately simplified visual model.  No DAE file is
parsed or converted: Collada scene transforms, materials and units therefore
cannot be silently lost by an incomplete conversion.

The URDF retains the official empty width joint and its two mimic joints.  The
MJCF has two physical finger joints, one equality constraint, and one motor;
``width = 2 * gripper_joint1``.  There is no free joint or hardware interface.

Mesh paths in the returned URDF are relative to ``description``.  MJCF
paths are relative to the project root.  A caller writing elsewhere must
rebase them using the returned ``asset_files`` / ``mesh_files`` metadata.
"""

from __future__ import annotations

import copy
import math
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


EXPECTED_SOURCE_COMMIT = "680fa925cd00db7e2628563d2edc5540963045de"
_XACRO = "{http://www.ros.org/wiki/xacro}"
_ROS_PREFIX = "$(find agx_arm_description)/agx_arm_urdf/"
_MESH_PREFIX = "package://agx_arm_description/agx_arm_urdf/"


def _numbers(text: str, size: int) -> list[float]:
    values = [float(value) for value in text.split()]
    if len(values) != size or not all(math.isfinite(value) for value in values):
        raise ValueError(f"Expected {size} finite numbers, got {text!r}")
    return values


def _fmt(values) -> str:
    return " ".join(format(float(value), ".17g") for value in values)


def _origin(element: ET.Element) -> tuple[list[float], list[float]]:
    origin = element.find("origin")
    if origin is None:
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    return (_numbers(origin.get("xyz", "0 0 0"), 3),
            _numbers(origin.get("rpy", "0 0 0"), 3))


def _quaternion(rpy: list[float]) -> list[float]:
    """URDF fixed-axis RPY, Rz(yaw) Ry(pitch) Rx(roll), to MJCF wxyz."""
    r, p, y = (angle / 2.0 for angle in rpy)
    cr, sr, cp, sp, cy, sy = (math.cos(r), math.sin(r), math.cos(p),
                             math.sin(p), math.cos(y), math.sin(y))
    return [cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy]


def _rotation(rpy: list[float]) -> list[list[float]]:
    w, x, y, z = _quaternion(rpy)
    return [[1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
            [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
            [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)]]


def _inside_repo(repo: Path, relative: str) -> Path:
    path = (repo / relative).resolve()
    if not path.is_relative_to(repo):
        raise ValueError(f"Source path escapes repository: {relative}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _expand_includes(path: Path, repo: Path, seen: tuple[Path, ...] = ()) -> ET.Element:
    """Expand the pinned model's plain include, refusing arbitrary xacro code."""
    if path in seen:
        raise ValueError(f"Recursive xacro include: {path}")
    source = ET.parse(path).getroot()
    if source.tag != "robot":
        raise ValueError(f"Expected a robot root in {path}")
    result = ET.Element("robot", dict(source.attrib))
    for child in source:
        if child.tag == _XACRO + "include":
            filename = child.get("filename", "")
            if not filename.startswith(_ROS_PREFIX):
                raise ValueError(f"Unsupported xacro include: {filename}")
            included = _inside_repo(repo, filename[len(_ROS_PREFIX):])
            expanded = _expand_includes(included, repo, seen + (path,))
            result.extend(copy.deepcopy(list(expanded)))
        elif child.tag.startswith(_XACRO):
            raise ValueError(f"Unsupported xacro element: {child.tag}")
        else:
            result.append(copy.deepcopy(child))
    # This is intentionally not a general-purpose xacro interpreter.
    if "${" in ET.tostring(result, encoding="unicode"):
        raise ValueError("Unexpanded xacro expression in source model")
    return result


def _index(robot: ET.Element) -> tuple[dict[str, ET.Element], dict[str, ET.Element]]:
    result = []
    for kind in ("link", "joint"):
        elements = robot.findall(kind)
        indexed = {element.attrib["name"]: element for element in elements}
        if len(indexed) != len(elements):
            raise ValueError(f"Duplicate {kind} names in assembled Piper model")
        result.append(indexed)
    return result[0], result[1]


def _prepare_assets(robot: ET.Element, repo: Path, project: Path,
                    prefix: str) -> tuple[list[str], dict[str, str], list[dict]]:
    """Use official STL collision geometry for both collision and visual."""
    outdir = project / "assets" / "converted"
    outdir.mkdir(parents=True, exist_ok=True)
    asset_files, mesh_files, provenance = [], {}, []
    for link in robot.findall("link"):
        link_name = link.attrib["name"]
        collisions = link.findall("collision")
        if link.findall("visual") and not collisions:
            raise ValueError(f"No official collision geometry for visual fallback: {link_name}")
        for visual in list(link.findall("visual")):
            link.remove(visual)
        for index, collision in enumerate(collisions):
            geometry = collision.find("geometry")
            mesh = geometry.find("mesh") if geometry is not None else None
            if mesh is None:
                raise ValueError(f"Expected official STL mesh for {link_name}")
            filename = mesh.get("filename", "")
            if not filename.startswith(_MESH_PREFIX):
                raise ValueError(f"Unsupported mesh URI: {filename}")
            source = _inside_repo(repo, filename[len(_MESH_PREFIX):])
            if source.suffix.lower() != ".stl":
                raise ValueError(f"STL fallback cannot silently convert {source}")
            suffix = f"_{index}" if index else ""
            stem = f"{prefix}{link_name}{suffix}_mesh"
            destination = outdir / f"{stem}.stl"
            shutil.copyfile(source, destination)
            relative = destination.relative_to(project).as_posix()
            mesh.set("filename", "../" + relative)
            # A single mesh asset is shared by the noncolliding visual and
            # collision geom.  Names/basenames are unique across all links.
            visual = ET.Element("visual", {"name": f"{prefix}{link_name}{suffix}_visual"})
            for part in collision:
                if part.tag in ("origin", "geometry"):
                    visual.append(copy.deepcopy(part))
            material = ET.SubElement(visual, "material", {"name": f"{prefix}stl_gray"})
            ET.SubElement(material, "color", {"rgba": "0.22 0.24 0.27 1"})
            link.append(visual)
            asset_files.append(relative)
            mesh_files[stem] = relative
            provenance.append({"output": relative,
                               "source": source.relative_to(repo).as_posix(),
                               "operation": "verbatim_copy_official_collision_stl"})
    return asset_files, mesh_files, provenance


def _add_inertia(body: ET.Element, link: ET.Element) -> float:
    inertial = link.find("inertial")
    if inertial is None:
        return 0.0
    mass_element, tensor = inertial.find("mass"), inertial.find("inertia")
    if mass_element is None or tensor is None:
        raise ValueError(f"Incomplete official inertia on {link.attrib['name']}")
    mass = float(mass_element.attrib["value"])
    if not math.isfinite(mass) or mass <= 0:
        raise ValueError(f"Invalid mass on {link.attrib['name']}: {mass}")
    values = {key: float(tensor.attrib[key]) for key in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")}
    if not all(math.isfinite(value) for value in values.values()):
        raise ValueError(f"Invalid inertia on {link.attrib['name']}")
    inertia = [[values["ixx"], values["ixy"], values["ixz"]],
               [values["ixy"], values["iyy"], values["iyz"]],
               [values["ixz"], values["iyz"], values["izz"]]]
    xyz, rpy = _origin(inertial)
    rotation = _rotation(rpy)
    # MJCF fullinertia is expressed at the COM in body-aligned axes. Rotate
    # the URDF inertial-frame tensor; the COM remains at its URDF xyz.
    rotated = [[sum(rotation[i][k] * inertia[k][l] * rotation[j][l]
                    for k in range(3) for l in range(3))
                for j in range(3)] for i in range(3)]
    full = [rotated[0][0], rotated[1][1], rotated[2][2],
            rotated[0][1], rotated[0][2], rotated[1][2]]
    ET.SubElement(body, "inertial", {"pos": _fmt(xyz), "mass": format(mass, ".17g"),
                                     "fullinertia": _fmt(full)})
    return mass


def _make_mjcf(robot: ET.Element, mesh_files: dict[str, str], prefix: str) -> tuple[ET.Element, float]:
    links, joints = _index(robot)
    master_name, dummy_name = prefix + "gripper", prefix + "gripper_link"
    master, dummy = joints[master_name], links[dummy_name]
    if (list(dummy) or master.find("child").get("link") != dummy_name
            or any(joint.find("parent").get("link") == dummy_name for joint in joints.values())):
        raise ValueError("Official virtual gripper master is no longer an empty leaf")
    joints = {name: joint for name, joint in joints.items() if name != master_name}
    links = {name: link for name, link in links.items() if name != dummy_name}
    root_name = prefix + "base_link"
    by_parent: dict[str, list[ET.Element]] = {}
    children = set()
    for joint in joints.values():
        parent, child = joint.find("parent").get("link"), joint.find("child").get("link")
        if parent not in links or child not in links or child in children:
            raise ValueError(f"Invalid Piper link tree at {joint.attrib['name']}")
        children.add(child)
        by_parent.setdefault(parent, []).append(joint)
    if set(links) - children != {root_name}:
        raise ValueError("Piper must have exactly one base_link root after removing world")
    mjcf = ET.Element("mujoco", {"model": prefix + "h_with_gripper"})
    ET.SubElement(mjcf, "compiler", {"angle": "radian", "autolimits": "true",
                                     "inertiafromgeom": "false", "fusestatic": "false"})
    asset = ET.SubElement(mjcf, "asset")
    for name, file in mesh_files.items():
        ET.SubElement(asset, "mesh", {"name": name, "file": file, "scale": "1 1 1"})
    world = ET.SubElement(mjcf, "worldbody")
    total_mass, visited = 0.0, set()

    def add_body(container: ET.Element, name: str, incoming: ET.Element | None = None):
        nonlocal total_mass
        if name in visited:
            raise ValueError(f"Cycle in Piper link tree at {name}")
        visited.add(name)
        xyz, rpy = ([0., 0., 0.], [0., 0., 0.]) if incoming is None else _origin(incoming)
        body = ET.SubElement(container, "body", {"name": name, "pos": _fmt(xyz),
                                               "quat": _fmt(_quaternion(rpy))})
        if incoming is not None and incoming.get("type") != "fixed":
            kind = incoming.get("type")
            if kind not in ("revolute", "prismatic"):
                raise ValueError(f"Unsupported Piper joint type: {kind}")
            axis_element, limit = incoming.find("axis"), incoming.find("limit")
            axis = _numbers(axis_element.get("xyz", "1 0 0") if axis_element is not None else "1 0 0", 3)
            if limit is None or sum(value*value for value in axis) <= 0:
                raise ValueError(f"Missing limit or invalid axis: {incoming.attrib['name']}")
            ET.SubElement(body, "joint", {"name": incoming.attrib["name"],
                "type": "hinge" if kind == "revolute" else "slide", "axis": _fmt(axis),
                "pos": "0 0 0", "limited": "true", "ref": "0", "springref": "0",
                "damping": "0", "frictionloss": "0", "armature": "0", "stiffness": "0",
                "range": f"{limit.attrib['lower']} {limit.attrib['upper']}"})
        total_mass += _add_inertia(body, links[name])
        for role in ("visual", "collision"):
            for index, geometry_element in enumerate(links[name].findall(role)):
                mesh = geometry_element.find("geometry/mesh")
                mesh_name = Path(mesh.attrib["filename"]).stem
                scale = _numbers(mesh.get("scale", "1 1 1"), 3)
                if scale != [1.0, 1.0, 1.0]:
                    raise ValueError("Pinned Piper STL assets unexpectedly specify a mesh scale")
                pos, angles = _origin(geometry_element)
                attributes = {"name": f"{name}_{role}_{index}", "type": "mesh",
                    "mesh": mesh_name, "pos": _fmt(pos), "quat": _fmt(_quaternion(angles)),
                    "mass": "0", "density": "0", "rgba": "0.22 0.24 0.27 1",
                    "group": "2" if role == "visual" else "3",
                    "contype": "0" if role == "visual" else "1",
                    "conaffinity": "0" if role == "visual" else "1",
                    "condim": "3", "friction": "1 0.005 0.0001", "margin": "0", "gap": "0"}
                ET.SubElement(body, "geom", attributes)
        if name == prefix + "tcp_nominal":
            ET.SubElement(body, "site", {"name": prefix + "tcp_nominal", "type": "sphere",
                "size": "0.003", "rgba": "0.1 0.8 0.2 1", "group": "4"})
        for joint in by_parent.get(name, []):
            add_body(body, joint.find("child").attrib["link"], joint)

    add_body(world, root_name)
    if visited != set(links):
        raise ValueError("Disconnected Piper links")
    equality = ET.SubElement(mjcf, "equality")
    ET.SubElement(equality, "joint", {"name": prefix + "finger_symmetry",
        "joint1": prefix + "gripper_joint2", "joint2": prefix + "gripper_joint1",
        "polycoef": "0 -1 0 0 0", "solref": "0.02 1", "solimp": "0.9 0.95 0.001 0.5 2"})
    actuator = ET.SubElement(mjcf, "actuator")
    for name in [prefix + f"joint{i}" for i in range(1, 7)] + [prefix + "gripper_joint1"]:
        effort = float(joints[name].find("limit").attrib["effort"])
        if not math.isfinite(effort) or effort <= 0:
            raise ValueError(f"Invalid actuator effort in source: {name}")
        bounds = _fmt([-effort, effort])
        ET.SubElement(actuator, "motor", {"name": name + "_motor", "joint": name,
            "gear": "1", "ctrllimited": "true", "ctrlrange": bounds,
            "forcelimited": "true", "forcerange": bounds})
    return mjcf, total_mass


def build_piper(source_repo: Path, project_root: Path, prefix: str = "piper_") -> dict:
    """Build detached Piper H trees; only copied assets are written to disk.

    ``source_repo`` must be the root of ``agilexrobotics/agx_arm_urdf``; the
    caller pins/verifies its revision.  ``urdf`` and ``mjcf`` are ET.Element
    roots.  Neither output contains a world attachment or freejoint.  Motors
    expose generalized force inputs for later controller integration, not a
    commissioned or automatically enabled hardware controller.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", prefix):
        raise ValueError("Use a nonempty alphanumeric/underscore model prefix")
    repo, project = Path(source_repo).resolve(strict=True), Path(project_root).resolve()
    xacro = _inside_repo(repo, "piper_h/urdf/piper_h_with_gripper_description.xacro")
    robot = _expand_includes(xacro, repo)
    links, joints = _index(robot)
    world, attachment = links.get("world"), joints.get("world_to_base_link")
    if world is None or list(world) or attachment is None:
        raise ValueError("Unexpected official world attachment; review before mounting")
    if (attachment.get("type") != "fixed" or attachment.find("parent").get("link") != "world"
            or attachment.find("child").get("link") != "base_link"
            or _origin(attachment) != ([0., 0., 0.], [0., 0., 0.])):
        raise ValueError("Nonidentity official world attachment requires explicit handling")
    robot.remove(world)
    robot.remove(attachment)
    # Assert the source mimic algebra before reducing it for MuJoCo 3.3.
    for name, multiplier in (("gripper_joint1", 0.5), ("gripper_joint2", -0.5)):
        mimic = joints[name].find("mimic")
        if (mimic is None or mimic.get("joint") != "gripper"
                or float(mimic.get("multiplier", "1")) != multiplier
                or float(mimic.get("offset", "0")) != 0):
            raise ValueError("Official gripper mimic relationship changed")
    asset_files, mesh_files, provenance = _prepare_assets(robot, repo, project, prefix)
    ET.SubElement(robot, "link", {"name": "tcp_nominal"})
    tcp_joint = ET.SubElement(robot, "joint", {"name": "tcp_nominal_joint", "type": "fixed"})
    ET.SubElement(tcp_joint, "parent", {"link": "gripper_base"})
    ET.SubElement(tcp_joint, "child", {"link": "tcp_nominal"})
    ET.SubElement(tcp_joint, "origin", {"xyz": "0 0 0.138", "rpy": "0 0 0"})
    robot.set("name", prefix + "h_with_gripper")
    for link in robot.findall("link"):
        link.set("name", prefix + link.attrib["name"])
    for joint in robot.findall("joint"):
        joint.set("name", prefix + joint.attrib["name"])
        for tag in ("parent", "child"):
            reference = joint.find(tag)
            reference.set("link", prefix + reference.attrib["link"])
        mimic = joint.find("mimic")
        if mimic is not None:
            mimic.set("joint", prefix + mimic.attrib["joint"])
    mjcf, mass = _make_mjcf(robot, mesh_files, prefix)
    arm_names = [prefix + f"joint{i}" for i in range(1, 7)]
    finger_names = [prefix + "gripper_joint1", prefix + "gripper_joint2"]
    return {
        "urdf": robot, "mjcf": mjcf, "joint_names": arm_names + finger_names,
        "arm_joint_names": arm_names, "finger_joint_names": finger_names,
        "actuated_joint_names": arm_names + finger_names[:1],
        "actuator_names": [name + "_motor" for name in arm_names + finger_names[:1]],
        "asset_files": asset_files, "mesh_files": mesh_files, "asset_provenance": provenance,
        "source_revision_expected": EXPECTED_SOURCE_COMMIT,
        "frames": {"root": prefix + "base_link", "flange": prefix + "flange_link",
                   "gripper_base": prefix + "gripper_base", "tcp_site": prefix + "tcp_nominal"},
        "gripper": {"urdf_width_joint": prefix + "gripper", "mjcf_input_joint": finger_names[0],
                    "width_m_per_input_q": 2.0, "width_range_m": [0.0, 0.1],
                    "follower_joint": finger_names[1], "follower_multiplier": -1.0},
        "mass_kg": mass,
        "notes": [
            "Official Piper H with-gripper Xacro expanded once; standalone gripper not appended.",
            "Removed the source world/world_to_base_link; caller mounts piper_base_link with a fixed transform.",
            "Visuals use verbatim official collision STL, with flat gray material. DAE scenes/materials were NOT converted.",
            "Official STL coordinates/scales retained; no guessed millimeter conversion applied.",
            "Mesh collision uses MuJoCo convex hulls, so concavities and fine contact geometry are simplified.",
            "Contact friction/condim and equality solver settings use explicit MuJoCo default assumptions; source URDF has no calibrated contact data.",
            "Official link mass, COM and inertia retained; visual/collision geoms contribute zero inferred mass.",
            "URDF keeps official width master and mimic; MJCF removes empty master and constrains finger2=-finger1.",
            "One gripper motor acts on finger1 in N; opening width=2*q_finger1. This is not a calibrated grip-force interface.",
            "Seven motor force bounds are URDF effort limits, not independently verified hardware ratings; velocity limits need controller enforcement.",
            "TCP at gripper_base+[0,0,0.138] m is nominal; camera, hand-eye calibration and accessory payload are outside this module.",
            "No freejoint, hardware interface, auto-enable, controller gain, or successful dynamics claim is supplied.",
            "URDF mesh paths assume description; MJCF mesh paths assume project root. Rebase when writing elsewhere.",
        ],
    }
