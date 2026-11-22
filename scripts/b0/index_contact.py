"""Index real variable-length contact episodes; measure action scale and RSI reconstruction."""
from argparse import ArgumentParser
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from scripts.b0.collect_reference import DECIMATION, dump_json
from learning.b0.physics import ActionMap
from p6_contacts import ContactMeter
from p6_scene import build


SEGMENTS = {
    0: (("close", ("approach_arm", "grasp")), ("grip_hold", ("hold",))),
    5: (("open_5", ("open", "hold")), ("release", ("release", "retreat_arm", "post_release_hold"))),
    15: (("open_15", ("open", "hold")),),
}


def phase_bounds(path, meta):
    p = np.load(path/"substeps/phase.npy", mmap_mode="r")
    changes = np.r_[0, np.flatnonzero(np.diff(p)) + 1, len(p)]
    return {meta["phases"][int(p[start])]: (int(start), int(end))
            for start, end in zip(changes[:-1], changes[1:])}


def recon_error(model, cfg, path, start, prefix):
    """From stored initial state, physically rebuild preceding intervals; compare the next 20 ms."""
    data = mj.MjData(model)
    m = ActionMap(model)
    fields = {name:np.load(path/"substeps"/(name+".npy"),mmap_mode="r") for name in
              ("qpos","qvel","physical_target","finger_load_N","wheel_load_N")}
    init = start - prefix
    data.qpos[:] = fields["qpos"][init]
    data.qvel[:] = fields["qvel"][init]
    data.time = init * model.opt.timestep
    mj.mj_forward(model,data)
    meter = ContactMeter(model, "preview_floor", "back" if cfg["stage"] == "push" else "front")
    hinge = model.joint("door_single_hinge")
    maxima = np.zeros(8)
    for i in range(init, start+DECIMATION):
        # Replay the actual physical targets with the state-dependent servo; do not copy ctrl.
        data.ctrl[m.actuator_ids] = fields["physical_target"][i]*m.finger_factor + data.qfrc_bias[m.dof]*m.bias_gain
        mj.mj_step(model,data)
        if i >= start:
            c = meter.measure(data)
            target_q,target_v = fields["qpos"][i+1],fields["qvel"][i+1]
            finger_q = [model.joint(f"piper_gripper_joint{n}").qposadr.item() for n in (1,2)]
            delta = np.abs(data.qpos-target_q)
            vdelta = np.abs(data.qvel-target_v)
            maxima = np.maximum(maxima, [np.linalg.norm(delta[:3]), np.max(delta[m.q[16:22]]),
                delta[finger_q].max(), delta[hinge.qposadr.item()], vdelta[hinge.dofadr.item()],
                np.max(np.abs(fields["finger_load_N"][i]-c.finger_normal)),
                np.max(np.abs(fields["wheel_load_N"][i]-c.normal)),
                np.max(np.not_equal(fields["finger_load_N"][i] > cfg["contact_threshold_n"],
                                    c.finger_normal > cfg["contact_threshold_n"]))])
    names = ("root_position_m","arm_angle_rad","finger_m","door_rad","door_speed_rad_s",
             "finger_load_N","wheel_load_N","finger_contact_disagreement")
    return dict(prefix_physics_steps=prefix, measured_physics_steps=DECIMATION, **dict(zip(names,maxima)))


def index(root):
    episodes,segments,actions = [], [], []
    models = {}
    for path in sorted(root.iterdir()):
        if not (path/"metadata.json").is_file():
            continue
        meta = json.loads((path/"metadata.json").read_text())
        if not meta["finished"] or not meta["held_action_replay"]:
            raise ValueError(f"Not a finished held-action episode: {path}")
        cfg = json.loads((path/"config.json").read_text())
        # These episodes vary the initial position/yaw only. Cache models by
        # side and any actual physical-parameter perturbation.
        physical_parameters = {k:v for k,v in cfg["perturbation"].items() if k not in ("dx","dy","yaw","door")}
        model_key = (cfg["stage"], tuple(sorted(physical_parameters.items())))
        if model_key not in models:
            models[model_key] = build(cfg)
        model = models[model_key]
        mapping = ActionMap(model)
        targets = np.load(path/"physical_target.npy")
        home = model.key("home").qpos[mapping.q].copy()
        home[12:16] = 0.
        home[-1] *= 2.
        units = .25*model.actuator_forcerange[mapping.actuator_ids,1] / model.actuator_gainprm[mapping.actuator_ids,0]
        units[-1] *= 2.
        actions.append(dict(episode_id=meta["episode_id"], units="network output before home offset and effort scaling",
                            channel_names=mapping.names, quarter_effort_units=units.tolist(),
                            max_abs_network_units=np.max(np.abs((targets-home)/units),axis=0).tolist()))
        physical = np.load(path/"physics_step.npy")
        dt = np.load(path/"actual_dt.npy")
        valid = np.load(path/"valid_full_interval.npy")
        assert np.array_equal(valid,np.diff(physical)==DECIMATION)
        assert np.allclose(dt,np.diff(physical)*model.opt.timestep,rtol=0,atol=1e-12)
        n = meta["physics_steps"]
        bounds = phase_bounds(path, meta)
        episodes.append(dict(episode_id=meta["episode_id"],path=str(path),side=meta["task"],
                             split=meta["wm_split"],initial_perturbation=meta["initial_perturbation"],
                             valid_fixed_dt=int(valid.sum()), actual_physics_steps=n,
                             terminal_partial_substeps=n%10, physical_teacher_pass=meta["success"],
                             first_failure_interval=meta["first_failure_physics_interval"], failure=meta["failure"],
                             phase_intervals=bounds, goal_deg=meta["target_angle_deg"],
                             final_deg=meta["final_door_deg"]))
        if not (meta["success"] and meta["wm_split"]=="train"):
            continue
        for name, phases in SEGMENTS[meta["target_angle_deg"]]:
            begin,end = bounds[phases[0]][0],bounds[phases[-1]][1]
            start = begin // DECIMATION
            stop = int(np.searchsorted(physical,end))
            row = dict(name=f"{meta['task']}_{name}", episode_id=meta["episode_id"],
                       phases=list(phases), event_start_step=begin,event_stop_step_exclusive=end,
                       start_policy_k=start,stop_policy_k=stop,actual_start_physics_step=int(physical[start]),
                       actual_stop_physics_step=int(physical[stop]),history_first_policy_k=start-10,
                       target_absolute_deg=meta["target_angle_deg"],
                       initial_absolute_deg=float(np.rad2deg(np.load(path/"qpos.npy",mmap_mode='r')[start,-1])),
                       final_boundary_is_full_interval=bool(valid[stop-1]))
            row["reconstruction_comparison"] = [recon_error(model,cfg,path,start*DECIMATION,p) for p in (0,10,100)]
            segments.append(row)
    return dict(episodes=episodes,segments=segments,action_diagnostics=actions,
                time_convention="Bounds index the same episode; real state rows include every 10th initial state and the exact terminal. Read actual_dt and valid_full_interval for last transition. Never sample beyond the terminal or into another episode.",
                split_protocol="Validation uses independently integrated perturbations; all slices of a physical episode inherit its split. Repeated goals with the same start and side share their prefix and do not count as independent initial conditions.",
                rsi="For the finite-prefix variants, rewind to the stored qpos/qvel and mj_forward, then integrate the previously issued targets through the real servo. Prefix time and contacts are excluded from scored windows. Errors measured across first 10 scored intervals against uninterrupted execution.")


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    result=index(args.root)
    args.out.parent.mkdir(exist_ok=True, parents=True)
    dump_json(args.out,result)
    print(f"{len(result['episodes'])} episodes, {len(result['segments'])} segment references",flush=True)


if __name__ == "__main__":
    main()
