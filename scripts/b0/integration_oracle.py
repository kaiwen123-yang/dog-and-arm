"""Measure error of the O1 position integrator with exact endpoint velocities, offline."""
from argparse import ArgumentParser
import json
from pathlib import Path

import mujoco
import numpy as np
import torch
from mjlab.utils.lab_api.math import quat_apply_inverse

from learning.b0.evaluate import ErrorMeasures
from learning.b0.model import RobotRepresentation, full_state
from learning.b0.physics import ActionMap, ROOT, make_model
from learning.b0.reference import load_episode


def summary(values):
    values = np.asarray(values, dtype=float)
    return dict(rms=float(np.sqrt(np.mean(values**2))), p95=float(np.percentile(values,95)),
                maximum=float(values.max()))


def teacher_data(path):
    data = load_episode(path)
    return dict(q=data["qpos"][:-1], v=data["qvel"][:-1], q1=data["qpos"][1:], v1=data["qvel"][1:],
                target=data["physical_target"], delta_action=data["action_clipped"]-data["last_action"][:-1])


def policy_data(run):
    pieces = []
    for path in sorted(run.glob("policy_transitions_*")):
        def read(name):
            a = np.load(path/(name+".npy"), allow_pickle=False)
            return a.reshape((-1,) + a.shape[2:])
        pieces.append(dict(q=read("qpos"), v=read("qvel"), q1=read("next_qpos"), v1=read("next_qvel"),
                           target=read("physical_target"), delta_action=read("clipped")-read("prev_action"),
                           terminal=read("terminated"), truncated=read("truncated")))
    if not pieces:
        raise ValueError(f"No actual policy transitions under {run}")
    data = {k:np.concatenate([p[k] for p in pieces]) for k in pieces[0]}
    return data, [path.name for path in sorted(run.glob("policy_transitions_*"))]


def bins(magnitude, edges, tcp, arm_error):
    result = []
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        mask = (magnitude >= lo) & (magnitude < hi)
        n = int(mask.sum())
        row = dict(lower=lo, upper=hi if np.isfinite(hi) else None, count=n)
        if n:
            row.update(tcp_mm=summary(tcp[mask]*1000), arm_angle_rmse_rad=float(np.sqrt((arm_error[mask]**2).mean())))
        result.append(row)
    return result


@torch.no_grad()
def audit(d, rep, mapping, score):
    q, v, q1, v1 = [torch.tensor(d[k], dtype=torch.float64) for k in ("q", "v", "q1", "v1")]
    # Only for the offline reference-frame conversion. The integrator never sees
    # q1's payload or absolute orientation. Its single start is the true q[k], v[k].
    s = full_state(q, v)
    s1 = full_state(q1, v1)
    q0_quat = s[:,3:7]
    # The O1 delta is expressed in the CURRENT body frame, including endpoint angular
    # velocity. MuJoCo saves the endpoint root linear velocity in world coordinates.
    dv = quat_apply_inverse(q0_quat, s1[:,31:34]-s[:,31:34])
    dw = quat_apply_inverse(q0_quat, s1[:,34:37]-s[:,34:37])
    delta = torch.cat((dv, dw, s1[:,37:]-s[:,37:]), dim=-1)
    aux, state = rep.apply_prediction(s[:,:7], rep.represent(s), delta / rep.velocity_units, rep.dt)
    result = rep.reconstruct_full_state(aux,state)
    pos = result[:,:31].numpy()
    actual = q1[:,:31].numpy()
    # FK only reads articulated robot + root. Use current passive door angle in both
    # pose buffers; an independent worldbody cannot change this site's FK.
    tcp = np.linalg.norm(score.tcp_world(np.c_[pos,d["q"][:,-1]]) -
                         score.tcp_world(np.c_[actual,d["q"][:,-1]]), axis=1)
    angle = []
    for a, b in zip(pos[:,3:7], actual[:,3:7]):
        residual = np.empty(3)
        mujoco.mju_subQuat(residual, a/np.linalg.norm(a), b/np.linalg.norm(b))
        angle.append(np.rad2deg(np.linalg.norm(residual)))
    qerr = pos-actual
    legs, arms = qerr[:,mapping.q[:12]], qerr[:,mapping.q[16:22]]
    fingers = qerr[:,score.fingers]
    wheel = qerr[:,mapping.q[12:16]]
    max_arm_target_delta = np.abs(d["target"][:,16:22]-d["q"][:,mapping.q[16:22]]).max(axis=1)
    arm_speed = np.abs(d["v"][:,mapping.dof[16:22]]).max(axis=1)
    max_action_change = np.abs(d["delta_action"]).max(axis=1)
    def rms(x):
        return float(np.sqrt((x**2).mean()))
    return dict(
        count=len(q), root_xyz_euclidean_mm=summary(np.linalg.norm(qerr[:,:3],axis=1)*1000),
        root_orientation_deg=summary(angle), tcp_euclidean_mm=summary(tcp*1000),
        leg_joint_abs_rad=summary(abs(legs)), arm_joint_abs_rad=summary(abs(arms)),
        wheel_phase_abs_rad=summary(abs(wheel)), finger1_abs_mm=summary(abs(fingers[:,0])*1000),
        finger2_abs_mm=summary(abs(fingers[:,1])*1000), opening_abs_mm=summary(abs(fingers[:,0]-fingers[:,1])*1000),
        constraint_residual_abs_mm=summary(abs(fingers.sum(axis=1))*1000),
        per_joint_rms={name:rms(qerr[:,idx]) for name,idx in zip(rep.fk.joint_names,range(7,31))},
        achieved_endpoint_velocity_max_errors=dict(
            root_world_linear_m_s=float((result[:,31:34]-s1[:,31:34]).abs().max()),
            root_world_angular_rad_s=float((result[:,34:37]-s1[:,34:37]).abs().max()),
            hinge_rad_s=float((result[:,37:-2]-s1[:,37:-2]).abs().max()),
            finger_m_s=float((result[:,-2:]-s1[:,-2:]).abs().max())),
        arm_target_minus_initial_joint_max_abs_rad=summary(max_arm_target_delta),
        initial_arm_speed_max_abs_rad_s=summary(arm_speed),
        action_change_max_abs_normalized=summary(max_action_change),
        tcp_by_arm_target_minus_actual_rad=bins(max_arm_target_delta,[0,.02,.2,1,np.inf],tcp,arms),
        tcp_by_initial_arm_speed_rad_s=bins(arm_speed,[0,.25,1,5,np.inf],tcp,arms),
        tcp_by_max_normalized_action_change=bins(max_action_change,[0,.05,.25,1,np.inf],tcp,arms))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--teacher-dir", type=Path, default=ROOT/"results/raw_large/b0/native_teacher_20261121_r1")
    parser.add_argument("--policy-dir", type=Path, default=ROOT/"results/raw_large/b0/free_s0_integration_r1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output to preserve existing evidence")
    model = make_model()
    rep = RobotRepresentation(model,"cpu").double()
    score = ErrorMeasures(model)
    mapping = ActionMap(model)
    result = dict(method="B0 RobotRepresentation.apply_prediction / O1 GenCoord. Per true start state k use measured k+1 velocities only as an offline oracle; no network forward, optimization or chained rollout.",
                  interpretation="Momentary error when exactly fitting endpoint velocity. A velocity-imperfect model may trade velocity error for smaller position error; these errors are not hard lower bounds on pose RMSE.",
                  pose="endpoint native root quaternion used only to express measured body angular velocity in world, never used as next-pose estimate. TCP from independent native FK at true/predicted pose.",
                  dt=rep.dt, c=rep.substep_coeff, integration_precision="float64 on CPU, source values keep captured precision",
                  source_versions=dict(native_teacher="MuJoCo 3.3.0", policy_physics="pinned mjlab / MuJoCo Warp 3.16.0",
                                       oracle_fk=mujoco.__version__, policy_dir=args.policy_dir.name, teacher_dir=args.teacher_dir.name),
                  units="per_joint_rms in rad for hinge, m for finger slides. Distributions cover absolute component errors for joints, norm for root/TCP, angle for quaternion.",
                  datasets={})
    for name in ("support","moving_arm","park","moving_arm_wm_validation"):
        result["datasets"][name] = audit(teacher_data(args.teacher_dir/name), rep, mapping, score)
    data, blocks = policy_data(args.policy_dir)
    result["policy_capture_blocks"] = blocks
    result["policy_truncations"] = int(np.count_nonzero(data["truncated"]))
    for name, mask in (("policy_failed_step", data["terminal"]), ("policy_other_step", ~data["terminal"])):
        if np.any(mask):
            result["datasets"][name] = audit({k:v[mask] for k,v in data.items()}, rep, mapping, score)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    for key, d in result["datasets"].items():
        print(key,d["count"],"TCP RMS (mm)",format(d["tcp_euclidean_mm"]["rms"],".6g"))


if __name__ == "__main__":
    main()
