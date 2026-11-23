"""Test frozen reference endpoints followed by a finite grasp move to the current handle."""
import argparse
import json
from functools import partial
from pathlib import Path

import mujoco as mj
import numpy as np
from scipy.spatial.transform import Rotation

from scripts.b0.collect_contact import collect
from scripts.b0.recovery_teacher import FROZEN, REGISTER, index_teacher_clock
from scripts.b0.score_recovery_teacher_clock import score
from learning.b0.contact_events import FrozenDoorReference
from learning.b0.physics import build
from p4_fixed_door import smooth
from p6_arm import Arm

CASES = ("aug_pull_06_train_door","aug_push_06_train_door")
RUN = "recovery_endpoint_teacher_r1"


def blend_pose(start, end, alpha):
    a,b = start
    c,d = end
    delta = Rotation.from_matrix(d @ b.T).as_rotvec()
    return (1-alpha)*a + alpha*c, Rotation.from_rotvec(alpha*delta).as_matrix() @ b


class EndpointTeacher(Arm):
    """Move to the two declared nominal poses; retain measured-handle feedback during grasp."""
    def __init__(self, model, data, cfg, *, match_release=False):
        super().__init__(model,data,cfg)
        side = "pull" if cfg["stage"]=="mobile" else "push"
        frozen = FROZEN/f'{side}_{cfg["target_angle_deg"]}_train'
        ref=FrozenDoorReference.from_episode(frozen,model)
        self.endpoints=ref.endpoint_pose
        if match_release:
            cfg["teacher_release_earliest_step"]=ref.phase_bounds["release"][0]
        self.grasp_move_fraction=0.55

    def update(self, data, phase, fraction, raw_angle_deg=None, effective_angle_deg=None):
        self.active_fraction=fraction
        target,width=super().update(data,phase,fraction,raw_angle_deg,effective_angle_deg)
        if phase == "grasp":
            # Reserve the initial 55% of the 2 s grasp ramp for the shortest
            # Cartesian move from the frozen approach pose. Maintain open jaws.
            close=float(smooth(np.clip((fraction-self.grasp_move_fraction)/(1-self.grasp_move_fraction),0,1)))
            self.width=self.start_width+close*(self.cfg["closed_command_width_m"]-self.start_width)
            width=self.width/2
        return target,width

    def _tool_pose(self, data, angle_deg, clearance=0., retreat_fraction=0.):
        if self.phase=="pregrasp":
            return self.endpoints["pregrasp"]
        if self.phase=="approach_arm":
            return blend_pose(self.endpoints["pregrasp"],self.endpoints["approach_arm"],float(smooth(self.active_fraction)))
        current=super()._tool_pose(data,angle_deg,clearance,retreat_fraction)
        if self.phase=="grasp":
            alpha=float(smooth(np.clip(self.active_fraction/self.grasp_move_fraction,0,1)))
            return blend_pose(self.endpoints["approach_arm"],current,alpha)
        return current


def endpoint_clearance(frozen,perturbation):
    """Static counterfactual at the measured nominal endpoint; keep the given door pose."""
    cfg=json.loads((frozen/"config.json").read_text())
    cfg["perturbation"]=perturbation
    m=build(cfg)
    ref=FrozenDoorReference.from_episode(frozen,m)
    q=np.load(frozen/"substeps/qpos.npy",mmap_mode="r")
    jaw=m.geom("piper_gripper_base_collision_0").id
    hinges=m.joint("door_single_hinge").qposadr[0]
    handle=[i for i in range(m.ngeom) if "_handle_" in (m.geom(i).name or "") and (m.geom_contype[i] or m.geom_conaffinity[i])]
    rows=[]
    for phase in ("pregrasp","approach_arm"):
        stop=ref.phase_bounds[phase][1]-1
        d=mj.MjData(m)
        d.qpos[:]=q[stop]
        d.qpos[hinges]=np.deg2rad(perturbation["door"])
        mj.mj_forward(m,d)
        distances=[(float(mj.mj_geomDistance(m,d,jaw,i,1.,None)),m.geom(i).name) for i in handle]
        dist,partner=min(distances)
        err=np.linalg.norm(d.site("p4_grasp").xpos-ref.endpoint_pose[phase][0])
        rows.append(dict(phase=phase,nominal_state_physics_step=stop,door_deg=perturbation["door"],
                         tcp_to_frozen_endpoint_mm=float(err*1000),
                         closest_gripper_base_handle_pair=partner,signed_static_distance_mm=dist*1000.))
    return dict(scope="CPU3.16 FK and signed geom distance at recorded nominal endpoints with perturbed door; no dynamics, no force prediction, no search over other feasible poses",rows=rows)


def pose_shell(frozen, perturbation):
    """Sample legal TCP tolerance-boundary poses of the rigid gripper collision geometry."""
    cfg=json.loads((frozen/"config.json").read_text())
    cfg["perturbation"]=perturbation
    m=build(cfg)
    d=mj.MjData(m)
    ref=FrozenDoorReference.from_episode(frozen,m)
    k=ref.phase_bounds["approach_arm"][1]-1
    d.qpos[:]=np.load(frozen/"substeps/qpos.npy",mmap_mode="r")[k]
    d.qpos[m.joint("door_single_hinge").qposadr[0]]=np.deg2rad(perturbation["door"])
    mj.mj_forward(m,d)
    jaw=m.geom("piper_gripper_base_collision_0").id
    rod=m.geom(cfg["handle_site"]+"_grip").id
    tcp=d.site("p4_grasp")
    local_centroid=tcp.xmat.reshape(3,3).T @ (d.geom_xpos[jaw]-tcp.xpos)
    local_orientation=tcp.xmat.reshape(3,3).T @ d.geom_xmat[jaw].reshape(3,3)
    radius=float(np.linalg.norm(local_centroid)+m.geom_rbound[jaw])
    position,orientation=ref.endpoint_pose["approach_arm"]
    rng=np.random.default_rng(231126)
    offsets=rng.normal(size=(512,3))
    offsets=.003*offsets/np.linalg.norm(offsets,axis=1,keepdims=True)
    axes=rng.normal(size=(512,3))
    axes=.02*axes/np.linalg.norm(axes,axis=1,keepdims=True)
    distances=[]
    for offset,axis in zip(offsets,axes):
        r=Rotation.from_rotvec(axis).as_matrix() @ orientation
        d.geom_xpos[jaw]=position+offset+r@local_centroid
        d.geom_xmat[jaw]=(r@local_orientation).ravel()
        distances.append(float(mj.mj_geomDistance(m,d,jaw,rod,1.,None))*1000)
    return dict(geometry="only rigid gripper-base mesh and designated fixed-angle rod",
                angle_deg=perturbation["door"],translation_radius_m=.003,rotation_radius_rad=.02,
                seed=231126,samples=len(distances),samples_with_negative_distance=sum(v<0 for v in distances),
                signed_distance_range_mm=[min(distances),max(distances)],gripper_tcp_bounding_radius_m=radius,
                maximum_rigid_point_displacement_mm=(.003+2*np.sin(.02/2)*radius)*1000,
                scope="uniform random translation and rotation axes on tolerance boundaries; no IK or physical force, did not examine changing door angle")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True,choices=CASES)
    p.add_argument("--geometry-only",action="store_true",help="measure distances at nominal joint endpoint with the registered door angle")
    p.add_argument("--index",action="store_true",help="index fixed-clock action supervision separately from the original A0-A3 set")
    p.add_argument("--video",action="store_true",help="render the recorded physical episode at 25 fps")
    p.add_argument("--pose-shell",action="store_true",help="probe signed gripper-base distance near the frozen approach endpoint")
    p.add_argument("--match-release",action="store_true",help="also hold until the frozen reference release begins")
    a=p.parse_args()
    if a.match_release and a.source!=CASES[1]:
        p.error("only the push matched-endpoint trial reached and then lost the timed hold")
    tr=next(x for x in json.loads(REGISTER.read_text())["cases"] if x["episode_id"]==a.source)
    trial=dict(tr,episode_id="endpoint_"+a.source)
    run="recovery_endpoint_release_teacher_r2" if a.match_release else RUN
    raw=Path("results/raw_large/b0")/run
    out=Path("results/b0")/run
    out.mkdir(parents=True,exist_ok=True)
    case=trial["episode_id"]
    frozen=FROZEN/f'{trial["side"]}_{trial["goal"]}_train'
    if a.index:
        index_teacher_clock(trial,raw,out)
        return
    if a.video:
        from scripts.b0.eval_contact_segments import save_video
        dest=out/(case+".mp4")
        if dest.exists():
            raise FileExistsError(dest)
        source=raw/case
        model=build(json.loads((source/"config.json").read_text()))
        q=np.load(source/"substeps/qpos.npy",mmap_mode="r")
        n=len(q)
        save_video(model,q,range(n),dest)
        return
    if a.pose_shell:
        with (out/(case+"_pose_shell.json")).open("x") as f:
            f.write(json.dumps(pose_shell(frozen,trial["perturbation"]),indent=2,allow_nan=False)+"\n")
        return
    if a.geometry_only:
        with (out/(case+"_static_geometry.json")).open("x") as f:
            f.write(json.dumps(endpoint_clearance(frozen,trial["perturbation"]),indent=2,allow_nan=False)+"\n")
        return
    with (out/(case+"_design.json")).open("x") as f:
        json.dump(dict(source=a.source,perturbation=trial["perturbation"],group="endpoint feasibility diagnostic, excluded from A0-A3",
                       additional_to_endpoint_r1="earliest release at fixed reference release start" if a.match_release else None,
                       change="nominal pregrasp and approach_arm endpoint poses; then smooth 1.1s move toward current handle with jaws open and .9s closure in original 2s grasp ramp; remaining teacher and all physical thresholds unchanged",
                       reference=str(FROZEN),clock="same 2ms/20ms and fixed frozen reference length, no extra clock margin"),
                  f,indent=2)
    collect(trial["side"],trial["goal"],trial["split"],raw,out/(case+".json"),
            hold_seconds=1.5,full_task=True,backend="warp",extra_final_park=True,trial=trial,arm_factory=partial(EndpointTeacher,match_release=a.match_release))
    frozen=FROZEN/f'{trial["side"]}_{trial["goal"]}_train'
    obj=score(raw/case,frozen,trial["side"])
    with (out/(case+"_frozen_judge.json")).open("x") as f:
        f.write(json.dumps(obj,indent=2,allow_nan=False)+"\n")
    print(case,obj["frozen_judge_pass"],obj["frozen_judge_first_failure"])


if __name__=="__main__":
    main()
