#!/usr/bin/env python3
"""Generate passive single/double hinged-door MJCF scenes.

Only the four generated XML files below are written:
  sim/components/door_single.xml
  sim/components/door_double.xml
  sim/scenes/door_single.xml
  sim/scenes/door_double.xml

The components contain static geoms and leaf bodies, without a floor, camera, actuator,
equality constraint, latch or closer. Include exactly the desired component
inside a robot scene's worldbody, with compiler angle="radian".

Default examples:
  .venv/bin/python scripts/build_doors.py
  .venv/bin/python scripts/build_doors.py --config config/door.yaml

Site names:
  single: door_single_front_handle, door_single_back_handle
  double: door_left_front_handle, door_left_back_handle,
          door_right_front_handle, door_right_back_handle

"Front" is the negative-X panel face in the closed pose. Each handle site's
local +Z points outward from that face. Left +Z and right -Z hinge axes make
positive joint angles swing both leaves toward negative world X.

All dimensions and inertias are nominal scene-design assumptions. Generating
a scene does not run or validate robot contact control or opening success.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import yaml


def vector(values) -> str:
    return " ".join(f"{float(value):.12g}" for value in values)


def add_geom(parent: ET.Element, name: str, kind: str, **attributes) -> ET.Element:
    values = {"name": name, "type": kind, "mass": "0"}
    for key, value in attributes.items():
        values[key] = vector(value) if isinstance(value, (tuple, list)) else str(value)
    return ET.SubElement(parent, "geom", values)


def add_frame(parent: ET.Element, prefix: str, half_opening: float, cfg: dict) -> None:
    frame = cfg["frame"]
    gap = cfg["clearance"]
    leaf = cfg["leaf"]
    post_width = float(frame["post_width"])
    depth = float(frame["depth"])
    top_inner = float(gap["bottom"]) + float(leaf["height"]) + float(gap["frame_top"])
    top_outer = top_inner + post_width
    opening_side = half_opening + float(gap["frame_side"])
    # The frame is behind the panel, so the passive leaves can swing toward
    # -X without starting inside a frame post or catching it at the hinge.
    frame_x = (
        float(cfg["door_plane_x"])
        + float(leaf["thickness"]) / 2
        + float(gap["frame_rear"])
        + depth / 2
    )
    # Static frame geoms belong directly to worldbody. An otherwise empty
    # fixed body containing only zero-mass geoms triggers MuJoCo 3.3.0's
    # automatic centre-of-mass calculation on a total mass of zero.
    body = parent
    for side, direction in (("left", -1), ("right", 1)):
        add_geom(
            body,
            f"{prefix}_{side}_post",
            "box",
            pos=(frame_x, direction * (opening_side + post_width / 2), top_outer / 2),
            size=(depth / 2, post_width / 2, top_outer / 2),
            rgba=frame["rgba"],
        )
    add_geom(
        body,
        f"{prefix}_top_beam",
        "box",
        pos=(frame_x, 0, top_inner + post_width / 2),
        size=(depth / 2, opening_side + post_width, post_width / 2),
        rgba=frame["rgba"],
    )


def add_leaf(
    parent: ET.Element,
    prefix: str,
    hinge_y: float,
    direction: int,
    free_edge_clearance: float,
    cfg: dict,
) -> None:
    leaf = cfg["leaf"]
    hinge = cfg["hinge"]
    handle = cfg["handle"]
    gap = cfg["clearance"]
    nominal_width = float(leaf["width"])
    height = float(leaf["height"])
    thickness = float(leaf["thickness"])
    mass = float(leaf["mass"])
    bottom = float(gap["bottom"])
    panel_start = float(gap["hinge_edge"])
    panel_end = nominal_width - free_edge_clearance
    panel_width = panel_end - panel_start
    if panel_width <= 0:
        raise ValueError("Door edge clearances must leave a positive panel width.")
    panel_y = direction * (panel_start + panel_end) / 2

    body = ET.SubElement(
        parent,
        "body",
        name=f"{prefix}_leaf",
        pos=vector((float(cfg["door_plane_x"]), hinge_y, bottom)),
    )
    ET.SubElement(
        body,
        "joint",
        name=f"{prefix}_hinge",
        type="hinge",
        pos="0 0 0",
        axis=vector((0, 0, direction)),
        limited="true",
        range=vector(hinge["range"]),
        stiffness=f"{float(hinge['stiffness']):.12g}",
        damping=f"{float(hinge['damping']):.12g}",
        frictionloss=f"{float(hinge['frictionloss']):.12g}",
    )
    # Positive nominal box inertia at the panel centre. All leaf geoms have
    # mass=0 so no default density silently adds a second payload estimate.
    ET.SubElement(
        body,
        "inertial",
        pos=vector((0, panel_y, height / 2)),
        mass=f"{mass:.12g}",
        diaginertia=vector(
            (
                mass * (panel_width**2 + height**2) / 12,
                mass * (thickness**2 + height**2) / 12,
                mass * (thickness**2 + panel_width**2) / 12,
            )
        ),
    )
    add_geom(
        body,
        f"{prefix}_panel",
        "box",
        pos=(0, panel_y, height / 2),
        size=(thickness / 2, panel_width / 2, height / 2),
        rgba=leaf["rgba"],
        friction=leaf["friction"],
        condim="3",
    )

    handle_y = direction * (panel_end - float(handle["offset_from_free_edge"]))
    handle_z = float(handle["height"]) - bottom
    half_length = float(handle["vertical_length"]) / 2
    radius = float(handle["radius"])
    for side, sign in (("front", -1), ("back", 1)):
        face_x = sign * thickness / 2
        grip_x = sign * (thickness / 2 + float(handle["stand_off"]))
        for endpoint, z in (("lower", handle_z - half_length), ("upper", handle_z + half_length)):
            add_geom(
                body,
                f"{prefix}_{side}_handle_{endpoint}_stand",
                "capsule",
                fromto=(face_x, handle_y, z, grip_x, handle_y, z),
                size=(radius,),
                rgba=handle["rgba"],
                friction=handle["friction"],
                condim="3",
            )
        add_geom(
            body,
            f"{prefix}_{side}_handle_grip",
            "capsule",
            fromto=(
                grip_x, handle_y, handle_z - half_length,
                grip_x, handle_y, handle_z + half_length,
            ),
            size=(radius,),
            rgba=handle["rgba"],
            friction=handle["friction"],
            condim="3",
        )
        half_root = math.sqrt(0.5)
        ET.SubElement(
            body,
            "site",
            name=f"{prefix}_{side}_handle",
            pos=vector((grip_x, handle_y, handle_z)),
            quat=vector((half_root, 0, sign * half_root, 0)),
            type="sphere",
            size="0.008",
            rgba="0.15 0.6 1 0.7" if side == "front" else "1 0.55 0.15 0.7",
        )


def component(cfg: dict, double: bool) -> ET.Element:
    root = ET.Element("mujocoinclude")
    root.append(ET.Comment(" Passive doors; parent scene must use compiler angle='radian'. "))
    root.append(ET.Comment(" Nominal geometry and inertia; no latch, closer, actuator or equality constraint. "))
    width = float(cfg["leaf"]["width"])
    if double:
        add_frame(root, "door_double", width, cfg)
        meeting_clearance = float(cfg["clearance"]["meeting_gap"]) / 2
        add_leaf(root, "door_left", -width, 1, meeting_clearance, cfg)
        add_leaf(root, "door_right", width, -1, meeting_clearance, cfg)
    else:
        add_frame(root, "door_single", width / 2, cfg)
        add_leaf(
            root, "door_single", -width / 2, 1,
            float(cfg["clearance"]["single_free_edge"]), cfg,
        )
    return root


def camera_xyaxes(position, target) -> tuple[float, ...]:
    # MuJoCo cameras look down local -Z; local +Y is the image's up axis.
    backward = [float(position[i]) - float(target[i]) for i in range(3)]
    length = math.sqrt(sum(value * value for value in backward))
    z = [value / length for value in backward]
    x = [-z[1], z[0], 0.0]
    length = math.sqrt(sum(value * value for value in x))
    x = [value / length for value in x]
    y = [
        z[1] * x[2] - z[2] * x[1],
        z[2] * x[0] - z[0] * x[2],
        z[0] * x[1] - z[1] * x[0],
    ]
    return tuple(x + y)


def scene(cfg: dict, double: bool) -> ET.Element:
    label = "door_double" if double else "door_single"
    root = ET.Element("mujoco", model=f"{label}_passive_preview")
    root.append(ET.Comment(" Preview scene only: no robot controller or automated door opening. "))
    ET.SubElement(root, "compiler", angle="radian")
    ET.SubElement(root, "option", timestep=f"{float(cfg['scene']['timestep']):.12g}", gravity="0 0 -9.81")
    centre = (
        float(cfg["door_plane_x"]), 0,
        float(cfg["clearance"]["bottom"]) + float(cfg["leaf"]["height"]) / 2,
    )
    ET.SubElement(root, "statistic", center=vector(centre), extent="2.2")
    world = ET.SubElement(root, "worldbody")
    floor_size = cfg["scene"]["floor_half_size"]
    add_geom(
        world, f"{label}_floor", "plane",
        pos=(0, 0, 0), size=(floor_size[0], floor_size[1], 0.1),
        rgba=(0.78, 0.80, 0.83, 1), friction=(0.9, 0.005, 0.0001),
    )
    ET.SubElement(
        world, "light", name=f"{label}_light", pos="-1 -2 4",
        dir="0.5 0.3 -1", diffuse="0.9 0.9 0.9", castshadow="true",
    )
    position = cfg["scene"]["overview_position"]
    ET.SubElement(
        world, "camera", name="overview", pos=vector(position),
        xyaxes=vector(camera_xyaxes(position, centre)),
        fovy=f"{float(cfg['scene']['overview_fovy']):.12g}",
    )
    ET.SubElement(world, "include", file=f"../components/{label}.xml")
    return root


def write_xml(path: Path, root: ET.Element) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=project / "config" / "door.yaml")
    parser.add_argument("--output-root", type=Path, default=project / "sim", help="Directory containing components/ and scenes/.")
    args = parser.parse_args()
    with args.config.open(encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    for label, double in (("door_single", False), ("door_double", True)):
        component_path = args.output_root / "components" / f"{label}.xml"
        scene_path = args.output_root / "scenes" / f"{label}.xml"
        write_xml(component_path, component(cfg, double))
        write_xml(scene_path, scene(cfg, double))
        print(component_path)
        print(scene_path)
    print("Generated passive door assets only; no control or task-success evaluation was run.")


if __name__ == "__main__":
    main()
