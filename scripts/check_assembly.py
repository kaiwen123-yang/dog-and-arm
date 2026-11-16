#!/usr/bin/env python3
"""Check this project's URDF/MJCF assembly at three finite kinematic poses.

This is a conversion check, not a dynamics/controller test.  It uses independent
SciPy rotations and URDF tree traversal, calls only mj_forward, and records the
home keyframe, actual qpos, mimic values, compared frames and omissions.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation


ROOT = Path(__file__).resolve().parents[1]
POSITION_TOLERANCE_M = 1e-7
ROTATION_MATRIX_TOLERANCE = 1e-7
JOINT_TOLERANCE = 1e-10
SITE_FRAMES = {
    "m1_arm_mount", "piper_camera_bracket", "piper_camera_shell",
    "piper_wrist_optical_frame",
}
VIRTUAL_WIDTH_LINK = "piper_gripper_link"
WIDTH_JOINT = "piper_gripper"
FINGERS = ("piper_gripper_joint1", "piper_gripper_joint2")
# Six explicit, small changes sample arm, leg and wheel axes.  No random sweep.
PERTURBATIONS = {
    "piper_joint1": 1, "piper_joint2": -1, "piper_joint5": 1,
    "m1_FAR_ABAD_JOINT": 1, "m1_RBL_HIP_JOINT": -1, "m1_FBL_FOOT_JOINT": 1,
}


def numbers(text: str, count: int) -> np.ndarray:
    values = np.array([float(value) for value in text.split()], dtype=float)
    if len(values) != count or not np.isfinite(values).all():
        raise ValueError(f"Expected {count} finite values: {text!r}")
    return values


def origin_transform(joint: ET.Element) -> np.ndarray:
    transform = np.eye(4)
    origin = joint.find("origin")
    if origin is not None:
        # SciPy lowercase xyz means extrinsic/fixed-axis rotations, as in URDF.
        transform[:3, :3] = Rotation.from_euler(
            "xyz", numbers(origin.get("rpy", "0 0 0"), 3)).as_matrix()
        transform[:3, 3] = numbers(origin.get("xyz", "0 0 0"), 3)
    return transform


def read_urdf(path: Path):
    robot = ET.parse(path).getroot()
    link_elements, joint_elements = robot.findall("link"), robot.findall("joint")
    links = {link.attrib["name"] for link in link_elements}
    joints = {joint.attrib["name"]: joint for joint in joint_elements}
    if len(links) != len(link_elements) or len(joints) != len(joint_elements):
        raise ValueError("Duplicate link/joint names in combined URDF")
    children = [joint.find("child").attrib["link"] for joint in joint_elements]
    roots = links - set(children)
    if len(roots) != 1 or len(children) != len(set(children)):
        raise ValueError("Combined URDF must have one root and one parent per link")
    for joint in joints.values():
        if any(joint.find(tag).attrib["link"] not in links for tag in ("parent", "child")):
            raise ValueError(f"Dangling link reference: {joint.attrib['name']}")
    return links, joints, roots.pop()


def scalar_joints(model) -> dict[str, int]:
    result = {}
    for index in range(model.njnt):
        if model.jnt_type[index] in (mujoco.mjtJoint.mjJNT_HINGE, mujoco.mjtJoint.mjJNT_SLIDE):
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
            if name is None:
                raise ValueError("The combined model has an unnamed scalar joint")
            if abs(model.qpos0[model.jnt_qposadr[index]]) > JOINT_TOLERANCE:
                raise ValueError(f"This project check assumes scalar joint ref=0: {name}")
            result[name] = index
    return result


def bounds(model, index: int, joint: ET.Element) -> tuple[float, float]:
    lower, upper = -math.inf, math.inf
    if model.jnt_limited[index]:
        lower, upper = map(float, model.jnt_range[index])
    limit = joint.find("limit")
    if joint.get("type") != "continuous" and limit is not None:
        if "lower" in limit.attrib:
            lower = max(lower, float(limit.attrib["lower"]))
        if "upper" in limit.attrib:
            upper = min(upper, float(limit.attrib["upper"]))
    if lower > upper:
        raise ValueError(f"URDF/MJCF limits do not intersect: {joint.attrib['name']}")
    return lower, upper


def urdf_coordinates(joints: dict, measured: dict) -> tuple[dict, list[dict]]:
    """Resolve source mimic algebra, instead of copying the physical slave q."""
    resolved, visiting = {}, set()

    def resolve(name):
        if name in resolved:
            return resolved[name]
        if name in visiting or name not in joints:
            raise ValueError(f"Invalid/cyclic URDF mimic reference: {name}")
        visiting.add(name)
        joint = joints[name]
        mimic = joint.find("mimic")
        if joint.get("type") == "fixed":
            value = 0.0
        elif mimic is not None:
            value = (float(mimic.get("multiplier", "1")) * resolve(mimic.attrib["joint"])
                     + float(mimic.get("offset", "0")))
        elif name == WIDTH_JOINT:
            value = 2.0 * measured[FINGERS[0]]
        elif name in measured:
            value = measured[name]
        else:
            raise ValueError(f"No measured scalar coordinate for URDF joint {name}")
        if not math.isfinite(value):
            raise ValueError(f"Nonfinite URDF coordinate: {name}")
        visiting.remove(name)
        resolved[name] = float(value)
        return value

    for name in joints:
        resolve(name)
    checks = [{"joint": name, "urdf_mimic_q": resolved[name], "mjcf_q": measured[name],
               "absolute_error": abs(resolved[name] - measured[name])}
              for name, joint in joints.items()
              if joint.find("mimic") is not None and name in measured]
    return resolved, checks


def forward_urdf(joints: dict, coordinates: dict, root_name: str,
                 root_transform: np.ndarray) -> dict[str, np.ndarray]:
    frames = {root_name: root_transform.copy()}
    pending = list(joints.values())
    while pending:
        completed = []
        for joint in pending:
            parent = joint.find("parent").attrib["link"]
            if parent not in frames:
                continue
            transform = origin_transform(joint)
            kind = joint.attrib["type"]
            if kind != "fixed":
                axis_element = joint.find("axis")
                axis = numbers(axis_element.get("xyz", "1 0 0")
                               if axis_element is not None else "1 0 0", 3)
                norm = np.linalg.norm(axis)
                if norm <= 0:
                    raise ValueError(f"Invalid URDF joint axis: {joint.attrib['name']}")
                axis /= norm
                motion = np.eye(4)
                value = coordinates[joint.attrib["name"]]
                if kind in ("revolute", "continuous"):
                    motion[:3, :3] = Rotation.from_rotvec(axis * value).as_matrix()
                elif kind == "prismatic":
                    motion[:3, 3] = axis * value
                else:
                    raise ValueError(f"Unexpected internal URDF joint type: {kind}")
                transform = transform @ motion
            frames[joint.find("child").attrib["link"]] = frames[parent] @ transform
            completed.append(joint)
        if not completed:
            raise ValueError("Disconnected/cyclic URDF tree")
        for joint in completed:
            pending.remove(joint)
    return frames


def frame_targets(model, links: set[str]) -> tuple[list[dict], list[dict]]:
    targets, skipped = [], []
    for name in sorted(links):
        kinds = (("site", mujoco.mjtObj.mjOBJ_SITE),) if name in SITE_FRAMES else (
            ("body", mujoco.mjtObj.mjOBJ_BODY), ("site", mujoco.mjtObj.mjOBJ_SITE))
        found = False
        for kind, enum in kinds:
            index = mujoco.mj_name2id(model, enum, name)
            if index >= 0:
                targets.append({"urdf_link": name, "mujoco_kind": kind,
                                "mujoco_name": name, "mujoco_id": index})
                found = True
        if not found:
            virtual = name == VIRTUAL_WIDTH_LINK
            skipped.append({"urdf_link": name, "expected": virtual,
                            "reason": "virtual width-master link removed from physical MJCF" if virtual else
                            "required same-name site missing" if name in SITE_FRAMES else
                            "no same-name MuJoCo body or site"})
    for missing in sorted(SITE_FRAMES - links):
        skipped.append({"urdf_link": missing, "expected": False,
                        "reason": "required accessory frame missing from URDF"})
    return targets, skipped


def gripper_equalities(model, data, joint_ids: dict) -> list[dict]:
    ids = {joint_ids[name] for name in FINGERS}
    result = []
    for index in range(model.neq):
        if (model.eq_type[index] != mujoco.mjtEq.mjEQ_JOINT
                or {int(model.eq_obj1id[index]), int(model.eq_obj2id[index])} != ids):
            continue
        first, second = int(model.eq_obj1id[index]), int(model.eq_obj2id[index])
        q1, q2 = (float(data.qpos[model.jnt_qposadr[j]]) for j in (first, second))
        coefficients = np.asarray(model.eq_data[index, :5])
        result.append({"name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_EQUALITY, index),
                       "active": bool(data.eq_active[index]), "polycoef": coefficients.tolist(),
                       "residual_m": q1 - float(sum(c * q2**power for power, c in enumerate(coefficients)))})
    return result


def run(args, report: dict) -> None:
    if mujoco.__version__ != "3.3.0":
        raise RuntimeError(f"Use the project's MuJoCo 3.3.0 environment; found {mujoco.__version__}")
    links, joints, root_name = read_urdf(args.urdf)
    model = mujoco.MjModel.from_xml_path(str(args.model))
    data = mujoco.MjData(model)
    joint_ids = scalar_joints(model)
    for name in (*PERTURBATIONS, *FINGERS):
        if name not in joint_ids or name not in joints:
            raise ValueError(f"Required assembly joint missing: {name}")
    if WIDTH_JOINT not in joints:
        raise ValueError("Official virtual gripper width master missing from URDF")
    home_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "home")
    root_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, root_name)
    if home_id < 0 or root_id < 0:
        raise ValueError("The model needs a home keyframe and a body matching the URDF root")
    mujoco.mj_resetDataKeyframe(model, data, home_id)
    mujoco.mj_forward(model, data)
    targets, skipped = frame_targets(model, links)
    report.update(model_dimensions={name: int(getattr(model, name)) for name in ("nq", "nv", "nu", "neq")},
                  home={"keyframe": "home", "qpos": data.qpos.tolist(),
                        "scalar_coordinates": {name: float(data.qpos[model.jnt_qposadr[index]])
                                               for name, index in joint_ids.items()}},
                  root_link=root_name, frame_targets=targets, skipped_frames=skipped, cases=[])
    all_passed = bool(targets) and not any(not item["expected"] for item in skipped)
    for label, degrees, width in (("home_closed", 0.0, 0.0),
                                  ("small_plus_3deg_width_0p04", 3.0, 0.04),
                                  ("small_minus_5deg_width_0p08", -5.0, 0.08)):
        mujoco.mj_resetDataKeyframe(model, data, home_id)
        modifications = []
        for name, sign in PERTURBATIONS.items():
            index = joint_ids[name]
            address = model.jnt_qposadr[index]
            initial = float(data.qpos[address])
            requested = initial + math.radians(degrees * sign)
            lower, upper = bounds(model, index, joints[name])
            actual = min(upper, max(lower, requested))
            data.qpos[address] = actual
            modifications.append({"joint": name, "home_q_rad": initial,
                                  "requested_delta_rad": requested-initial,
                                  "applied_delta_rad": actual-initial,
                                  "clipped_to_joint_limits": actual != requested})
        for name, value in zip(FINGERS, (width / 2.0, -width / 2.0)):
            data.qpos[model.jnt_qposadr[joint_ids[name]]] = value
        data.qvel[:] = 0
        if not np.isfinite(data.qpos).all():
            raise ValueError(f"Nonfinite qpos in {label}")
        mujoco.mj_forward(model, data)
        measured = {name: float(data.qpos[model.jnt_qposadr[index]]) for name, index in joint_ids.items()}
        coordinates, mimic_checks = urdf_coordinates(joints, measured)
        for name, index in joint_ids.items():
            if name in joints:
                lo, hi = bounds(model, index, joints[name])
                if not lo-JOINT_TOLERANCE <= measured[name] <= hi+JOINT_TOLERANCE:
                    raise ValueError(f"Pose {label} is outside joint limits: {name}")
        root_transform = np.eye(4)
        root_transform[:3, 3] = data.xpos[root_id]
        root_transform[:3, :3] = data.xmat[root_id].reshape(3, 3)
        frames = forward_urdf(joints, coordinates, root_name, root_transform)
        comparisons = []
        for target in targets:
            index, kind = target["mujoco_id"], target["mujoco_kind"]
            position = data.xpos[index] if kind == "body" else data.site_xpos[index]
            rotation = (data.xmat[index] if kind == "body" else data.site_xmat[index]).reshape(3, 3)
            expected = frames[target["urdf_link"]]
            comparisons.append({"urdf_link": target["urdf_link"], "mujoco_kind": kind,
                "position_error_m": float(np.linalg.norm(position-expected[:3, 3])),
                "rotation_matrix_max_abs_error": float(np.max(np.abs(rotation-expected[:3, :3]))),
                "rotation_error_rad": float(Rotation.from_matrix(rotation @ expected[:3, :3].T).magnitude()),
                "urdf_position_m": expected[:3, 3].tolist(), "mujoco_position_m": position.tolist()})
        max_position = max(item["position_error_m"] for item in comparisons)
        max_rotation = max(item["rotation_matrix_max_abs_error"] for item in comparisons)
        equalities = gripper_equalities(model, data, joint_ids)
        mimic_pass = len(mimic_checks) == 2 and all(item["absolute_error"] <= JOINT_TOLERANCE for item in mimic_checks)
        equality_pass = len(equalities) == 1 and equalities[0]["active"] and abs(equalities[0]["residual_m"]) <= JOINT_TOLERANCE
        passed = max_position <= POSITION_TOLERANCE_M and max_rotation <= ROTATION_MATRIX_TOLERANCE and mimic_pass and equality_pass
        all_passed = all_passed and passed
        report["cases"].append({"name": label, "passed": passed,
            "description": "Base and arm reset from home; gripper explicitly set to the stated width.",
            "gripper_width_m": width, "modifications": modifications, "qpos": data.qpos.tolist(),
            "scalar_coordinates": measured, "urdf_coordinates": coordinates,
            "root_world_transform": root_transform.tolist(), "mimic_checks": mimic_checks,
            "gripper_equalities": equalities, "frame_comparisons": comparisons,
            "max_position_error_m": max_position, "max_rotation_matrix_error": max_rotation})
    report.update(status="passed" if all_passed else "failed",
                  max_position_error_m=max(case["max_position_error_m"] for case in report["cases"]),
                  max_rotation_matrix_error=max(case["max_rotation_matrix_error"] for case in report["cases"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--urdf", type=Path, default=ROOT / "description/m1_piper.urdf")
    parser.add_argument("--model", type=Path, default=ROOT / "sim/scenes/assembly_preview.xml")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/assembly_kinematics.json")
    args = parser.parse_args()
    for name in ("urdf", "model", "report"):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    report = {"created_utc": datetime.now(timezone.utc).isoformat(),
              "check": "URDF_MJCF_KINEMATICS_ONLY", "mujoco_version": mujoco.__version__,
              "urdf": args.urdf.relative_to(ROOT).as_posix() if args.urdf.is_relative_to(ROOT) else str(args.urdf),
              "model": args.model.relative_to(ROOT).as_posix() if args.model.is_relative_to(ROOT) else str(args.model),
              "status": "failed",
              "position_tolerance_m": POSITION_TOLERANCE_M,
              "rotation_matrix_tolerance": ROTATION_MATRIX_TOLERANCE,
              "notes": ["Independent URDF FK uses SciPy; generator helpers are not imported.",
                        "The URDF root is anchored to the actual MuJoCo root-body world transform.",
                        "The first case preserves home arm/base coordinates but closes the gripper.",
                        "Mimic slaves are evaluated from the URDF master, then compared with MJCF coordinates.",
                        "Only mj_forward is called: no dynamics, contact-task, controller or hardware validation."]}
    try:
        run(args, report)
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(report["error"], file=sys.stderr)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{report['status']}: {args.report}")
    if "max_position_error_m" in report:
        print(f"max position error {report['max_position_error_m']:.3e} m; "
              f"max rotation-matrix error {report['max_rotation_matrix_error']:.3e}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
