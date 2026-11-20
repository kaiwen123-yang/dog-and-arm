"""Observe solved P6 contacts without changing MjData or applying any forces."""
from dataclasses import dataclass

import mujoco as mj
import numpy as np


@dataclass
class ContactSample:
    normal: np.ndarray             # summed positive contact normals per wheel [N]
    slip_long: np.ndarray          # signed forward/left speed of fastest loaded point
    slip_lat: np.ndarray           # on each wheel against the stationary plane [m/s]
    supported: np.ndarray
    finger_normal: np.ndarray      # accumulated normal load on the selected bar [N]
    both: bool
    unexpected: dict               # category -> peak individual point force norm [N]
    door_force: np.ndarray         # door (leaf, handles, frame) on robot, world [N]
    door_torque: np.ndarray        # same contacts about m1_base_link origin, world [Nm]
    hand_force: np.ndarray         # door on gripper bodies only, world [N]
    force_norm_sum: float          # sum of point force norms for door-robot contacts [N]
    max_penetration: float         # door-robot penetration [m]
    rows: list


class ContactMeter:
    """One sample per solved physics step. Call with details=True for point rows.

    Point rows carry the world wrench on geom2 at the contact, regardless of pair
    order. Aggregates reverse that sign when the robot is geom1. After mj_step
    the solved contacts and Cartesian velocity fields describe the beginning of
    the integrated interval. Pass that interval's start time when storing rows.
    """

    row_fields = (
        'category', 'geom1', 'geom2', 'geom1_id', 'geom2_id', 'x_m', 'y_m', 'z_m',
        'penetration_m', 'normal_n', 'force_on_geom2_x_n', 'force_on_geom2_y_n',
        'force_on_geom2_z_n', 'torque_on_geom2_x_nm', 'torque_on_geom2_y_nm',
        'torque_on_geom2_z_nm', 'friction_tangent1', 'friction_tangent2',
    )

    def __init__(self, model, floor_name, handle_side='front', contact_threshold_n=0.01,
                 wheel_threshold_n=1.0):
        self.model = model
        self.contact_threshold_n = contact_threshold_n
        self.wheel_threshold_n = wheel_threshold_n
        self.floor = model.geom(floor_name).id
        self.root = model.body('m1_base_link').id
        self.rod = model.geom(f'door_single_{handle_side}_handle_grip').id
        self.fingers = {model.body(f'piper_gripper_link{i+1}').id: i for i in range(2)}
        self.gripper = model.body('piper_gripper_base').id
        self.wheel_labels = ('FAR', 'FBL', 'RAR', 'RBL')
        self.wheels = {model.body(f'm1_{name}_FOOT_LINK').id: i
                       for i, name in enumerate(self.wheel_labels)}
        self.wheel_joints = [model.joint(f'm1_{name}_FOOT_JOINT').id for name in self.wheel_labels]
        self.names = [model.geom(i).name or f'{model.body(model.geom_bodyid[i]).name}[geom{i}]'
                      for i in range(model.ngeom)]
        self.robot = model.body_rootid[model.geom_bodyid] == self.root
        self.is_door = [name.startswith('door_single_') for name in self.names]
        active = np.flatnonzero(model.geom_contype | model.geom_conaffinity)
        self.robot_collision = [i for i in active if self.robot[i]]
        self.door_collision = [i for i in active if self.is_door[i]]
        self.force_local = np.zeros(6)
        self.point_velocity = np.empty(6)

    def door_clearance(self, data):
        """Closest active robot/door collision surfaces at this observation."""
        best = 4.0  # above all relevant separations in this scene
        pair = None
        for robot in self.robot_collision:
            for door in self.door_collision:
                distance = mj.mj_geomDistance(self.model, data, robot, door, best, None)
                if distance < best:
                    best, pair = distance, [self.names[robot], self.names[door]]
        return best, pair

    def _door_pair(self, robot_geom, door_geom):
        body = self.model.geom_bodyid[robot_geom]
        if door_geom == self.rod and body in self.fingers:
            return f'finger{self.fingers[body] + 1}_handle', self.fingers[body]
        name = self.names[door_geom]
        if '_handle_' in name:
            if self.names[robot_geom].startswith('piper_gripper_base_'):
                return 'gripper_base_handle', None
            if body in self.fingers:
                return 'finger_non_grasp_handle', None
            return 'other_robot_handle', None
        return ('robot_panel' if name.endswith('_panel') else 'robot_frame'), None

    def measure(self, data, details=False):
        m = self.model
        normal = np.zeros(4)
        slip_long = np.full(4, np.nan)
        slip_lat = np.full(4, np.nan)
        fastest_sq = np.full(4, -1.)
        finger_normal = np.zeros(2)
        door_force, door_torque, hand_force = np.zeros((3, 3))
        unexpected = {}
        norm_sum = penetration = 0.
        rows = []
        for ci, contact in enumerate(data.contact):
            if contact.efc_address < 0:
                continue
            g1, g2 = map(int, contact.geom)
            mj.mj_contactForce(m, data, ci, self.force_local)
            fn = self.force_local[0]
            if fn <= 0:
                continue
            robot1, robot2 = self.robot[g1], self.robot[g2]
            rg, other = (g1, g2) if robot1 else (g2, g1)
            body = m.geom_bodyid[rg]
            is_robot_door = (robot1 or robot2) and self.is_door[other]
            world = None
            expected = False
            if self.floor == other and (robot1 or robot2):
                if body in self.wheels:
                    expected = True
                    wi = self.wheels[body]
                    category = f'wheel_ground_{self.wheel_labels[wi]}'
                    normal[wi] += fn
                    if fn > self.contact_threshold_n:
                        # cvel and Cartesian positions come from the same solver step.
                        mj.mj_objectVelocity(m, data, mj.mjtObj.mjOBJ_XBODY,
                                             body, self.point_velocity, 0)
                        omega = self.point_velocity[:3]
                        arm = contact.pos - data.xpos[body]
                        vx = self.point_velocity[3] + omega[1]*arm[2] - omega[2]*arm[1]
                        vy = self.point_velocity[4] + omega[2]*arm[0] - omega[0]*arm[2]
                        speed_sq = vx*vx + vy*vy
                        if speed_sq > fastest_sq[wi]:
                            fastest_sq[wi] = speed_sq
                            axle = data.xaxis[self.wheel_joints[wi], :2]
                            axis_norm = np.linalg.norm(axle)
                            if axis_norm > 1e-8:
                                left = data.xmat[self.root].reshape(3, 3)[:2, 1]
                                ax, ay = axle / (axis_norm if axle @ left >= 0 else -axis_norm)
                                slip_long[wi], slip_lat[wi] = vx*ay - vy*ax, vx*ax + vy*ay
                else:
                    category = 'nonwheel_ground'
            elif robot1 and robot2:
                category = 'robot_self'
            elif is_robot_door:
                category, finger = self._door_pair(rg, other)
                if finger is not None:
                    expected = True
                    finger_normal[finger] += fn
                # Contact frame rows are basis axes; the normal points geom1 -> geom2.
                world = self.force_local.reshape(2, 3) @ contact.frame.reshape(3, 3)
                force, torque = -world if robot1 else world
                door_force += force
                door_torque += torque + np.cross(contact.pos - data.xpos[self.root], force)
                if body == self.gripper or body in self.fingers:
                    hand_force += force
                norm_sum += np.linalg.norm(force)
                penetration = max(penetration, -contact.dist)
            elif robot1 or robot2:
                category = 'robot_other'
            else:
                expected = True
                category = 'environment'
            if not expected and fn > self.contact_threshold_n:
                unexpected[category] = max(unexpected.get(category, 0.),
                                           float(np.linalg.norm(self.force_local[:3])))
            if details:
                if world is None:
                    world = self.force_local.reshape(2, 3) @ contact.frame.reshape(3, 3)
                rows.append(dict(zip(self.row_fields, (
                    category, self.names[g1], self.names[g2], g1, g2, *contact.pos,
                    max(0., -contact.dist), fn, *world.ravel(), *contact.friction[:2],
                ))))
        return ContactSample(normal, slip_long, slip_lat, normal >= self.wheel_threshold_n,
                             finger_normal, bool(np.all(finger_normal > self.contact_threshold_n)),
                             unexpected, door_force, door_torque, hand_force,
                             float(norm_sum), float(penetration), rows)
