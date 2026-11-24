"""Offline paired temporal closure of registered 2 ms Warp branch arrays."""
import argparse
import csv
import importlib.metadata
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from learning.b0.physics import ActionMap, make_model, settings


DT = 0.002
PERIODS = (1, 2, 5, 10)
METRICS = ("finger1_mm", "finger2_mm", "opening_mm", "coupling_mm", "j2_rad")


def write_rows(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, rows[0], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def stats(x):
    x = np.asarray(x, dtype=np.float64).ravel()
    if not len(x):
        return {"n": 0}
    return dict(n=len(x), rms=float(np.sqrt(np.mean(x*x))), p95_abs=float(np.quantile(abs(x), 0.95)),
                max_abs=float(np.max(abs(x))), mean_signed=float(np.mean(x)))


def measured(sub, key):
    a = sub[key].swapaxes(0, 1)
    return a.reshape(a.shape[0], -1, *a.shape[3:])


def with_start(q0, q):
    return np.concatenate((np.broadcast_to(q0, (len(q), 1, len(q0))), q), axis=1).astype(float)


def coordinates(x, fingers, j2):
    f1, f2 = 1000*x[..., fingers[0]], 1000*x[..., fingers[1]]
    return np.stack((f1, f2, f1-f2, f1+f2, x[..., j2]), axis=-1)


def first_index(mask):
    return np.where(mask.any(1), mask.argmax(1), mask.shape[1])


def group_masks(sub, data, rec, load_threshold):
    finger = measured(sub, "finger_load_N") > load_threshold
    dual = finger.all(-1)
    net = np.linalg.norm(measured(sub, "door_robot_force_N"), axis=-1)
    fail = data["fail"].T
    first = first_index(fail > 0)
    n, nmacro = fail.shape
    ticks = np.arange(nmacro*10)[None, :]
    macro = ticks // 10
    # 1-based substep of first failure, relative to this branch's physical start.
    failure_tick = np.array([10*i + fail[b, i] if i < nmacro else nmacro*10+1 for b, i in enumerate(first)])
    event_tick = np.array([(j["failure"] or {}).get("first_failure_substep", nmacro*10+1) for j in rec["judges"]])
    masks = {
        "all": np.ones_like(dual), "zero_net_door_force": net == 0,
        "zero_vector_with_nonzero_contact_sum": (net == 0) & (measured(sub, "door_force_norm_sum_N") > 0),
        "left_only_loaded": finger[..., 0] & ~finger[..., 1], "right_only_loaded": ~finger[..., 0] & finger[..., 1],
        "both_loaded": dual, "neither_finger_loaded": ~finger.any(-1),
        "both_loaded_full_20ms": np.repeat(dual.reshape(n, nmacro, 10).all(-1), 10, axis=1),
        "training_first_failure_20ms": macro == first[:, None],
        "training_before_or_at_failure_tick": ticks+1 <= failure_tick[:, None],
        "training_after_failure_tick_in_first_failure_20ms": (macro == first[:, None]) & (ticks+1 > failure_tick[:, None]),
        "training_after_first_failure_20ms": macro > first[:, None],
        "event_after_first_failure_tick": ticks+1 > event_tick[:, None],
        "event_after_termination": measured(sub, "event_phase") < 0,
        "training_eligible_20ms": np.repeat(data["valid"].T, 10, axis=1),
        "first_command_20ms": np.broadcast_to(macro == 0, dual.shape)
    }
    return masks, first, failure_tick, event_tick


def root_angle_error(q, v):
    # MuJoCo free-joint qvel[3:6] is angular velocity in the body frame.
    # Warp forward._integrate_pos uses normalized q * exp(dt*omega_body).
    shape = q[:, 1:, 0].shape
    before = Rotation.from_quat(q[:, :-1, 3:7].reshape(-1, 4), scalar_first=True)
    after = Rotation.from_quat(q[:, 1:, 3:7].reshape(-1, 4), scalar_first=True)
    delta = Rotation.from_rotvec(DT*v[:, 1:, 3:6].reshape(-1, 3))
    return ((before*delta).inv() * after).magnitude().reshape(shape)


def slope(outputs, numerator, denominator, command):
    dx = command[numerator]-command[denominator]
    return (outputs[numerator]-outputs[denominator])/dx if dx != 0 else None


def directions(row, rec, data, sub, q, actuator_ids, limits, threshold, predictions):
    labels = rec["labels"]
    force = measured(sub, "actuator_force")[:, :10, actuator_ids]
    saturated = abs(force) >= limits[actuator_ids]
    loads = measured(sub, "finger_load_N")[:, :10]
    mode = loads > threshold
    net_force = np.linalg.norm(measured(sub, "door_robot_force_N")[:, :10], axis=-1)
    physical = data["physical"]
    rows = []
    for actor in ("u0", "u200"):
        center = next(i for i, lab in enumerate(labels) if lab[:2] == [actor, "actor"])
        repeat = next(i for i, lab in enumerate(labels) if lab[:2] == [actor, "repeat"])
        for ch in (17, 22):
            choices = {v[3]: i for i, v in enumerate(labels) if v[:3] == [actor, "delta", ch]}
            scales = sorted(set(abs(x) for x in choices))
            command = physical[:, ch]
            for target, y, model_y in (("opening_m", q[:, 10, 2]/1000, predictions[:, 29]-predictions[:, 30]),
                                      ("j2_rad", q[:, 10, 4], predictions[:, 24])):
                scale_rows = []
                for size in scales:
                    pos, neg = choices[size], choices[-size]
                    triple = [neg, pos, repeat]
                    dxm, dxp = command[neg]-command[center], command[pos]-command[center]
                    noise = abs(y[repeat]-y[center])
                    r = dict(start=row["id"], split=row["split"], phase=row["phase"], side=row["side"],
                             actor=actor, command_channel=ch, response=target, perturbation_abs=size,
                             actual_minus=dxm, actual_plus=dxp, y_center=y[center], delta_y_minus=y[neg]-y[center],
                             delta_y_plus=y[pos]-y[center], repeat_abs=noise,
                             repeat_same_loaded_trace=bool((mode[repeat] == mode[center]).all()),
                             same_loaded_trace=bool((mode[triple] == mode[center]).all()),
                             same_failure_tick=bool((data["fail"][0,triple] == data["fail"][0,center]).all()),
                             same_saturation_trace=bool((saturated[triple] == saturated[center]).all()),
                             max_net_force_change_n=float(abs(net_force[[neg,pos]]-net_force[center]).max()),
                             max_finger_load_change_n=float(abs(loads[[neg,pos]]-loads[center]).max()),
                             max_coupling_change_mm=float(abs(q[[neg,pos],1:11,3]-q[center,1:11,3]).max()))
                    for name, output in (("observed", y), ("wm0", model_y)):
                        for key, a, b in (("minus", neg, center), ("plus", pos, center), ("central", pos, neg)):
                            r[name+"_"+key] = slope(output, a, b, command)
                    r["both_sides_resolved"] = bool(dxm < 0 < dxp and
                        min(abs(r["delta_y_minus"]), abs(r["delta_y_plus"])) > noise)
                    scale_rows.append(r)
                slopes = [x["observed_central"] for x in scale_rows]
                for r in scale_rows:
                    r["two_scale_central_signs_agree"] = (bool(np.sign(slopes[0]) == np.sign(slopes[1]))
                                                            if None not in slopes else None)
                    r["central_large_minus_small"] = slopes[1]-slopes[0] if None not in slopes else None
                    r["both_scales_mode_saturation_failure_and_signal_match"] = all(
                        x["same_loaded_trace"] and x["same_failure_tick"] and x["same_saturation_trace"] and
                        x["both_sides_resolved"] for x in scale_rows)
                    rows.append(r)
    return rows


def figure(output, histories):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(4, 2, figsize=(8.2, 7.1), sharex=True, sharey="row", layout="constrained")
    t = np.arange(11)*2
    for column, side in enumerate(("pull", "push")):
        q, v, failed = histories[side]
        for j, (color, line) in enumerate((("#0072B2", "-"), ("#D55E00", "--"))):
            axes[0,column].plot(t, q[:,j]-q[0,j], line, color=color, marker=".", label=f"finger {j+1}")
            axes[1,column].plot(t, v[:,j]/1000, line, color=color, marker=".")
        axes[2,column].plot(t, q[:,4]-q[0,4], color="#333333", marker=".")
        axes[3,column].plot(t, v[:,4], color="#333333", marker=".")
        axes[0,column].set_title(f"{side.capitalize()}   |   validation hold, u0")
        for ax in axes[:,column]:
            if 0 < failed <= 10:
                ax.axvspan(2*failed, 20, color="0.92", zorder=-2)
                ax.axvline(2*failed, lw=0.8, ls=":", color="0.3")
            ax.grid(axis="y", alpha=0.22)
        axes[-1,column].set_xlabel("Physical time (ms)")
    for ax, unit in zip(axes[:,0], ("Finger displacement (mm)", "Finger velocity (m/s)",
                                    "J2 displacement (rad)", "J2 velocity (rad/s)")):
        ax.set_ylabel(unit)
    axes[0,0].legend(loc="best", frameon=False)
    fig.suptitle("Measured first-command response\nShading begins at the independent event judge's first failure")
    fig.savefig(output/"temporal_velocity_displacement.png", dpi=170)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registration", type=Path, default=Path("results/b0/standard_response_20261124/registration.json"))
    p.add_argument("--raw", type=Path, default=Path("results/raw_large/b0/response_entries_v1"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--prediction-root", type=Path, help="Matched h1 predictions for this sample identity")
    p.add_argument("--wm", type=Path, help="Frozen C20 checkpoint for H1 predictions on the supplied states and commands")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = json.loads(args.registration.read_text())["starts"]
    model = make_model()
    mapping = ActionMap(model)
    sat = settings("mobile",1)["sat_fraction"]*model.actuator_forcerange[:,1]
    threshold = settings("mobile",1)["contact_threshold_n"]
    ai = mapping.actuator_ids[[17,22]]
    groups = defaultdict(list)
    closure = defaultdict(list)
    identities, residuals, slopes, response, holds = [], [], [], [], {}
    pred_root = args.prediction_root or args.raw/"predictions_response_w0"
    repeats = []
    if args.wm:
        import torch
        from learning.b0.contact_model import ContactRepresentation, contact_context
        from scripts.b0.score_temporal_wm import load_wm
        rep = ContactRepresentation(model, "cpu")
        wm, _ = load_wm(args.wm, model, rep, "cpu")
    for row in rows:
        d = args.raw/row["id"]
        rec = json.loads((d/"receipt.json").read_text())
        if rec.get("rejected"):
            identities.append(dict(id=row["id"], rejected=True))
            continue
        with np.load(d/"substeps.npz") as sub, np.load(d/"start.npz") as start, np.load(d/"dynamics.npz") as data:
            assert sub["qpos_post"].dtype == sub["qvel_post"].dtype == np.float32
            assert np.all(sub["numerical_valid"]) and not np.any(sub["overflow_bits"])
            qraw = with_start(start["qpos"], measured(sub, "qpos_post"))
            vraw = with_start(start["qvel"], measured(sub, "qvel_post"))
            q = coordinates(qraw, [29,30], mapping.q[17])
            v = coordinates(vraw, [28,29], mapping.dof[17])
            act = measured(sub, "actuator_force")[:, :10, ai]
            ctrl = measured(sub, "ctrl")[:, :10, ai]
            masks, first, fail_tick, event_tick = group_masks(sub, data, rec, threshold)
            micro = q[:,1:]-q[:,:-1]-DT*v[:,1:]
            summed = q[:,10::10]-q[:,:-1:10]-DT*v[:,1:].reshape(len(q),-1,10,5).sum(2)
            closure["each_2ms"].append(micro.reshape(-1,5))
            closure["sum_ten_2ms"].append(summed.reshape(-1,5))
            closure["root_quat_rad"].append(root_angle_error(qraw,vraw).ravel())
            boundary = data["state"]
            assert np.array_equal(qraw[:,::10,29:31], boundary[:,:,29:31].swapaxes(0,1))
            assert np.array_equal(vraw[:,::10,28:30], boundary[:,:,59:61].swapaxes(0,1))
            identity = dict(id=row["id"], split=row["split"], side=row["side"], phase=row["phase"], path=row["path"],
                            accepted_offset=rec["offset"], real_frame=rec["frame"], reference_frame=rec["goal_frame"],
                            prefix_substeps=100, actor_clock=int(start["clock"].item()), solver_time_s=float(start["time"]),
                            formal_clock_start=rec.get("formal_clock_start",row["formal_start"]), raw_dir=str(d),
                            actor_history="start.npz history, clean_history, previous, goal, u0, u200",
                            command="dynamics.npz physical and action", solver="registered with preserved continuous qfrc_bias" if "qfrc_bias" in start else "archived full-batch forward before first command")
            identities.append(identity)
            if args.wm:
                with torch.no_grad():
                    x = torch.from_numpy(data["state"][0])
                    a = torch.from_numpy(data["action"][0])
                    ctx = contact_context(model, row["side"], "cpu").expand(len(x), -1)
                    aux, h = wm(rep.represent(x), a, x[:,:7], ctx)
                    predicted = rep.reconstruct_full_state(aux,h).numpy()
            else:
                predicted = np.load(pred_root/(row["id"]+".npy"), mmap_mode="r")[0]
            for actor in ("u0","u200","reference"):
                center = next(i for i,k in enumerate(rec["labels"]) if k[:2] == [actor,"reference" if actor=="reference" else "actor"])
                repeat = next(i for i,k in enumerate(rec["labels"]) if k[:2] == [actor,"repeat"])
                assert np.array_equal(data["action"][:,center],data["action"][:,repeat])
                repeats.append(dict(start=row["id"], actor=actor, jaw_h1_repeat_abs_mm=abs(q[repeat,10,2]-q[center,10,2]),
                    finger_h1_path_repeat_max_mm=np.max(abs(q[repeat,1:11,:2]-q[center,1:11,:2])),
                    j2_h1_path_repeat_max_rad=np.max(abs(q[repeat,1:11,4]-q[center,1:11,4]))))
            slopes.extend(directions(row, rec, data, sub, q, ai, sat, threshold, predicted))
            for b, (actor, label, ch, delta) in enumerate(rec["labels"]):
                key = dict(start=row["id"],split=row["split"],side=row["side"],phase=row["phase"],
                           actor=actor,branch=label,channel=ch,requested_delta=delta,lane=b)
                r = dict(**key, training_first_failure_tick=fail_tick[b] if first[b] < len(data["fail"]) else None,
                         event_first_failure_tick=(rec["judges"][b]["failure"] or {}).get("first_failure_substep"),
                         j2_target_rad=data["physical"][b,17], jaw_target_mm=1000*data["physical"][b,22],
                         j2_peak_abs_actuator_nm=abs(act[b,:,0]).max(), finger_peak_abs_actuator_n=abs(act[b,:,1]).max(),
                         j2_sat_ticks=int((abs(act[b,:,0]) >= sat[ai[0]]).sum()),
                         finger_sat_ticks=int((abs(act[b,:,1]) >= sat[ai[1]]).sum()),
                         ctrl0_j2_rad=ctrl[b,0,0], ctrl0_active_finger_m=ctrl[b,0,1])
                for idx, label_coord in enumerate(METRICS):
                    path = q[b,:11,idx]-q[b,0,idx]
                    velocity = v[b,:11,idx]
                    r[label_coord+"_actual_delta"] = path[-1]
                    r[label_coord+"_peak_abs_speed_per_s"] = abs(velocity).max()
                    r[label_coord+"_speed_sign_reversals"] = int(np.count_nonzero(np.diff(np.sign(velocity[velocity!=0]))))
                response.append(r)
            for n in PERIODS:
                c = (n+1)/(2*n)
                disp = n*DT*((1-c)*v[:,:-1:n]+c*v[:,n::n])
                err = q[:,:-1:n]+disp-q[:,n::n]
                for name, mask in masks.items():
                    selected = mask.reshape(len(q),-1,n).all(-1)
                    groups[(n,name)].append(err[selected])
                for b, (actor, label, ch, delta) in enumerate(rec["labels"]):
                    line = dict(start=row["id"], split=row["split"], side=row["side"], phase=row["phase"], lane=b,
                                actor=actor, branch=label, channel=ch, requested_delta=delta, block_ms=2*n)
                    for idx, metric in enumerate(METRICS):
                        x = err[b,:,idx]
                        line[metric+"_rms"] = np.sqrt(np.mean(x*x))
                        line[metric+"_h1_blocks_rms"] = np.sqrt(np.mean(x[:10//n]**2))
                        line[metric+"_h1_last_block_signed"] = x[10//n-1]
                    line["opening_displacement_sign_matches"] = int(
                        np.count_nonzero(np.sign(disp[b,:,2]) == np.sign(np.diff(q[b,::n,2]))))
                    line["block_count"] = len(err[b])
                    residuals.append(line)
            if row["split"] == "validation" and row["phase"] == "hold":
                b = rec["labels"].index(["u0","actor",0,0.])
                holds[row["side"]] = (q[b,:11].copy(),v[b,:11].copy(),event_tick[b])
    by_group = {f"{2*n}ms": {} for n in PERIODS}
    for (n,name), parts in groups.items():
        arr = np.concatenate(parts)
        by_group[f"{2*n}ms"][name] = {metric:stats(arr[:,i]) for i,metric in enumerate(METRICS)}
    micro_result = {}
    for name in ("each_2ms","sum_ten_2ms"):
        a = np.concatenate(closure[name])
        micro_result[name] = {metric:stats(a[:,i]) for i,metric in enumerate(METRICS)}
    micro_result["root_rotation_2ms_rad"] = stats(np.concatenate(closure["root_quat_rad"]))
    stats_out = dict(method="GenCoord signed residual = true start + N*0.002*((1-c)*v0 + c*vN) - true end; c=(N+1)/(2*N); blocks aligned to outer intervals. Finger velocities from raw qvel[28:30], positions qpos[29:31].",
        identity="Float32 arrays scored in float64. Physical joint and root residuals use all recorded microsteps (including postfailure); force and contact belong to interval start, q/v to postintegration endpoint. Groups require every microstep in block to match; groups overlap. No fitting or training.",
        timing="Training first failure uses first nonzero dynamics.fail in trajectory, 1-based local substep. Training validity uses recorded data.valid. Event clock uses independent rejudged nominal segment and -1 after termination. Only original training source qualification defines legal train windows.",
        direction="Physical first held action only; commands after clipping. J2 in rad; jaw command and opening response in m. One-sided and central slopes retain actual asymmetric denominators, actual deltas and repeated-command floor. Full two-scale interpretation also requires agreement of one-sided signs/magnitudes and both resolutions; no smoothness accuracy threshold.",
        versions={p:importlib.metadata.version(p) for p in ("numpy","mujoco","mujoco-warp","warp-lang")},
        implementation="MuJoCo-Warp _src/forward.py and _src/math.py quat_integrate uses body-frame rotation q*exp(h*w); independent SO(3) product and geodesic residual. Scalar q integration uses post-step v.",
        upstream=json.loads(Path("config/b0/source_lock.json").read_text())["upstream"], registration=str(args.registration),
        starts=identities, source_trajectories={s:sorted({r["path"] for r in rows if r["split"]==s}) for s in ("train","validation")},
        finger_load_threshold_n=threshold, saturation_fraction=settings("mobile",1)["sat_fraction"],
        fields="Both passive and active slide positions and velocities, per-finger handle normal loads, net and sum door force available; only active finger has actuator/ctrl. Independent constraint impulse and per-substep bias are absent from archived arrays.",
        micro_closure=micro_result, strata=by_group, repeat_resolution=repeats,
        direction_wm=str(args.wm or pred_root))
    (args.output/"temporal_closure.json").write_text(json.dumps(stats_out, indent=2,allow_nan=False)+"\n")
    write_rows(args.output/"temporal_residuals.csv",residuals)
    write_rows(args.output/"temporal_first_responses.csv",response)
    write_rows(args.output/"temporal_directions.csv",slopes)
    figure(args.output, holds)


if __name__ == "__main__":
    main()
