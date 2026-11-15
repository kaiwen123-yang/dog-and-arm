#!/usr/bin/env python3
"""Inventory the exact upstream MJCF/URDF files without running a simulator."""
from __future__ import annotations

import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_MESH_PREFIX = "package://agx_arm_description/agx_arm_urdf/"
XACRO_INCLUDE_PREFIX = "$(find agx_arm_description)/agx_arm_urdf/"


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def attributes(parent: ET.Element, child_name: str) -> dict | None:
    child = parent.find(child_name)
    return dict(child.attrib) if child is not None else None


def resource_record(path: Path | None, original: str) -> dict:
    return {
        "source_reference": original,
        "resolved_path": relative(path) if path is not None else None,
        "exists": path.is_file() if path is not None else False,
    }


def inspect_mjcf(path: Path) -> dict:
    document = ET.parse(path).getroot()
    compiler = document.find("compiler")
    compiler_attributes = dict(compiler.attrib) if compiler is not None else {}
    mesh_directory = path.parent / compiler_attributes.get("meshdir", "")
    bodies = []
    joints = []

    def visit(body: ET.Element, parent_name: str | None) -> None:
        name = body.get("name")
        bodies.append({
            "name": name,
            "parent": parent_name,
            "attributes": dict(body.attrib),
            "inertial": attributes(body, "inertial"),
            "geoms": [dict(geometry.attrib) for geometry in body.findall("geom")],
        })
        for joint in body:
            if joint.tag not in {"joint", "freejoint"}:
                continue
            kind = "free" if joint.tag == "freejoint" else joint.get("type", "hinge")
            joints.append({"body": name, "type": kind, "attributes": dict(joint.attrib)})
        for child in body.findall("body"):
            visit(child, name)

    for body in document.findall("worldbody/body"):
        visit(body, None)

    meshes = []
    for mesh in document.findall("asset/mesh"):
        filename = mesh.get("file", "")
        resolved = mesh_directory / filename if filename else None
        meshes.append({"attributes": dict(mesh.attrib), **resource_record(resolved, filename)})
    actuator_parent = document.find("actuator")
    actuators = [] if actuator_parent is None else [
        {"type": actuator.tag, "attributes": dict(actuator.attrib)} for actuator in actuator_parent
    ]
    dimensions = {"free": (7, 6), "ball": (4, 3), "slide": (1, 1), "hinge": (1, 1)}
    nq = sum(dimensions[joint["type"]][0] for joint in joints)
    nv = sum(dimensions[joint["type"]][1] for joint in joints)
    wheels = [joint for joint in joints if joint["attributes"].get("name", "").endswith("_FOOT_JOINT")]

    return {
        "format": "MJCF source inventory; no compilation or physics performed",
        "model": document.get("model"),
        "compiler": compiler_attributes,
        "bodies": bodies,
        "joints": joints,
        "wheel_joints": wheels,
        "actuators": actuators,
        "meshes": meshes,
        "active_keyframes": [dict(key.attrib) for key in document.findall("keyframe/key")],
        "summary": {
            "body_count": len(bodies),
            "free_joint_count": sum(joint["type"] == "free" for joint in joints),
            "one_dof_joint_count": sum(joint["type"] in {"hinge", "slide"} for joint in joints),
            "wheel_joint_count": len(wheels),
            "actuator_count": len(actuators),
            "mesh_count": len(meshes),
            "source_mass_sum_kg": sum(float(body["inertial"]["mass"]) for body in bodies if body["inertial"]),
            "structurally_expected_dimensions": {"nq": nq, "nv": nv, "nu": len(actuators)},
            "dimensions_compiled_and_checked": False,
        },
        "notes": [
            "For the pinned ZGWS model, the structural dimensions are nq=23, nv=22, nu=16.",
            "Source actuatorfrcrange values are simulation settings, not verified hardware continuous torque ratings.",
            "The source does not specify physical joint velocity limits; do not invent official URDF velocity ratings.",
            "motor actuator controls are not desired joint positions.",
            "Only actual key elements are counted; XML comments do not define an active home posture.",
            "The root body placement belongs to the scene, not to the M1-to-arm mounting transform.",
        ],
    }


def resolve_piper_reference(reference: str, source_file: Path, repository: Path) -> Path | None:
    if reference.startswith(PACKAGE_MESH_PREFIX):
        return repository / reference.removeprefix(PACKAGE_MESH_PREFIX)
    if reference.startswith(XACRO_INCLUDE_PREFIX):
        return repository / reference.removeprefix(XACRO_INCLUDE_PREFIX)
    if reference.startswith("package://") or "$(" in reference or "${" in reference:
        return None
    return source_file.parent / reference


def inspect_urdf(path: Path, repository: Path) -> dict:
    document = ET.parse(path).getroot()
    links = []
    meshes = []
    for link in document.findall("link"):
        inertial = link.find("inertial")
        links.append({
            "name": link.get("name"),
            "inertial": None if inertial is None else {
                "origin": attributes(inertial, "origin"),
                "mass": attributes(inertial, "mass"),
                "inertia": attributes(inertial, "inertia"),
            },
        })
        for role in ("visual", "collision"):
            for geometry_owner in link.findall(role):
                mesh = geometry_owner.find("geometry/mesh")
                if mesh is None:
                    continue
                reference = mesh.get("filename", "")
                meshes.append({
                    "link": link.get("name"),
                    "role": role,
                    "origin": attributes(geometry_owner, "origin"),
                    "attributes": dict(mesh.attrib),
                    **resource_record(resolve_piper_reference(reference, path, repository), reference),
                })
    joints = [{
        "name": joint.get("name"),
        "type": joint.get("type"),
        "parent": attributes(joint, "parent"),
        "child": attributes(joint, "child"),
        "origin": attributes(joint, "origin"),
        "axis": attributes(joint, "axis"),
        "limit": attributes(joint, "limit"),
        "mimic": attributes(joint, "mimic"),
    } for joint in document.findall("joint")]
    includes = []
    for include in document.findall("{http://www.ros.org/wiki/xacro}include"):
        reference = include.get("filename", "")
        includes.append(resource_record(resolve_piper_reference(reference, path, repository), reference))
    return {
        "format": "URDF/Xacro XML inventory; xacro includes are recorded, not expanded",
        "robot": document.get("name"),
        "links": links,
        "joints": joints,
        "mimics": [{"driven_joint": joint["name"], **joint["mimic"]} for joint in joints if joint["mimic"]],
        "meshes": meshes,
        "includes": includes,
        "summary": {"local_link_count": len(links), "local_joint_count": len(joints), "mesh_reference_count": len(meshes)},
    }


def main() -> None:
    configuration = json.loads((ROOT / "config/sources.lock.json").read_text())
    repositories = {entry["key"]: ROOT / entry["destination"] for entry in configuration["repositories"]}
    piper = repositories["piper_h"]
    inputs = [
        ("m1", repositories["m1"] / "model/zgws/zgws.xml"),
        ("piper_h_base", piper / "piper_h/urdf/piper_h_description.urdf"),
        ("piper_h_with_gripper", piper / "piper_h/urdf/piper_h_with_gripper_description.xacro"),
        ("standalone_gripper", piper / "agx_gripper/urdf/agx_gripper_description.urdf"),
    ]
    report = {"source_files": {}, "missing_source_files": [], "missing_resources": []}
    for key, path in inputs:
        entry = {"path": relative(path), "exists": path.is_file()}
        report["source_files"][key] = entry
        if not path.is_file():
            report["missing_source_files"].append(relative(path))
            continue
        entry.update(inspect_mjcf(path) if key == "m1" else inspect_urdf(path, piper))
        for resource in entry.get("meshes", []) + entry.get("includes", []):
            if not resource["exists"]:
                report["missing_resources"].append({"source_file": key, **resource})

    report_path = ROOT / "reports/source_inventory.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {report_path.relative_to(ROOT)}")
    for key, entry in report["source_files"].items():
        print(f"{key}: {entry.get('summary', 'source not downloaded')}")
    if report["missing_source_files"] or report["missing_resources"]:
        print("Some sources or referenced meshes are missing; their exact paths are recorded in the report.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
