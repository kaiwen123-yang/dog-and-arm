"""Feed recorded 2 ms Warp teacher outcomes through the frozen full-task judge without new dynamics."""
from argparse import ArgumentParser
import json
from pathlib import Path
from types import SimpleNamespace

import mujoco as mj
import numpy as np

from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from learning.b0.physics import build
from scripts.b0.recovery_teacher import FROZEN, OUT, RAW


def read(path):
    return json.loads(path.read_text())


def load(path, key):
    return np.load(path/"substeps"/(key+".npy"), mmap_mode="r")


def score(path, frozen, side):
    meta = read(path/"metadata.json")
    cfg = read(path/"config.json")
    model = build(cfg)
    ref = FrozenDoorReference.from_episode(frozen,model)
    judge = ContactEvents(model,cfg,side,ref,hold_seconds=.5,start_step=0)
    d = mj.MjData(model)
    q,v,phase,sub_goal,rot,effort,wheels,fingers,slip_long,slip_lat,force,norm = (
        load(path,n) for n in ("qpos","qvel","phase","tcp_goal_world_m","tool_goal_world_R","actuator_force",
                               "wheel_load_N","finger_load_N","wheel_slip_long_m_s","wheel_slip_lat_m_s",
                               "door_robot_force_N","door_force_norm_sum_N"))
    reference_goal=load(frozen,"tcp_goal_world_m")
    reference_phase=load(frozen,"phase")
    stops = [len(phase),len(reference_phase)]
    if meta["first_failure_physics_interval"] is not None:
        stops.append(meta["first_failure_physics_interval"]+1)
    n=min(stops)
    unexpected={ev["step"]:ev["categories"] for ev in read(path/"unexpected_contacts.json")}
    contact=SimpleNamespace()
    for k in range(n):
        # The solver's interval geometry precedes integration (no second forward).
        # Reconstruct only this FK; every contact force and effort comes from the recording.
        d.qpos[:]=q[k]
        mj.mj_kinematics(model,d)
        d.qpos[:]=q[k+1]
        d.qvel[:]=v[k+1]
        d.actuator_force[:]=effort[k]
        contact.normal=wheels[k]
        contact.supported=contact.normal >= cfg["wheel_threshold_n"]
        contact.finger_normal=fingers[k]
        contact.both=bool(np.all(contact.finger_normal > cfg["contact_threshold_n"]))
        contact.unexpected=unexpected.get(k,{})
        contact.door_force=force[k]
        contact.force_norm_sum=norm[k]
        contact.slip_long=slip_long[k]
        contact.slip_lat=slip_lat[k]
        judge.observe(d,contact,q[k],v[k])
        if judge.passed or judge.failure:
            break
    reason = judge.failure
    if not reason and not judge.passed:
        reason = dict(reason=("reference_exhausted" if judge.step==len(reference_phase) else "teacher_trace_ended"),
                      phase=judge.phase,step=judge.step)
    frozen_names=read(frozen/"metadata.json")["phases"]
    actual_names=np.asarray(meta["phases"])[phase[:n]]
    frozen_names=np.asarray(frozen_names)[reference_phase[:n]]
    match=actual_names==frozen_names
    phases={}
    for name in ("pregrasp","approach_arm","grasp","open","retreat_arm"):
        mask=match&(actual_names==name)
        actual=np.flatnonzero(actual_names==name)
        if not len(actual):
            continue
        last=actual[-1]
        mjpos=q[last]
        d.qpos[:]=mjpos
        mj.mj_kinematics(model,d)
        tcp=d.site_xpos[judge.tcp]
        handle=d.site_xpos[judge.handle]
        endpoint,orientation=ref.endpoint_pose[name]
        chosen=sub_goal[last]
        frozen_error=float(np.linalg.norm(tcp-endpoint)*1e3)
        own_error=float(np.linalg.norm(tcp-chosen)*1e3)
        point=dict(actual_last_physics_step=int(last),last_in_measured_phase=bool(last+1==len(phase) or phase[last+1]!=phase[last]),
                   tolerance_mm=cfg["tracking_tol_m"]*1e3,teacher_goal_to_frozen_endpoint_mm=float(np.linalg.norm(chosen-endpoint)*1e3),
                   actual_tcp_to_teacher_goal_mm=own_error,actual_tcp_to_frozen_endpoint_mm=frozen_error,
                   actual_tcp_to_handle_mm=float(np.linalg.norm(tcp-handle)*1e3),
                   actual_door_deg=float(np.rad2deg(mjpos[judge.hinge_q])),actual_force_N=float(np.linalg.norm(force[last])),
                   active_finger_N=fingers[last].tolist(),same_phase_substeps=int(mask.sum()))
        if mask.any():
            dist=1000*np.linalg.norm(sub_goal[:n][mask]-reference_goal[:n][mask],axis=1)
            point.update(same_clock_same_phase_goal_delta_mm_quantiles=np.quantile(dist,[.5,.95,1.]).tolist(),
                         same_clock_same_phase_goal_delta_above_3mm=int((dist>3).sum()))
        phases[name]=point
    return dict(teacher_episode=path.name,fixed_reference=frozen.name,teacher_pass=meta["success"],
                teacher_hard_failure=meta["failure"],source="raw solved contact/effort, CPU FK at interval start plus recorded post-step q/v; native solver warning vector unavailable",
                reference_length_substeps=len(reference_phase),teacher_recorded_substeps=len(phase),
                recorded_minus_frozen_steps=len(phase)-len(reference_phase),scored_substeps=judge.step,
                scored_margin_to_ref_end_s=round((len(reference_phase)-judge.step)*.002,6),
                frozen_judge_pass=judge.passed, frozen_judge_first_failure=reason, events=judge.events,
                last_not_ready=judge.last_not_ready, peak_ready_steps=judge.peak_ready_steps,
                tolerance_scope="3 mm absolute TCP endpoint is tested at pregrasp, approach_arm, retreat_arm; elsewhere comparisons are diagnostic",
                phase_geometry=phases, metrics_are_policy_evaluation=False)


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("--episode",required=True)
    args=p.parse_args()
    nominal=args.episode in ("pull_60_train","push_25_train")
    path=(FROZEN if nominal else RAW)/args.episode
    meta=read(path/"metadata.json")
    side=meta["task"]
    frozen=FROZEN/f"{side}_{meta['target_angle_deg']}_train"
    out=OUT/"judge"/(path.name+".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():
        raise FileExistsError(out)
    result=score(path,frozen,side)
    body=json.dumps(result,indent=2,allow_nan=False)+"\n"
    with out.open("x") as f:
        f.write(body)
    print(out,result["frozen_judge_pass"],result["frozen_judge_first_failure"],flush=True)


if __name__ == "__main__":
    main()
