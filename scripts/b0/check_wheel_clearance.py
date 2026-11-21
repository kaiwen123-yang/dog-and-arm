"""Compare exact wheel mesh-to-plane clearance with solved 500 Hz loads."""

import argparse
import json
from pathlib import Path
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from learning.b0.physics import LIMBS, NativePlant, make_model


class WheelGeometry:
    def __init__(self, model):
        self.floor = model.geom("preview_floor").id
        self.geoms = []
        self.hulls = []
        self.section = []
        self.info = {}
        for limb in LIMBS:
            body = model.body(f"m1_{limb}_FOOT_LINK").id
            joint = model.joint(f"m1_{limb}_FOOT_JOINT").id
            ids = np.where(
                (model.geom_bodyid == body)
                & ((model.geom_contype | model.geom_conaffinity) != 0)
            )[0]
            geom = int(ids.item())
            mesh = model.geom_dataid[geom]
            start = model.mesh_vertadr[mesh]
            nvert = model.mesh_vertnum[mesh]
            vertices = model.mesh_vert[start : start + nvert].astype(float)
            graph = model.mesh_graph[model.mesh_graphadr[mesh] :]
            # MuJoCo's convex mesh graph: nverts, nfaces, edge offsets, vertex IDs.
            count = int(graph[0])
            hull = vertices[graph[2 + count : 2 + 2 * count]]
            rot = np.empty(9)
            mj.mju_quat2Mat(rot, model.geom_quat[geom])
            # Body-frame axial/radial coordinates about the actual spin hinge.
            v = hull @ rot.reshape(3, 3).T + model.geom_pos[geom] - model.jnt_pos[joint]
            axis = model.jnt_axis[joint]
            axial = v @ axis
            radius = np.linalg.norm(v - axial[:, None] * axis, axis=1)
            self.geoms.append(geom)
            self.hulls.append(hull)
            self.section.append((joint, axial, radius))
            self.info[limb] = dict(
                mesh=model.mesh(mesh).name,
                geom_id=geom,
                mesh_vertices=int(nvert),
                hull_vertices=count,
                max_radius_m=float(radius.max()),
                geom_margin_m=float(model.geom_margin[geom]),
                geom_gap_m=float(model.geom_gap[geom]),
            )
        self.floor_margin = float(model.geom_margin[self.floor])

    def at(self, d):
        normal = d.geom_xmat[self.floor].reshape(3, 3)[:, 2]
        origin = d.geom_xpos[self.floor]
        exact, revolved = [], []
        for geom, hull, (joint, axial, radius) in zip(
            self.geoms, self.hulls, self.section
        ):
            # geom_xmat maps centered mesh coordinates to world coordinates.
            local_n = normal @ d.geom_xmat[geom].reshape(3, 3)
            exact.append((d.geom_xpos[geom] - origin) @ normal + np.min(hull @ local_n))
            cosine = np.clip(d.xaxis[joint] @ normal, -1.0, 1.0)
            radial = np.sqrt(1 - cosine**2)
            revolved.append(
                (d.xanchor[joint] - origin) @ normal
                + np.min(axial * cosine - radius * radial)
            )
        return exact, revolved


def first_unload(all_supported, limit=50):
    run = 0
    for t, supported in enumerate(all_supported):
        run = 0 if supported else run + 1
        if run == limit:
            return t + 1
    return None


def summary(gap, envelope, loads):
    supported = loads >= 1.0

    def quantiles(arr):
        return list(np.quantile(arr, [0, 0.05, 0.50, 0.95, 1])) if arr.size else []

    def confusion(pred):
        return dict(
            loaded_pred_loaded=int(np.sum(supported & pred)),
            loaded_pred_unloaded=int(np.sum(supported & ~pred)),
            unloaded_pred_loaded=int(np.sum(~supported & pred)),
            unloaded_pred_unloaded=int(np.sum(~supported & ~pred)),
        )

    out = dict(
        substeps=len(loads),
        wheel_steps=int(loads.size),
        loaded_n=int(supported.sum()),
        unloaded_n=int((~supported).sum()),
        gap_quantiles_mm_loaded=quantiles(gap[supported] * 1000),
        gap_quantiles_mm_unloaded=quantiles(gap[~supported] * 1000),
        mesh_minus_revolved_quantiles_mm=quantiles((gap - envelope).ravel() * 1000),
        gap_confusion={str(mm): confusion(gap <= mm / 1000) for mm in (-0.1, 0, 0.1)},
        revolved_confusion_at_zero=confusion(envelope <= 0),
    )
    # Geometrically very similar states with different solved support labels.
    low_ids = np.flatnonzero(~supported)
    high_ids = np.flatnonzero(supported)
    if low_ids.size and high_ids.size:
        g = gap.ravel()
        sorted_high = high_ids[np.argsort(g[high_ids])]
        offsets = np.searchsorted(g[sorted_high], g[low_ids])
        candidates = np.stack(
            [
                sorted_high[np.clip(offsets + i, 0, len(sorted_high) - 1)]
                for i in (-1, 0)
            ]
        )
        diff = np.abs(g[candidates] - g[low_ids])
        side, col = np.unravel_index(np.argmin(diff), diff.shape)
        idx = [int(candidates[side, col]), int(low_ids[col])]
        out["closest_opposite_labels"] = [
            dict(
                gap_mm=1000 * g[i],
                load_N=loads.flat[i],
                wheel=LIMBS[i % 4],
                pooled_step=i // 4,
            )
            for i in idx
        ]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--teacher", type=Path)
    group.add_argument("--evaluation", type=Path)
    group.add_argument("--wm-evaluation", type=Path)
    parser.add_argument(
        "--validation-episode", type=Path, help="Time-aligned held-out teacher episode"
    )
    parser.add_argument("--cases", nargs="+", help="Frozen evaluation case IDs")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    m = make_model()
    geometry = WheelGeometry(m)
    if args.wm_evaluation:
        if not args.validation_episode:
            parser.error("--wm-evaluation needs --validation-episode")
        saved = json.loads((args.wm_evaluation / "evaluation.json").read_text())
        if (
            mj.__version__ != saved["mujoco_version"]
            or args.validation_episode.name != saved["validation_episode_id"]
        ):
            raise ValueError(
                "Saved model diagnostic and validation source do not match"
            )
        raw = ROOT / saved["raw_path"] / "held_out"
        beginnings = np.load(raw / "start_policy_step.npy")
        predicted = np.load(raw / "predicted_qpos.npy")
        actual = np.load(raw / "actual_qpos.npy")
        # At successor boundary k use the force solved FROM k, not the last force
        # of the preceding interval. The final teacher state has no following step.
        teacher_q = np.load(args.validation_episode / "substeps/qpos.npy")
        loads = np.load(args.validation_episode / "substeps/wheel_load_N.npy")
        d = mj.MjData(m)

        def signed_gap(q):
            d.qpos[:] = q
            mj.mj_kinematics(m, d)
            return geometry.at(d)[0]

        rows = []
        for h in (1, 7, 32):
            starts = (beginnings + h) * 10
            valid = starts < len(loads)
            indices = starts[valid]
            q = actual[valid, h - 1]
            if not np.allclose(q, teacher_q[indices], rtol=0, atol=1e-10):
                raise RuntimeError(
                    "WM diagnostic and native teacher state boundary differ"
                )
            real = np.asarray([signed_gap(x) for x in q])
            pred = np.asarray([signed_gap(x) for x in predicted[valid, h - 1]])
            supported = loads[indices] >= 1.0
            err = np.abs(real - pred) * 1000

            def classification(gaps):
                labels = gaps <= 0
                return dict(
                    loaded_pred_loaded=int((supported & labels).sum()),
                    loaded_pred_unloaded=int((supported & ~labels).sum()),
                    unloaded_pred_loaded=int((~supported & labels).sum()),
                    unloaded_pred_unloaded=int((~supported & ~labels).sum()),
                )

            rows.append(
                dict(
                    horizon=h,
                    starts_scored=len(indices),
                    wheel_states=int(err.size),
                    absolute_gap_error_mm_p50_p95_max=np.quantile(
                        err, [0.5, 0.95, 1]
                    ).tolist(),
                    measured_q=classification(real),
                    predicted_q=classification(pred),
                )
            )
        result = dict(
            evaluation=str(args.wm_evaluation),
            validation=str(args.validation_episode),
            load_alignment="First solved 2 ms step FROM successor boundary; no terminal successor sample",
            geometry="compiled mesh hull with complete wheel spin phase",
            horizons=rows,
        )
        args.output.parent.mkdir(exist_ok=True, parents=True)
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
            stream.write("\n")
        return
    entries = []
    if args.teacher:
        if mj.__version__ != "3.3.0":
            raise RuntimeError(
                "Teacher replay requires the acquisition version MuJoCo 3.3.0"
            )
        paths = [
            args.teacher / n
            for n in ("support", "moving_arm", "park", "moving_arm_wm_validation")
        ]
    else:
        provenance = json.loads((args.evaluation / "evaluation.json").read_text())
        if mj.__version__ != provenance["mujoco_version"]:
            raise RuntimeError(
                "Replay the saved native evaluation using its original MuJoCo version"
            )
        base = ROOT / provenance["raw_path"] / "physical"
        paths = sorted(
            p
            for p in base.iterdir()
            if p.is_dir()
            and (args.cases is None or p.name.split("_")[-1] in args.cases)
        )
        if not paths:
            raise ValueError(f"No selected physical traces at {base}")
    all_g, all_e, all_f = [], [], []
    for path in paths:
        g, e, f = [], [], []

        def observe(d, c):
            exact, envelope = geometry.at(d)
            g.append(exact)
            e.append(envelope)
            f.append(c.normal.copy())

        plant = NativePlant(m)
        if args.teacher:
            sub = path / "substeps"
            q = np.load(sub / "qpos.npy")
            v = np.load(sub / "qvel.npy")
            ctrl = np.load(sub / "ctrl.npy")
            saved_load = np.load(sub / "wheel_load_N.npy")
            plant.reset(q[0], v[0])
            max_state_error = 0.0
            for k, command in enumerate(ctrl):
                plant.data.ctrl[:] = command
                mj.mj_step(m, plant.data)
                observe(plant.data, plant.meter.measure(plant.data))
                max_state_error = max(
                    max_state_error, float(np.max(np.abs(plant.data.qpos - q[k + 1])))
                )
            max_load_error = float(np.max(np.abs(f - saved_load)))
        else:
            q, v = [np.load(path / f"{k}.npy") for k in ("qpos", "qvel")]
            actions = np.load(path / "action_clipped.npy")
            steps = np.load(path / "substep_count.npy")
            plant.reset(q[0], v[0])
            max_state_error = 0.0
            for k, (action, n) in enumerate(zip(actions, steps, strict=True)):
                result = plant.step(action, on_substep=observe)
                if result["physics_steps"] != n:
                    raise RuntimeError(
                        f"Replay substep count differs: {path} at frame {k}"
                    )
                max_state_error = max(
                    max_state_error, float(np.max(np.abs(plant.data.qpos - q[k + 1])))
                )
            max_load_error = None
        if max_state_error > 1.0e-7 or (
            max_load_error is not None and max_load_error > 1.0e-4
        ):
            raise RuntimeError(
                f"Physical replay diverged at {path}: {max_state_error}, {max_load_error}"
            )
        g, e, f = map(np.asarray, (g, e, f))
        entries.append(
            dict(
                episode=path.name,
                steps=len(f),
                qpos_replay_max_abs=max_state_error,
                load_replay_max_abs_n=max_load_error,
                mixed_support_substeps=int(((f >= 1).any(1) & ~(f >= 1).all(1)).sum()),
                actual_loss_step=first_unload((f >= 1).all(1)),
                mesh_loss_tick_20ms=first_unload((g[9::10] <= 0).all(1), 5),
                mesh_gap_loss_step=first_unload((g <= 0).all(1)),
                revolved_gap_loss_step=first_unload((e <= 0).all(1)),
            )
        )
        all_g.append(g)
        all_e.append(e)
        all_f.append(f)
    metrics = summary(*[np.concatenate(x) for x in (all_g, all_e, all_f)])
    result = dict(
        mujoco=mj.__version__,
        source=str(args.teacher or args.evaluation),
        substep="Solved mj_step geometry transforms and forces from the same interval start",
        dt_s=float(m.opt.timestep),
        threshold_n=1.0,
        loss_consecutive_substeps=50,
        quantile_probabilities=[0, 0.05, 0.50, 0.95, 1],
        wheel_meshes=geometry.info,
        floor_margin_m=geometry.floor_margin,
        selected_episodes=entries,
        metrics=metrics,
    )
    args.output.parent.mkdir(exist_ok=True, parents=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
