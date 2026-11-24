"""Probe eleven preregistered windows on the training Warp solver, with a 2 ms external servo."""
import argparse
import dataclasses
import json
import time
from pathlib import Path
from types import SimpleNamespace

import mujoco as mj
import mujoco_warp as mjw
import numpy as np
import torch
import warp as wp

from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from learning.b0.contact_warp import ContactPlant, PHASE_ID
from learning.b0.physics import make_model, settings
from scripts.b0.check_solver_continuity import buffers, COUNTERS
from scripts.b0.register_contact_dev import SEGMENTS
from scripts.b0.training_entry_response import arr, phases, register_solver

BASE = Path("results/b0/standard_temporal_20261124")
OLD = Path("results/raw_large/b0/temporal_entries_v1")
OUT = Path("results/b0/standard_dynamics_20261124/warp_windows")
RAW = Path("results/raw_large/b0/dynamics_20261124/warp_windows")
DEVICE = "cuda:0"
COARSE = .002


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def read(path):
    return json.loads(path.read_text())


def vec(x):
    return torch.as_tensor(np.array(x), dtype=torch.float32, device=DEVICE)


def registered():
    old = read(BASE / "nonterminal_wrist_replay_3.16.0.json")
    # Two extrema nominate the same training transition. Keep it once.
    rows = {a["trace_id"]:a for a in old["selection"]}
    for a in old["validation_hold"]:
        if a["branch"][0] != "u0":
            continue
        meta = read(OLD / a["start"] / "receipt.json")
        for label in ("actor", "ref_arm"):
            branch = ["u0", label, 0, 0.]
            lane = meta["labels"].index(branch)
            name = f"{a['start']}/t0/b{lane}"
            rows[name] = dict(a, trace_id=name, lane=lane, branch=branch)
    assert len(rows) == 11
    return rows


def use_step(plant, ratio):
    # Keep model/graph/buffer addresses intact. The captured integration and constraint kernels
    # read this per-model device array on every step. No internal bias or mass field is frozen.
    step = wp.to_torch(plant.sim.wp_model.opt.timestep)
    step.fill_(COARSE/ratio)
    wp.synchronize()
    assert np.isclose(step[0].item(), COARSE/ratio)


def reconstruct(plant, item, meta, sub, action, start, archive_anchor=False):
    use_step(plant, 1)
    path = Path(meta["row"]["path"])
    frame = meta["frame"]
    side = torch.full((plant.count,), int(item["side"] == "push"), dtype=torch.int32, device=DEVICE)
    phase = torch.as_tensor(phases(path), device=DEVICE)
    plant.reset(vec(arr(path, "qpos")[frame-10]).expand(plant.count, -1),
                vec(arr(path, "qvel")[frame-10]).expand(plant.count, -1))
    for j in range(frame-10, frame):
        ret = plant.step_contact(vec(arr(path, "action_clipped")[j]).expand(plant.count,-1), side,
                                 phase[j*10:(j+1)*10].expand(plant.count,-1))
        assert not ret["first_fail_substep"][0] and ret["valid_full_interval"][0]
    # The archived experiment used this registration, which keeps the preceding-solve bias.
    registered_state = register_solver(plant)
    t, b = item["transition"], item["lane"]
    for j in range(t):
        plant.step_contact(vec(action[j]), side, phase[(j+frame)*10:(j+frame+1)*10].expand(plant.count,-1))
    q = start["qpos"] if not t else sub["qpos_post"][t-1,b,-1]
    v = start["qvel"] if not t else sub["qvel_post"][t-1,b,-1]
    # Keep the full live physical state. Report possible differences from the archived rerun.
    errors = dict(branch_start_q_max=float(abs(registered_state["qpos"]-start["qpos"]).max()),
                  branch_start_v_max=float(abs(registered_state["qvel"]-start["qvel"]).max()),
                  branch_start_bias_max=float(abs(registered_state["qfrc_bias"]-start["qfrc_bias"]).max()),
                  window_q_max=float(abs(plant.data.qpos[b].cpu().numpy()-q).max()),
                  window_v_max=float(abs(plant.data.qvel[b].cpu().numpy()-v).max()))
    if archive_anchor:
        # The original 28-world trajectory stored exact q/v at every 2 ms and the initial
        # warmstart/bias/clock/ctrl. Reconstitute remaining solver buffers from the measured
        # trajectory with its actual ctrl. No mj_forward at the window, and no prescribed
        # state or modified internal force during any measured fine/coarse integration.
        d=plant.sim.wp_data
        for key in ("qpos","qvel","qacc_warmstart","qfrc_bias","ctrl","time"):
            buf=wp.to_torch(getattr(d,key))
            buf.copy_(vec(start[key]).expand_as(buf))
        for j in range(t):
            for tick in range(10):
                plant.data.ctrl[:]=vec(sub["ctrl"][j,:,tick])
                plant.sim.step()
                plant.data.qpos[:]=vec(sub["qpos_post"][j,:,tick])
                plant.data.qvel[:]=vec(sub["qvel_post"][j,:,tick])
        errors.update(exact_archive_q_max=float(abs(plant.data.qpos[b].cpu().numpy()-q).max()),
                      exact_archive_v_max=float(abs(plant.data.qvel[b].cpu().numpy()-v).max()))
        assert errors["exact_archive_q_max"] == errors["exact_archive_v_max"] == 0
    wp.synchronize()
    snapshot = [(x,wp.clone(x)) for x in buffers(plant.sim.wp_data)]
    counters = {name:getattr(plant,name).clone() for name in COUNTERS}
    return snapshot, counters, errors


def restore(plant, snapshot, counters):
    for live, recorded in snapshot:
        wp.copy(live,recorded)
    for key, value in counters.items():
        getattr(plant,key).copy_(value)
    wp.synchronize()


def integrate(plant, actions, full_ctrl, side, lane, ratio, bias, record=True):
    """Step complete 23d ctrl or canonical actions. Bias for servo at t comes from solve at t-2ms."""
    n = len(actions)
    side_wp = wp.from_torch(side, dtype=wp.int32)
    data = plant.data
    rod = plant.rod_ids[side[lane].long()]
    initial = {k:getattr(data,k)[lane].cpu().numpy().copy() for k in ("qpos","qvel")}
    rows = {}
    for k in range(n):
        if full_ctrl is None:
            target = (actions[k]*plant.scale + plant.offset)*plant.finger_factor
            data.ctrl[:,plant.actuator_ids] = target + bias[:,plant.dof]*plant.bias_gain
        else:
            data.ctrl[:] = full_ctrl[k]
        used_bias = bias[lane].clone()
        for z in range(ratio):
            plant.sim.step()
            # First fine solve in a servo interval samples qfrc_bias at its left endpoint.
            if z == 0:
                bias = data.qfrc_bias[:].clone()
            if not record:
                continue
            plant._contacts(side_wp)
            m = plant.metrics[lane]
            d = plant.sim.wp_data
            measurements = dict(qpos=data.qpos[lane], qvel=data.qvel[lane], ctrl=data.ctrl[lane],
                actuator_force=data.actuator_force[lane], wheel_load_N=m[:4], finger_load_N=m[4:6],
                door_robot_force_N=m[6:9], door_force_norm_sum_N=m[9], unexpected_contact_N=m[10],
                wheel_slip_m_s=m[11], tcp_start=data.site_xpos[lane,plant.tcp_id],
                handle_start=data.site_xpos[lane,rod], tcp_rotation_start=data.site_xmat[lane,plant.tcp_id],
                eq_residual_start=wp.to_torch(d.efc.pos)[lane,0], eq_row0_type=wp.to_torch(d.efc.type)[lane,0],
                nefc=wp.to_torch(d.nefc)[lane], overflow=plant.contact_audit.overflow_bits[lane],
                velocity_warmstart=wp.to_torch(d.qacc_warmstart)[lane], time_device=wp.to_torch(d.time)[lane],
                internal_bias_start=data.qfrc_bias[lane], servo_cached_bias=used_bias)
            for key,val in measurements.items():
                rows.setdefault(key,[]).append(val.clone())
    if record:
        arrays = {k:torch.stack(v).cpu().numpy() for k,v in rows.items()}
        arrays["q0"], arrays["v0"] = initial["qpos"], initial["qvel"]
        arrays["force_site_start_s"] = np.arange(n*ratio)*(COARSE/ratio)
        arrays["qv_end_s"] = np.arange(1,n*ratio+1)*(COARSE/ratio)
        arrays["judge_call_s"] = arrays["qv_end_s"].copy()
        # Check measured engine clock actually incorporated every selected microstep.
        assert abs(arrays["time_device"][-1] - arrays["time_device"][0]-(n*ratio-1)*COARSE/ratio) < 1e-4
        return bias, arrays
    return bias, None

def original_judge(model, meta, ratio):
    row=meta["row"]
    cfg = settings("push" if row["side"]=="push" else "mobile",1)
    ref = FrozenDoorReference.from_episode(row["formal_ref"],model)
    event_phases = SEGMENTS[row["segment"]][1]
    base = row["formal_start"]
    end = ref.phase_bounds[event_phases[-1]][1]
    ref = dataclasses.replace(ref, phase_bounds={k:(a*ratio,b*ratio) for k,(a,b) in ref.phase_bounds.items()})
    judge = ContactEvents(model,cfg,row["side"],ref,phases=event_phases,hold_seconds=3.,
                          start_step=base*ratio,score_until_step=(end-base)*ratio)
    judge.dt = COARSE/ratio
    return judge


def feed(judge, data, rec):
    n = len(rec["qpos"])
    for s in range(n):
        if judge.passed or judge.failure:
            break
        q = rec["q0"] if s == 0 else rec["qpos"][s-1]
        v = rec["v0"] if s == 0 else rec["qvel"][s-1]
        if "tcp_start" in rec:
            data.site_xpos[judge.tcp] = rec["tcp_start"][s]
            data.site_xpos[judge.handle] = rec["handle_start"][s]
            data.site_xmat[judge.tcp] = rec["tcp_rotation_start"][s].reshape(9)
        else:
            data.qpos[:] = q
            mj.mj_kinematics(judge.meter_model, data)
        data.qpos[:] = rec["qpos"][s]
        data.qvel[:] = rec["qvel"][s]
        data.actuator_force[:] = rec["actuator_force"][s]
        f, w = rec["finger_load_N"][s], rec["wheel_load_N"][s]
        c = SimpleNamespace(finger_normal=f,normal=w,both=bool((f>judge.cfg["contact_threshold_n"]).all()),
                supported=w >= judge.cfg["wheel_threshold_n"],door_force=rec["door_robot_force_N"][s],
                force_norm_sum=rec["door_force_norm_sum_N"][s],slip_long=np.atleast_1d(rec["wheel_slip_m_s"][s]),
                slip_lat=np.zeros(1),unexpected=["unregistered_pair"] if rec["unexpected_contact_N"][s]>judge.cfg["contact_threshold_n"] else [])
        judge.observe(data,c,q,v)


def before_window(model, meta, ratio, prior):
    # At a common starting state the event timers and clock have the same physical history.
    canonical = original_judge(model,meta,1)
    canonical.meter_model = model
    if prior is not None:
        feed(canonical,mj.MjData(model),prior)
    fine = original_judge(model,meta,ratio)
    for key in ("step","phase_start","good","lost","sliding","unloaded"):
        setattr(fine,key,getattr(canonical,key)*ratio)
    fine.saturation = canonical.saturation*ratio
    fine.i = canonical.i
    fine.failure = canonical.failure
    fine.events = canonical.events.copy()
    fine.terminal_event_step = None if canonical.terminal_event_step is None else canonical.terminal_event_step*ratio
    return fine


def archive_prior(sub, start, t, b):
    if not t:
        return None
    out = {"q0":start["qpos"],"v0":start["qvel"]}
    for k in ("qpos_post","qvel_post","actuator_force","finger_load_N","wheel_load_N","door_robot_force_N",
              "door_force_norm_sum_N","wheel_slip_m_s","unexpected_contact_N"):
        x=sub[k][:t,b]
        out[{"qpos_post":"qpos","qvel_post":"qvel"}.get(k,k)] = x.reshape((-1,)+x.shape[2:])
    return out


def safe_id(name):
    return name.replace("/","__")


def per_case(plant, item, args):
    name = item["trace_id"]
    folder=OLD/item["start"]
    meta=read(folder/"receipt.json")
    t,b = item["transition"],item["lane"]
    with np.load(folder/"substeps.npz") as f:
        sub = {k:f[k] for k in f.files}
    with np.load(folder/"start.npz") as f:
        start = dict(f)
    actions = np.load(folder/"dynamics.npz")["action"]
    snapshot,counters,errors = reconstruct(plant,item,meta,sub,actions,start,args.route in ("archive_ctrl","snapshot_servo"))
    prior = archive_prior(sub,start,t,b)
    count = plant.count
    cmds = vec(actions[t]).expand(10,-1,-1)
    controls = vec(sub["ctrl"][t]).transpose(0,1).contiguous()
    side = torch.full((count,),int(item["side"]=="push"),dtype=torch.int32,device=DEVICE)
    path = Path(meta["row"]["path"])
    frame = meta["frame"]
    for ratio in args.ratios:
        for repeat in (0,1):
            key = f"{safe_id(name)}__{args.route}__r{ratio}__rep{repeat}"
            json_file = RAW/"receipts"/(key+".json")
            if json_file.exists():
                print("existing",key,flush=True)
                continue
            since=time.monotonic()
            h=COARSE/ratio
            use_step(plant,ratio)
            prefix_record = None
            if args.route == "live_servo":
                plant.reset(vec(arr(path,"qpos")[frame-10]).expand(count,-1),
                            vec(arr(path,"qvel")[frame-10]).expand(count,-1))
                bias=plant.data.qfrc_bias[:].clone()
                a = vec(arr(path,"action_clipped")[frame-10:frame]).repeat_interleave(10,0)
                bias,prefix_record = integrate(plant,a[:,None].expand(-1,count,-1),None,side,b,ratio,bias)
                fine = original_judge(plant.model,meta,ratio)
                if t:
                    a=vec(actions[:t]).repeat_interleave(10,0)
                    bias, history = integrate(plant,a,None,side,b,ratio,bias)
                    feed(fine,mj.MjData(plant.model),history)
                ctrl = None
            else:
                restore(plant,snapshot,counters)
                fine = before_window(plant.model,meta,ratio,prior)
                bias=plant.data.qfrc_bias[:].clone()
                ctrl=controls if args.route in ("fixed_ctrl","archive_ctrl") else None
            history_failure = fine.failure
            unused, rec = integrate(plant,cmds,ctrl,side,b,ratio,bias)
            feed(fine,mj.MjData(plant.model),rec)
            rawfile=RAW/(key+".npz")
            RAW.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(rawfile,**rec)
            sol = np.linalg.norm(rec["door_robot_force_N"],axis=1)
            finger = rec["finger_load_N"]
            first6 = np.flatnonzero(sol>6.)
            archive_control = np.repeat(sub["ctrl"][t,b],ratio,axis=0)
            prefix_audit = None
            if prefix_record:
                prefix_file=RAW/(key+"_prefix.npz")
                np.savez_compressed(prefix_file,**prefix_record)
                prefix_audit=dict(raw=str(prefix_file),duration_s=.2,steps=len(prefix_record["qvel"]),
                                  finite=bool(np.isfinite(prefix_record["qvel"]).all()),
                                  peak_n=float(np.linalg.norm(prefix_record["door_robot_force_N"],axis=1).max()),
                                  end_q_max_delta_original=float(abs(prefix_record["qpos"][-1]-start["qpos"]).max()),
                                  end_v_max_delta_original=float(abs(prefix_record["qvel"][-1]-start["qvel"]).max()))
            joint_v=plant.mapping.dof[[19,21]]
            w=rec["qvel"][:,joint_v]
            f=fine.failure or {}
            first_rec_from_origin = f.get("interval_end_s")
            receipt=dict(key=key,id=name,registration=item,route=args.route,ratio=ratio,repeat=repeat,h_s=h,
                width_s=.02,real_prefix=prefix_audit,original_2ms_reconstruction=errors,
                raw=str(rawfile),window_origin_after_branch_s=.02*t,nticks=len(sol),
                training_metadata=dict(phase=meta["row"]["phase"],source=meta["row"]["path"],source_frame=frame),
                archive_max_ctrl_delta=float(abs(rec["ctrl"]-archive_control).max()),
                archive_max_q_delta_at_2ms=float(abs(rec["qpos"][ratio-1::ratio]-sub["qpos_post"][t,b]).max()),
                archive_max_v_delta_at_2ms=float(abs(rec["qvel"][ratio-1::ratio]-sub["qvel_post"][t,b]).max()),
                judge_failed_before_window=bool(history_failure),event_failure=fine.failure,events=fine.events,
                judge_first_call_with_failure_s_from_window=None if first_rec_from_origin is None else first_rec_from_origin-.02*t,
                max_force_n=float(sol.max()),force_peak_sample_s=float(sol.argmax()*h),
                first_gt6N_sample_s=None if not len(first6) else float(first6[0]*h),
                first_gt6N_judge_call_s=None if not len(first6) else float((first6[0]+1)*h),
                finger_both_duration_s=float(((finger>.01).all(1)).sum()*h),
                finger_both_at_start=bool((finger[0]>.01).all()), finger_min_n=finger.min(0).tolist(),
                wrist_peak_abs_rad_s=abs(w).max(0).tolist(),wrist_peak_end_s=((abs(w).argmax(0)+1)*h).tolist(),
                wrist_reversal_end_s=[(1+np.flatnonzero(np.diff(np.signbit(np.r_[rec["v0"][d], w[:,i]])))).tolist()
                                      for i,d in enumerate(joint_v)],
                elapsed_s=time.monotonic()-since,buffer_overflow=bool((rec["overflow"] & plant.contact_audit.buffer_mask).any()),
                counts=dict(prefix_reconstruction_2ms_shared_per_window=100+10*t,
                            measured_worlds=count,selected_world=b,recorded_window_ticks=10*ratio,
                            live_servo_preceding_branch_ticks=10*t*ratio if args.route=="live_servo" else 0))
            receipt["wrist_reversal_end_s"]=[[step*h for step in x] for x in receipt["wrist_reversal_end_s"]]
            dump(json_file,receipt)
            print(key, "q/v re-enact",errors["window_q_max"],errors["window_v_max"],
                  "peak",receipt["wrist_peak_abs_rad_s"],"door",receipt["max_force_n"],
                  "dur",receipt["finger_both_duration_s"], "failure",f.get("reason"),flush=True)


@torch.no_grad()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--route",choices=("fixed_ctrl","archive_ctrl","snapshot_servo","live_servo"),default="fixed_ctrl")
    p.add_argument("--ratios",nargs="+",type=int,default=[1,2,4],choices=[1,2,4,8,16])
    p.add_argument("--ids",nargs="+")
    args=p.parse_args()
    if (max(args.ratios)>4 or args.route not in ("fixed_ctrl","archive_ctrl")) and not args.ids:
        p.error("Choose registered decisive windows explicitly")
    items=registered()
    ids=args.ids if args.ids else list(items)
    assert len(ids)==len(set(ids)) and all(i in items for i in ids)
    if not (OUT/"registration.json").exists():
        dump(OUT/"registration.json",dict(items=list(items.values()),h_s=[.002,.001,.0005],
            critical_refinement_s=[.00025,.000125],replicates_per_condition=2,
            full_state="All nonempty Warp Data arrays recursively, counters, original 28 worlds",
            source="Seven unique archived nonterminal selections; bilateral original u0 actor/b0 and u0 ref_arm/b2, also measured in solver_retest. Native wrist file's reference/reference b26 is different.",
            dynamics="original mjlab Simulation and ContactPlant force audit; every integration solve recomputes all internal forces and mass",
            clocks="force/site at interval start, q/v at interval end; event observer called at end. External servo at t uses device qfrc_bias of preceding 2ms interval first solve (sample t-2ms), then holds full ctrl for 2ms. Initial live reset uses normal forward-derived cache, continuous prefix has no extra forward.",
            versions=dict(mujoco=mj.__version__,mujoco_warp=mjw.__version__,warp=wp.__version__)))
    plant=ContactPlant(make_model(),28,DEVICE,preserve_continuous_bias=True)
    for i in ids:
        per_case(plant,items[i],args)


if __name__=="__main__":
    main()
