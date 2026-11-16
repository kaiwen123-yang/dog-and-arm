"""Build the M1 description from the official, pinned ZGWS MJCF.

The returned MJCF retains the upstream dynamics and floating base.  The URDF
is a derived description of the same body tree, without a world placement.
No generic MJCF-to-URDF conversion or locomotion controller is implemented.
"""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET


URDF_VELOCITY_PLACEHOLDER_RAD_S = 1.0
SOURCE_REVISION = "7c63590c21beba2f633c344b96bc29a695d7a807"
SOURCE_URL = (
    "https://github.com/zsibot/MATRiX_Python_SDK/blob/"
    + SOURCE_REVISION + "/model/zgws/zgws.xml"
)


def _numbers(value: str | None, default: tuple[float, ...]) -> list[float]:
    return list(default) if value is None else [float(item) for item in value.split()]


def _text(values) -> str:
    return " ".join(format(float(value), ".16g") for value in values)


def _quat_rpy(quaternion: list[float]) -> list[float]:
    """MuJoCo wxyz quaternion to URDF fixed-axis roll, pitch, yaw."""
    norm = math.sqrt(sum(value * value for value in quaternion))
    w, x, y, z = [value / norm for value in quaternion]
    return [
        math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y)),
        math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x)))),
        math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)),
    ]


def _origin(parent: ET.Element, element: ET.Element) -> None:
    ET.SubElement(
        parent, "origin",
        xyz=_text(_numbers(element.get("pos"), (0.0, 0.0, 0.0))),
        rpy=_text(_quat_rpy(_numbers(element.get("quat"), (1.0, 0.0, 0.0, 0.0)))),
    )


def _body_frame_inertia(inertial: ET.Element) -> dict[str, str]:
    """Rotate source principal moments into the body frame without changing them.

    Some URDF importers disregard inertial-origin RPY when diagonalizing the
    supplied tensor.  An identity inertial orientation plus the full body-frame
    tensor expresses the same inertia unambiguously in both URDF and MuJoCo.
    """
    quaternion = _numbers(inertial.get("quat"), (1.0, 0.0, 0.0, 0.0))
    norm = math.sqrt(sum(value * value for value in quaternion))
    w, x, y, z = [value / norm for value in quaternion]
    rotation = [
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ]
    diagonal = _numbers(inertial.get("diaginertia"), ())
    if len(diagonal) != 3:
        raise ValueError("Pinned ZGWS inertias must contain three principal moments")
    tensor = [
        [sum(rotation[i][k] * diagonal[k] * rotation[j][k] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]
    return {
        name: _text([tensor[i][j]])
        for name, i, j in (("ixx", 0, 0), ("iyy", 1, 1), ("izz", 2, 2),
                           ("ixy", 0, 1), ("ixz", 0, 2), ("iyz", 1, 2))
    }


def _copy_stl(source: Path, destination: Path) -> dict:
    """Copy geometry; normalize only an ambiguous binary STL header if present."""
    data = source.read_bytes()
    triangle_count = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else None
    is_binary = triangle_count is not None and len(data) == 84 + 50 * triangle_count
    header_rewritten = is_binary and data[:5].lower() == b"solid"
    bounds = None
    if is_binary:
        lower = [math.inf, math.inf, math.inf]
        upper = [-math.inf, -math.inf, -math.inf]
        for triangle in struct.iter_unpack("<12fH", memoryview(data)[84:]):
            for offset in (3, 6, 9):
                for axis in range(3):
                    coordinate = triangle[offset + axis]
                    lower[axis] = min(lower[axis], coordinate)
                    upper[axis] = max(upper[axis], coordinate)
        bounds = {"min": lower, "max": upper}
    if header_rewritten:
        header = b"Binary STL: unchanged official ZGWS triangle data".ljust(80, b" ")
        data = header + data[80:]
    destination.write_bytes(data)
    return {
        "binary_stl": is_binary,
        "triangle_count": triangle_count if is_binary else None,
        "binary_stl_header_rewritten": header_rewritten,
        "vertex_scaling_applied": False,
        "triangles_removed": 0,
        "bounds_m": bounds,
    }


def _body_tree(body: ET.Element, parent: ET.Element | None = None):
    yield body, parent
    for child in body.findall("body"):
        yield from _body_tree(child, body)


def _urdf_geometry(parent: ET.Element, geom: ET.Element, meshes: dict) -> None:
    geometry = ET.SubElement(parent, "geometry")
    kind = geom.get("type", "sphere")
    if kind == "mesh":
        asset = meshes[geom.attrib["mesh"]]
        mesh = ET.SubElement(geometry, "mesh", filename=asset["urdf_filename"])
        if asset["scale"] is not None:
            mesh.set("scale", asset["scale"])
    elif kind == "box":
        ET.SubElement(geometry, "box", size=_text(2.0 * value for value in _numbers(geom.get("size"), ())))
    else:
        raise ValueError(f"Pinned ZGWS conversion expects mesh/box geoms, found {kind!r}")


def _commented_stance(source_text: str, joint_names: list[str]) -> dict | None:
    """Expose the upstream commented home pose as a candidate, never as a controller."""
    for comment in re.findall(r"<!--(.*?)-->", source_text, flags=re.DOTALL):
        match = re.search(r'<key\b[^>]*\bname=["\']home["\'][^>]*/>', comment)
        if match is None:
            continue
        key = ET.fromstring(match.group(0))
        qpos = _numbers(key.get("qpos"), ())
        if len(qpos) != 7 + len(joint_names):
            continue
        return {
            "source": "commented home keyframe in the official zgws.xml",
            "active_upstream_keyframe": False,
            "dynamic_standing_validated": False,
            "root_position_m": qpos[:3],
            "root_quaternion_wxyz": qpos[3:7],
            "joint_positions_rad": dict(zip(joint_names, qpos[7:])),
            "source_ctrl_ignored": True,
            "note": "Set qpos for assembly/FK only; the commented ctrl is not a standing controller.",
        }
    return None


def build_m1(source_xml: Path, project_root: Path, prefix: str = "m1_") -> dict:
    """Return native MJCF and a derived URDF, with copied named mesh assets.

    URDF mesh paths are relative to a URDF placed immediately under description/.
    MJCF mesh file paths are relative to project_root; the scene assembler must
    rebase them when it writes a scene in another directory.  Neither XML tree
    is written by this function.  The original vendor files remain unchanged.
    """
    source_xml = Path(source_xml).resolve()
    project_root = Path(project_root).resolve()
    source_text = source_xml.read_text(encoding="utf-8")
    source = ET.fromstring(source_text)
    native = deepcopy(source)
    compiler = source.find("compiler")
    mesh_directory = source_xml.parent / (compiler.get("meshdir", "") if compiler is not None else "")
    converted = project_root / "assets/converted"
    converted.mkdir(parents=True, exist_ok=True)

    assets = []
    meshes = {}
    for mesh in source.findall("asset/mesh"):
        original_name = mesh.attrib["name"]
        output_name = prefix + original_name + ".stl"
        source_path = mesh_directory / mesh.attrib["file"]
        output_path = converted / output_name
        copied = _copy_stl(source_path, output_path)
        record = {
            "source_name": original_name,
            "name": prefix + original_name,
            "source_path": str(source_path),
            "output_path": str(output_path),
            "project_relative_path": "assets/converted/" + output_name,
            "urdf_filename": "../assets/converted/" + output_name,
            "scale": mesh.get("scale"),
            **copied,
        }
        assets.append(record)
        meshes[original_name] = record

    source_root_body = source.find("worldbody/body")
    if source_root_body is None:
        raise ValueError("ZGWS source has no root body")
    body_pairs = list(_body_tree(source_root_body))
    urdf = ET.Element("robot", name=prefix + "zgws_derived")
    joint_names = []
    joint_info = []
    wheel_geometry = []

    for body, parent_body in body_pairs:
        original_body_name = body.attrib["name"]
        body_name = prefix + original_body_name
        link = ET.SubElement(urdf, "link", name=body_name)
        inertial = body.find("inertial")
        if inertial is not None:
            target = ET.SubElement(link, "inertial")
            ET.SubElement(
                target, "origin",
                xyz=_text(_numbers(inertial.get("pos"), (0.0, 0.0, 0.0))),
                rpy="0 0 0",
            )
            ET.SubElement(target, "mass", value=inertial.attrib["mass"])
            ET.SubElement(target, "inertia", **_body_frame_inertia(inertial))

        for index, geom in enumerate(body.findall("geom")):
            contact = int(geom.get("contype", "1")) != 0 or int(geom.get("conaffinity", "1")) != 0
            role = "collision" if contact else "visual"
            target = ET.SubElement(link, role, name=f"{body_name}_{role}_{index}")
            _origin(target, geom)
            _urdf_geometry(target, geom, meshes)
            if role == "visual" and "rgba" in geom.attrib:
                material = ET.SubElement(target, "material", name=f"{body_name}_color_{index}")
                ET.SubElement(material, "color", rgba=geom.attrib["rgba"])

        if parent_body is None:
            continue
        source_joint = body.find("joint")
        if source_joint is None:
            raise ValueError(f"Pinned ZGWS body {original_body_name} has no joint")
        joint_position = _numbers(source_joint.get("pos"), (0.0, 0.0, 0.0))
        if any(value != 0.0 for value in joint_position):
            raise ValueError("This ZGWS-specific derivation requires the source joint origins at their body origins")
        name = prefix + source_joint.attrib["name"]
        joint_names.append(name)
        kind = source_joint.get("type", "hinge")
        target = ET.SubElement(urdf, "joint", name=name, type={"hinge": "revolute", "slide": "prismatic"}[kind])
        ET.SubElement(target, "parent", link=prefix + parent_body.attrib["name"])
        ET.SubElement(target, "child", link=body_name)
        _origin(target, body)
        axis = _numbers(source_joint.get("axis"), (0.0, 0.0, 1.0))
        limits = _numbers(source_joint.get("range"), ())
        forces = _numbers(source_joint.get("actuatorfrcrange"), ())
        ET.SubElement(target, "axis", xyz=_text(axis))
        ET.SubElement(
            target, "limit", lower=_text([limits[0]]), upper=_text([limits[1]]),
            effort=_text([max(abs(value) for value in forces)]),
            velocity=_text([URDF_VELOCITY_PLACEHOLDER_RAD_S]),
        )
        if "damping" in source_joint.attrib or "frictionloss" in source_joint.attrib:
            ET.SubElement(target, "dynamics", damping=source_joint.get("damping", "0"), friction=source_joint.get("frictionloss", "0"))
        wheel = original_body_name.endswith("_FOOT_LINK")
        joint_info.append({
            "name": name,
            "source_name": source_joint.attrib["name"],
            "parent_body": prefix + parent_body.attrib["name"],
            "body": body_name,
            "type": kind,
            "axis_in_joint_frame": axis,
            "range_rad": limits,
            "actuator_force_range_model_units": forces,
            "body_origin_position_m": _numbers(body.get("pos"), (0.0, 0.0, 0.0)),
            "body_origin_quaternion_wxyz": _numbers(body.get("quat"), (1.0, 0.0, 0.0, 0.0)),
            "wheel": wheel,
            "urdf_velocity_rad_s": URDF_VELOCITY_PLACEHOLDER_RAD_S,
            "velocity_is_description_placeholder": True,
        })
        if wheel:
            contact_meshes = []
            for geom in body.findall("geom"):
                contact = int(geom.get("contype", "1")) != 0 or int(geom.get("conaffinity", "1")) != 0
                if contact and geom.get("type") == "mesh":
                    asset = meshes[geom.attrib["mesh"]]
                    bounds = asset["bounds_m"]
                    contact_meshes.append({
                        "mesh": asset["name"],
                        "mesh_bounds_m": bounds,
                        "geom_position_m": _numbers(geom.get("pos"), (0.0, 0.0, 0.0)),
                        "geom_quaternion_wxyz": _numbers(geom.get("quat"), (1.0, 0.0, 0.0, 0.0)),
                        "mesh_scale": _numbers(asset["scale"], (1.0, 1.0, 1.0)),
                        "mesh_bbox_center_m": None if bounds is None else [0.5 * (lo + hi) for lo, hi in zip(bounds["min"], bounds["max"])],
                    })
            wheel_geometry.append({"joint": name, "body": body_name, "axis": axis, "contact_meshes": contact_meshes})

    # Rename native object names and references, never their numeric dynamics.
    reference_attributes = {
        "joint", "joint1", "joint2", "site", "site1", "site2", "body", "body1", "body2",
        "mesh", "geom", "geom1", "geom2", "material", "texture", "tendon", "target",
        "camera", "cranksite", "slidersite", "objname", "refname", "actuator", "sensor",
    }
    free_joint_name = None
    for element in native.iter():
        if element.tag == "freejoint" and "name" not in element.attrib:
            element.set("name", "floating_base")
        if "name" in element.attrib:
            element.set("name", prefix + element.attrib["name"])
        for attribute in reference_attributes:
            if attribute in element.attrib:
                element.set(attribute, prefix + element.attrib[attribute])
        if element.tag == "freejoint":
            free_joint_name = element.attrib["name"]
        if element.tag == "geom":
            contact = int(element.get("contype", "1")) != 0 or int(element.get("conaffinity", "1")) != 0
            if contact:
                element.set("group", "3")
            elif "group" not in element.attrib:
                element.set("group", "1")
    native.set("model", prefix + source.get("model", "zgws"))
    native_compiler = native.find("compiler")
    if native_compiler is not None:
        native_compiler.attrib.pop("meshdir", None)
    native_assets = {record["name"]: record for record in assets}
    for mesh in native.findall("asset/mesh"):
        mesh.set("file", native_assets[mesh.attrib["name"]]["project_relative_path"])

    standing_candidate = _commented_stance(source_text, joint_names)
    actuator_elements = list(native.find("actuator"))
    return {
        "urdf": urdf,
        "mjcf": native,
        "root_body_name": prefix + source_root_body.attrib["name"],
        "free_joint_name": free_joint_name,
        "joint_names": joint_names,
        "wheel_joint_names": [joint["name"] for joint in joint_info if joint["wheel"]],
        "actuator_names": [element.attrib["name"] for element in actuator_elements],
        "actuated_joint_names": [element.attrib["joint"] for element in actuator_elements],
        "assets": assets,
        "asset_file_paths_are_relative_to": "project_root",
        "urdf_mesh_paths_assume": "URDF file immediately under project_root/description/",
        "joint_info": joint_info,
        "wheel_geometry": wheel_geometry,
        "initial_pose": {
            "source_root_position_m": _numbers(source_root_body.get("pos"), (0.0, 0.0, 0.0)),
            "source_root_quaternion_wxyz": _numbers(source_root_body.get("quat"), (1.0, 0.0, 0.0, 0.0)),
            "zero_joint_positions_rad": {name: 0.0 for name in joint_names},
            "standing_candidate": standing_candidate,
        },
        "notes": [
            f"Derived from official ZGWS source: {SOURCE_URL}",
            "Native MJCF retains source masses, inertial quaternions, joint ranges, motors, sensors, contact geometry, and floating base.",
            "Contact geoms use display group 3; non-contact visual geoms retain their existing group. Collision masks are unchanged.",
            "URDF omits the root body's scene placement and freejoint; downstream scene placement remains separate.",
            "URDF expresses each source principal-axis inertia as the equivalent full tensor R diag(I) R^T in the link frame, with inertial RPY zero; masses, centers of mass, and physical inertias are preserved.",
            "The four URDF wheel joints retain the source finite +/-99999 rad ranges; this is not a claim of validated wheel control.",
            f"URDF velocity={URDF_VELOCITY_PLACEHOLDER_RAD_S} rad/s is a description/planning placeholder because the source specifies no physical velocity limits.",
            "actuatorfrcrange values are source model settings, not verified continuous hardware torque specifications.",
            "The upstream home keyframe is commented out. Its qpos is exposed only as an assembly/FK candidate; its ctrl is ignored.",
            "Use transformed wheel collision mesh vertices or the compiled model to set contact height; bbox centers alone are only geometric references.",
            "Binary STL headers beginning with 'solid' are normalized only when their byte layout confirms binary STL; triangle data is unchanged.",
        ],
    }
