"""Measure the pinned GenCoord loss on independent, recorded action sequences."""
from pathlib import Path

import numpy as np
import torch
from supermimic.learners.wm_learner import WorldModelLearner

from learning.b0.contact_model import ContactWorldModelCfg
from learning.b0.contact_replay import MODES
from learning.b0.contact_warp import PHASES
from learning.b0.physics import WHEELS
from scripts.b0.fit_contact_model import prediction_errors
from scripts.b0.h32_fit_recovery_wm import csv_out
from scripts.b0.h32_recovery import write


UNITS = dict(root_pos="m", root_ori="sqrt(0.5) times rotation matrix entries; nominal in rad",
             joint_pos="rad", joint_vel="rad/s", finger_pos="m", finger_vel="m/s",
             door_angle="rad", door_speed="rad/s")


def strata(episodes, details, horizon, cap):
    """Select from identical lane-local valid windows for every predictor."""
    lanes, times, modes, phases = [], [], [], []
    for lane, (ep, meta) in enumerate(zip(episodes, details, strict=True)):
        starts = ep.starts(horizon)
        lanes.extend([lane] * len(starts))
        times.extend(starts)
        modes.extend(ep.modes[starts])
        phases.extend(meta["phase"][starts])
    lanes = np.asarray(lanes, dtype=int)
    times = np.asarray(times, dtype=int)
    modes = np.asarray(modes, dtype=str)
    phases = np.asarray(phases, dtype=int)
    masks = [("all", "all", np.ones(len(lanes), dtype=bool))]
    masks += [("contact_mode", mode, modes == mode) for mode in (*MODES, "recontact")]
    masks += [("reference_phase", phase, phases == phase_id) for phase_id, phase in enumerate(PHASES)]
    selected = []
    for kind, name, mask in masks:
        ids = np.flatnonzero(mask)
        count, lane_count = len(ids), len(np.unique(lanes[ids]))
        if len(ids) > cap:
            ids = np.random.default_rng(301).choice(ids, cap, replace=False)
        selected.append((dict(stratum=kind, label=name, available=count, available_lanes=lane_count,
                              scored=len(ids), scored_lanes=len(np.unique(lanes[ids]))), ids))
    return lanes, times, selected


@torch.no_grad()
def score_recorded_states(rep, dyn, model, episodes, details, out: Path, cap):
    if not episodes or any(e.split != "validation" for e in episodes):
        raise ValueError("State scoring requires validation lanes")
    device = episodes[0].state.device
    cfg = ContactWorldModelCfg()
    learner = WorldModelLearner(dyn, rep, cfg, str(device))
    wheel = torch.tensor([31 + model.joint(name).dofadr.item() for name in WHEELS], device=device)
    first = episodes[0].state[:1]
    blocks = rep.loss_blocks(rep.represent(first), rep.extract_aux_state(first))
    spec = {name: dict(width=values.shape[-1], unit=UNITS[name],
                       nominal_error=getattr(cfg, rep.LOSS_WEIGHT_CONFIG[name]))
            for name, values in blocks.items()}
    widths = first.new_tensor([v["width"] for v in spec.values()])
    weights = first.new_tensor([learner.loss_group_weights[name] for name in spec])
    loss_rows, metric_rows = [], []
    for side in ("pull", "push"):
        source = [(ep, meta) for ep, meta in zip(episodes, details, strict=True) if ep.side == side]
        side_eps = [ep for ep, _ in source]
        side_meta = [meta for _, meta in source]
        offsets = np.cumsum([0] + [len(e.state) for e in side_eps])[:-1]
        if side_eps:
            states = torch.cat([e.state for e in side_eps])
            actions = torch.cat([torch.cat([e.action, e.action[-1:]]) for e in side_eps])
            context = torch.stack([e.context for e in side_eps])
        for h in (1, 7, 8, 32):
            lanes, times, selections = strata(side_eps, side_meta, h, cap)
            union = np.unique(np.concatenate([ids for _, ids in selections]))
            result = {}
            for start in range(0, len(union), 128):
                ids = union[start:start + 128]
                ix = torch.as_tensor(offsets[lanes[ids]] + times[ids], device=device)
                ctx = context[torch.as_tensor(lanes[ids], device=device)]
                real = states[ix[:, None] + torch.arange(h + 1, device=device)]
                real_rep = rep.represent(real)
                real_aux = rep.extract_aux_state(real)
                true_rep, true_aux = real_rep[:, 1:], real_aux[:, 1:]
                target_blocks = rep.loss_blocks(true_rep, true_aux)
                init = real_aux[:, 0], real_rep[:, 0]
                moving = init
                zero = init[1].new_zeros(len(ix), rep.prediction_dim)
                ma, mr = [], []
                for _ in range(h):
                    moving = rep.apply_prediction(*moving, zero, rep.dt)
                    ma.append(moving[0])
                    mr.append(moving[1])
                # _rollout discards the last stored action. Lane-final padding
                # here occupies only that unused slot; all h applied actions are real.
                aa = actions[ix[:, None] + torch.arange(h + 1, device=device)]
                model_rep, model_aux = learner._rollout(init[1], aa, init[0], ctx)
                for predictor, pred_rep, pred_aux in (
                    ("wm", model_rep, model_aux),
                    ("hold", init[1][:, None].expand(-1, h, -1), init[0][:, None].expand(-1, h, -1)),
                    ("constant_velocity", torch.stack(mr, 1), torch.stack(ma, 1)),
                ):
                    pred_blocks = rep.loss_blocks(pred_rep, pred_aux)
                    group_mse = torch.stack([(pred_blocks[name] - target_blocks[name]).square().mean(dim=(1, 2))
                                             for name in spec], dim=-1)
                    state_loss = (group_mse * weights * widths).sum(-1) / widths.sum()
                    official, official_groups = learner._compute_losses(pred_rep, pred_aux, true_rep, true_aux)
                    torch.testing.assert_close(state_loss.mean(), official, rtol=2e-5, atol=1e-7, equal_nan=True)
                    torch.testing.assert_close(group_mse.mean(0), official_groups, rtol=2e-5, atol=1e-7, equal_nan=True)
                    physical = prediction_errors(rep, pred_aux[:, -1], pred_rep[:, -1], real[:, -1], wheel)
                    measurements = dict(state_loss=state_loss, **dict(zip(spec, group_mse.unbind(-1), strict=True)),
                                        **physical)
                    for name, vals in measurements.items():
                        result.setdefault((predictor, name), []).append(vals.cpu().numpy())
            result = {key: np.concatenate(pieces) for key, pieces in result.items()}
            for info, ids in selections:
                idx = np.searchsorted(union, ids)
                common = dict(side=side, h=h, stored_frames=h+1, **info)
                for predictor in ("wm", "hold", "constant_velocity"):
                    loss = dict(**common, predictor=predictor)
                    for name in ("state_loss", *spec):
                        values = result.get((predictor, name), np.empty(0))[idx]
                        # Report a nonfinite as such; never discard it from the mean loss.
                        loss[name] = float(values.mean(dtype=np.float64)) if len(values) and np.isfinite(values).all() else None
                        if name == "state_loss":
                            loss["nonfinite_windows"] = int((~np.isfinite(values)).sum())
                    loss_rows.append(loss)
                    for (label, metric), entire in result.items():
                        if label != predictor or metric == "state_loss" or metric in spec:
                            continue
                        values = entire[idx]
                        finite = values[np.isfinite(values)].astype(np.float64)
                        metric_rows.append(dict(**common, predictor=predictor, metric=metric,
                            nonfinite=len(values)-len(finite), p95=np.percentile(finite, 95) if len(finite) else None,
                            rmse=np.sqrt(np.mean(finite**2)) if len(finite) else None, maximum=finite.max() if len(finite) else None))
    csv_out(out / "state_loss.csv", loss_rows)
    csv_out(out / "errors.csv", metric_rows)
    write(out / "state_loss_definition.json", dict(source="abc124c WorldModelLearner._compute_losses and _rollout",
        groups=spec, state_loss="mean squared error over h successor steps and all channels weighted by 1/nominal_error^2; then mean over sampled windows",
        group_columns="unweighted group MSE over channels and all h successors", horizons=[1,7,8,32],
        window="Within-lane valid 20 ms recorded clipped commands. Complete terminal interval included; no crossing reset or cohort boundary.",
        sampling="Each side/h/stratum independently capped without replacement, numpy seed 301. All, physical start mode, and reference start phase overlap; do not add their counts.",
        physical_columns="Endpoint errors at successor h. RMSE/P95/max over finite windows; nonfinite windows counted.",
        interpretation="Recorded-action open loop on the transferred robot and door; dataset, channels and scales differ from G1."))
