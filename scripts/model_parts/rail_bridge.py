"""Nominal rail bridge. Coordinates in metres in m1_base_link unless indicated."""

import json
import numpy as np
from scipy.spatial import Delaunay
from scipy.spatial.transform import Rotation


def plate_mesh(path, size, holes):
    # Each circular ring bounds an empty disk. Its Delaunay interior faces
    # are the bore; retain the surrounding faces and add the bore walls.
    sx, sy, half_thickness = np.asarray(size) / 2
    points = [[-sx, -sy], [sx, -sy], [sx, sy], [-sx, sy]]
    loops = [list(range(4))]
    ring_of = [-1] * 4
    for index, (center, radius) in enumerate(holes):
        angles = np.arange(32) * 2 * np.pi / 32
        ring = center + radius * np.column_stack((np.cos(angles), np.sin(angles)))
        loops.append(list(range(len(points), len(points) + len(ring)))[::-1])
        points.extend(ring)
        ring_of.extend([index] * len(ring))
    points = np.asarray(points)
    n = len(points)
    faces = []
    for a, b, c in Delaunay(points).simplices:
        if ring_of[a] >= 0 and ring_of[a] == ring_of[b] == ring_of[c]:
            continue
        faces.extend([(a + n, b + n, c + n), (c, b, a)])
    for loop in loops:
        for a, b in zip(loop, loop[1:] + loop[:1]):
            faces.extend([(a, b, b + n), (a, b + n, a + n)])
    with path.open("w") as stream:
        for z in [-half_thickness, half_thickness]:
            for x, y in points:
                stream.write(f"v {x:.9f} {y:.9f} {z:.9f}\n")
        for a, b, c in faces:
            stream.write(f"f {a + 1} {b + 1} {c + 1}\n")


def geometry(root, mount):
    cfg = mount["bridge"]
    ref = json.loads((root / cfg["interface"]).read_text())
    origin = np.array(cfg["rail_pattern_origin_xy_m"])
    top = cfg["cover_top_z_m"] + cfg["cover_clearance_m"] + cfg["plate_size_xyz_m"][2]
    under = top - cfg["plate_size_xyz_m"][2]
    center = np.array(cfg["plate_center_xy_m"])
    rail_xy = origin + np.array(ref["m1_interface"]["selected_hole_centers_m"])[:, :2]
    piper = ref["piper_h_interface"]
    xy = (
        np.array(cfg["piper_pattern_center_in_root_xy_m"])
        + np.array(piper["hole_centers_in_pattern_center_frame_m"])[:, :2]
    )
    R = Rotation.from_euler("xyz", mount["rpy_rad"])
    piper_xyz = mount["xyz_m"] + R.apply(np.column_stack((xy, np.zeros(len(xy)))))
    holes = [(p - center, cfg["m4_plate_clearance_diameter_m"] / 2) for p in rail_xy]
    holes += [(p[:2] - center, cfg["m5_plate_minor_diameter_m"] / 2) for p in piper_xyz]
    mesh = "assets/converted/m1_rail_bridge_plate.obj"
    plate_mesh(root / mesh, cfg["plate_size_xyz_m"], holes)
    solids = [("plate", np.r_[center, (top + under) / 2], cfg["plate_size_xyz_m"])]
    for i, y in enumerate(np.unique(rail_xy[:, 1])):
        z = cfg["seat_top_z_m_by_y"][i]
        solids.append(
            (
                "rail_" + ("left" if y > 0 else "right"),
                np.array([origin[0], y, (z + under) / 2]),
                [*cfg["support_size_xy_m"], under - z],
            )
        )
    # Bolt detail is visual. The native Piper mesh supplies its flange and four
    # through-holes. Cylinder axes follow plate normal for this flat installation.
    bolts = []
    for kind, centers, seat, head_radius, head_height, shaft_radius in [
        ("m4", rail_xy, top, 0.0035, 0.0028, 0.002),
        (
            "m5",
            piper_xyz[:, :2],
            mount["xyz_m"][2] + cfg["piper_flange_thickness_m"],
            0.00425,
            0.0035,
            0.0025,
        ),
    ]:
        for i, point in enumerate(centers):
            bolt = f"{kind}_{i + 1}"
            bolts.append(
                (
                    bolt + "_head",
                    np.r_[point, seat + head_height / 2],
                    head_radius,
                    head_height,
                )
            )
            bottom = under + 0.002 if kind == "m5" else under - 0.001
            bolts.append(
                (
                    bolt + "_shaft",
                    np.r_[point, (seat + bottom) / 2],
                    shaft_radius,
                    seat - bottom,
                )
            )
    return mesh, solids, bolts
