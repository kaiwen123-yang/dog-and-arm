"""Run the same held contact commands through three real physics backends."""
from argparse import ArgumentParser
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from scripts.b0.collect_reference import dump_json
from learning.b0.physics import ActionMap
from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from p6_scene import build


def source(root, side):
    path = root / f"{side}_5_train"
    cfg = json.loads((path/"config.json").read_text())
    fingers = np.load(path/"substeps/finger_load_N.npy")
    first = np.flatnonzero((fingers > cfg["contact_threshold_n"]).all(1))[0]
    start = max(10, int(first//10)-4)*10
    return dict(path=path, cfg=cfg, side=side, start=start, prefix=10, first=int(first),
                q=np.load(path/"substeps/qpos.npy",mmap_mode="r")[start-10].copy(),
                v=np.load(path/"substeps/qvel.npy",mmap_mode="r")[start-10].copy(),
                actions=np.load(path/"action_clipped.npy",mmap_mode="r")[start//10-1:start//10+32].copy())


def simulate(args):
    output = args.output / args.backend
    output.mkdir(parents=True, exist_ok=False)
    src = [source(args.root,side) for side in ("pull","push")]
    model = build(src[0]["cfg"])
    mapping = ActionMap(model)
    # Same mechanical model and two physical handles. Each world's meter selects its own rod.
    m2 = build(src[1]["cfg"])
    for name in ("body_pos","body_quat","body_mass","body_inertia","geom_pos","geom_friction","site_pos",
                 "jnt_axis","jnt_range","dof_damping","dof_frictionloss","actuator_gainprm","actuator_biasprm"):
        if not np.array_equal(getattr(model,name),getattr(m2,name)):
            raise ValueError(f"Physics differs between sides at {name}")
    data = [mj.MjData(model) for s in src]
    judges = [ContactEvents(model, s["cfg"], s["side"], FrozenDoorReference.from_episode(s["path"],model),
                            phases=["grasp","open","hold"], start_step=s["start"], hold_seconds=3.)
              for s in src]
    failures, traces = [None,None],[[],[]]
    ids = [s["cfg"]["handle_site"] for s in src]
    wp_data = None
    if args.backend == "warp316":
        import mujoco_warp as mjw
        import torch
        import warp as wp
        from learning.b0.research_env import ResearchPlant
        count = args.worlds
        if count%2 or count<2:
            raise ValueError("Warp comparison alternates front and back worlds; require an even batch")
        plant = ResearchPlant(model, count, "cuda:0")
        wp_data = plant.sim.wp_data
        q = torch.as_tensor(np.stack([x["q"] for x in src]),device="cuda",dtype=torch.float32)
        v = torch.as_tensor(np.stack([x["v"] for x in src]),device="cuda",dtype=torch.float32)
        plant.reset(q.repeat(count//2,1),v.repeat(count//2,1))
        buffer_mask = plant.contact_audit.buffer_mask
        peak_nacon = peak_nefc = capacity_hits = solver_cap_intervals = 0
    elif args.worlds != 2:
        raise ValueError("CPU requires two distinct worlds")
    if mj.__version__ != ("3.3.0" if args.backend=="native33" else "3.16.0"):
        raise ValueError("Wrong interpreter for selected backend")
    for s,d in zip(src,data):
        d.qpos[:],d.qvel[:] = s["q"],s["v"]
        mj.mj_forward(model,d)
    for i in range(330):
        idx = i//10
        before = [(d.qpos.copy(),d.qvel.copy()) for d in data]
        if wp_data is not None:
            cmd = torch.as_tensor(np.stack([s["actions"][idx] for s in src]),device="cuda",dtype=torch.float32)
            target = ((cmd*plant.scale + plant.offset)*plant.finger_factor).repeat(count//2,1)
            plant.data.ctrl[:,plant.actuator_ids] = target + plant.data.qfrc_bias[:,plant.dof]*plant.bias_gain
            plant.sim.step()
            nj = wp_data.nefc.numpy()
            nc = int(wp_data.nacon.numpy()[0])
            bits = wp_data.overflow.numpy()
            peak_nacon=max(peak_nacon,nc)
            peak_nefc=max(peak_nefc,int(nj.max()))
            capacity_hits += int(((bits & buffer_mask)!=0).any() or nc>wp_data.naconmax or nj.max()>wp_data.njmax)
            solver_cap_intervals += int(((bits & ~buffer_mask)!=0).any())
            for w,d in enumerate(data):
                mjw.get_data_into(d,model,wp_data,world_id=w)
        else:
            for s,d in zip(src,data):
                target = (mapping.offset + s["actions"][idx]*mapping.scale)*mapping.finger_factor
                d.ctrl[mapping.actuator_ids] = target + d.qfrc_bias[mapping.dof]*mapping.bias_gain
                mj.mj_step(model,d)
        if i<10:
            continue
        for w,(s,d,judge) in enumerate(zip(src,data,judges)):
            q0,v0 = before[w]
            c = judge.meter.measure(d)
            if not failures[w] and not judge.passed:
                failures[w] = judge.observe(d,c,q0,v0)
            # Post-integrated state for hinge angle, solved interval-start state for all geometry/forces.
            delta = d.site("p4_grasp").xpos-d.site(ids[w]).xpos
            traces[w].append([i-10,float(q0[-1]),float(d.qpos[-1]),*delta,*c.normal,*c.finger_normal,
                              max(c.unexpected.values(),default=0.),np.linalg.norm(c.door_force),
                              d.ncon,d.nefc])
    report = {}
    for s,trace,judge,failure in zip(src,traces,judges,failures):
        a=np.array(trace)
        np.savetxt(output/(s["side"]+".csv"),a, delimiter=",",comments="",fmt="%.10g",
                   header="substep,door_start_rad,door_end_rad,tcp_minus_rod_x_m,tcp_minus_rod_y_m,tcp_minus_rod_z_m,wheel_FAR_N,wheel_FBL_N,wheel_RAR_N,wheel_RBL_N,finger_1_N,finger_2_N,unexpected_N,door_net_N,ncon,nefc")
        both=(a[:,10:12]>s["cfg"]["contact_threshold_n"]).all(1)
        report[s["side"]]=dict(source_episode=str(s["path"]),start_step=s["start"],
            source_first_both=s["first"],prefix_substeps=10,scored_intervals=len(trace),held_actions=32,
            first_both_substep=int(np.flatnonzero(both)[0]) if both.any() else None,
            both_substeps=int(both.sum()), min_wheel_N=float(a[:,6:10].min()), peak_grip_error_m=float(np.linalg.norm(a[:,3:6],axis=1).max()),
            tip_door_deg=float(np.rad2deg(a[-1,2])), peak_net_force_N=float(a[:,13].max()),
            peak_unexpected_N=float(a[:,12].max()), event_failure=failure, events=judge.events)
    report.update(backend=args.backend,mujoco=mj.__version__,worlds=args.worlds,
                  sampling="320 solved 2 ms intervals after one 10-substep reconstruction prefix; frozen teacher commands, not Actor evaluation")
    if wp_data is not None:
        report["capacity"] = dict(naconmax=int(wp_data.naconmax), njmax=int(wp_data.njmax), peak_nacon=peak_nacon,
                                  peak_nefc=peak_nefc, buffer_overflow_intervals=capacity_hits,
                                  cumulative_iteration_cap_bit_intervals=solver_cap_intervals, monitored_steps=330)
        report["warp"]=wp.__version__
        report["torch"]=torch.__version__
        report["gpu"]=torch.cuda.get_device_name()
    dump_json(output/"summary.json",report)
    print(report,flush=True)


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("backend",choices=("native33","cpu316","warp316"))
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--worlds",type=int,default=2)
    simulate(p.parse_args())


if __name__ == "__main__":
    main()
