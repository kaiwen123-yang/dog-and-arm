"""Measure physical action coverage and validate the B0-03 arm/jaw unit transfer on CPU."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import DoorMotions, build_actor
from learning.b0.contact_training import rescale_standard_arm_jaw
from learning.b0.model import RobotRepresentation
from learning.b0.physics import ActionMap, FINGERS, make_model
from scripts.b0.calibrate_contact_actor import REFS, observations

SCORED_RUNS = ("contact_u0_native33_r1", "contact_u0_warp316_r1",
               "contact_s0_tracking_u1000_native33_r2", "contact_s0_tracking_u1000_warp_r2")


def measure_physics(workspace, mapping):
    results = {}
    for run in SCORED_RUNS:
        raw, clipped = [], []
        for path in sorted((workspace / "results/b0" / run).glob("*/*/nominal/result.json")):
            case = json.loads(path.read_text())
            root = workspace / "results/raw_large/b0" / run / case["side"] / case["segment"] / "nominal"
            actual = np.load(root / "clipped_action.npy")
            before = np.load(root / "raw_action.npy")
            np.testing.assert_equal(len(actual), case["policy_calls"])
            np.testing.assert_array_equal(actual, np.clip(before, -1., 1.))
            raw.append(before)
            clipped.append(actual)
        if len(clipped) != 10:
            raise ValueError(f"{run}: expected ten nominal cases, found {len(clipped)}")
        raw, clipped = np.concatenate(raw), np.concatenate(clipped)
        physical = mapping.offset + clipped * mapping.scale
        results[run] = dict(cases=10, policy_calls=len(raw),
                            clipping_count=np.sum(raw != clipped, axis=0).tolist(),
                            physical_min=physical.min(axis=0).tolist(), physical_max=physical.max(axis=0).tolist())
    return results


@torch.no_grad()
def measure_transfer(model, rep, workspace, mapping):
    ckpt = Path("results/b0/free_s0_cloud_servo_r2/checkpoint_001000.pt")
    anchor = torch.load(workspace / ckpt, weights_only=False, map_location="cpu")
    actor, _ = build_actor(rep, anchor["cfg"], model, "cpu")
    actor.load_state_dict(anchor["actor"])
    actor.eval()
    refroot = workspace / "results/raw_large/b0/contact_held_r1"
    refs = [refroot / name for name in REFS]
    bank = DoorMotions(refs, rep, "cpu")
    goals, hist, _, _, _ = observations(refroot, refs, bank, rep, "cpu", False)
    def raw_and_clipped():
        chunks = []
        for g, h in zip(goals.split(256), hist.split(256), strict=True):
            obs = build_actor_obs_td({"motion": g}, h)
            raw = actor.raw(obs)
            torch.testing.assert_close(actor(obs), raw.clamp(-1., 1.), rtol=0., atol=0.)
            chunks.append(raw)
        return torch.cat(chunks)
    before = raw_and_clipped()
    exploration = actor.standard_action.clone()
    rescale_standard_arm_jaw(actor, 32.)
    after = raw_and_clipped()
    torch.testing.assert_close(after, before, rtol=0., atol=1e-6)
    reload_actor, _ = build_actor(rep, anchor["cfg"], model, "cpu")
    reload_actor.load_state_dict(actor.state_dict())
    reload_actor.eval()
    actor = reload_actor
    torch.testing.assert_close(raw_and_clipped(), after, rtol=0., atol=0.)
    return dict(checkpoint=str(ckpt), actual_class=type(actor).__name__, inherited_seed=anchor["seed"],
                inherited_updates=anchor["updates"], inherited_transitions=anchor["collected"],
                reference_names=list(REFS), real_complete_history_frames=len(hist), gain=32.,
                raw_max_abs_diff=(after-before).abs().max().item(),
                clipped_max_abs_diff=(after.clamp(-1,1)-before.clamp(-1,1)).abs().max().item(),
                strict_reload_max_abs_diff=0.,
                source_standard_action=exploration.tolist(),
                rescaled_standard_action=actor.standard_action.tolist(),
                collection_noise=anchor["cfg"]["collection_noise"],
                physical_noise_sigma=(exploration.numpy()*mapping.scale*anchor["cfg"]["collection_noise"]).tolist())



def measure_cohort(path, model, mapping, sat_fraction):
    def read(name):
        return np.load(path / (name + ".npy"), mmap_mode="r")
    active = read("active")
    raw, clipped = read("raw")[active], read("clipped")[active]
    np.testing.assert_array_equal(clipped, raw.clip(-1., 1.))
    targets = clipped * mapping.scale + mapping.offset
    target_error = abs(targets - read("physical_target")[active])
    np.testing.assert_allclose(target_error, 0., atol=3e-7, rtol=0.)
    first = read("first_fail_substep")[active]
    # Count real interactions through the first failure, inclusive. Warp also
    # integrates the rest of the held interval for fixed-dt WM supervision.
    keep = (first[:, None] == 0) | (np.arange(1, 11)[None, :] <= first[:, None])
    force = read("sub_actuator_force")[active][keep][:, mapping.actuator_ids]
    wheel_ids = mapping.actuator_ids[12:16]
    ctrl = read("sub_ctrl")[active][:, :, wheel_ids]
    wheel_error = abs(ctrl - targets[:, None, 12:16])[keep]
    np.testing.assert_allclose(wheel_error, 0., atol=5e-7, rtol=0.)
    return dict(path=str(path), active_policy_calls=int(active.sum()), valid_20ms=int(read("valid").sum()),
                substeps_through_first_failure=int(keep.sum()), clip_count=(raw!=clipped).sum(0).tolist(),
                target_min=targets.min(0).tolist(), target_max=targets.max(0).tolist(),
                wm_target_max_difference=float(target_error.max()), wheel_ctrl_max_difference=float(wheel_error.max()),
                saturation_fraction=sat_fraction,
                force_saturated_substeps=(abs(force) >= sat_fraction*model.actuator_forcerange[mapping.actuator_ids,1]).sum(0).tolist())

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-workspace", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cohorts", type=Path, nargs="+", help="Only measure the listed real online cohorts")
    args = parser.parse_args()
    workspace = args.asset_workspace
    model = make_model()
    mapping = ActionMap(model)
    if args.cohorts:
        from p6_scene import settings
        fraction = settings("mobile", 1)["sat_fraction"]
        out = dict(channel_order=mapping.names, cohorts=[measure_cohort(p, model, mapping, fraction) for p in args.cohorts])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")
        return
    anchor = measure_transfer(model, RobotRepresentation(model, "cpu"), workspace, mapping)
    home = model.key("home").qpos[mapping.q].copy()
    home[12:16] = 0.
    f1, f2 = [model.joint(n).qposadr.item() for n in FINGERS]
    home[-1] = model.key("home").qpos[f1] - model.key("home").qpos[f2]
    units = np.asarray(anchor["source_standard_action"])*mapping.scale
    expected_units = .25*model.actuator_forcerange[mapping.actuator_ids,1]/model.actuator_gainprm[mapping.actuator_ids,0]/mapping.finger_factor
    np.testing.assert_allclose(units, expected_units, rtol=1e-6)
    real, requested = [], []
    stats = []
    for name in REFS:
        root = workspace / "results/raw_large/b0/contact_held_r1" / name
        valid = np.load(root / "valid_full_interval.npy")
        complete = valid.sum()
        cmd = np.load(root / "physical_target.npy")[valid]
        action = np.load(root / "action_clipped.npy")[valid]
        raw = np.load(root / "teacher_requested_action.npy")[valid]
        np.testing.assert_allclose(action*mapping.scale + mapping.offset, cmd, rtol=0., atol=1.e-12)
        np.testing.assert_allclose(np.clip(raw,-1,1), action, rtol=0., atol=1.e-12)
        q = np.load(root / "qpos.npy")
        np.testing.assert_allclose(np.load(root / "opening_m.npy"), q[:,f1]-q[:,f2], atol=1.e-12)
        sat = np.load(root / "substeps/actuator_saturation.npy",mmap_mode="r")[:10*complete, mapping.actuator_ids]
        real.append(cmd)
        requested.append(raw)
        stats.append(dict(episode=name, full_20ms=int(complete), measured_substeps=len(sat),
                          saturation_substeps=sat.sum(axis=0).tolist()))
    real, requested = np.concatenate(real), np.concatenate(requested)
    chans = mapping.describe(model)
    for i, row in enumerate(chans):
        joint = model.joint(row["joint"])
        row.update(joint_range=joint.range.tolist(), home=float(home[i]),
                   command_range=[float(mapping.offset[i]-mapping.scale[i]), float(mapping.offset[i]+mapping.scale[i])],
                   raw_servo_multiplier=float(mapping.finger_factor[i]), network_unit=float(units[i]),
                   physical_exploration_sigma=anchor["physical_noise_sigma"][i],
                   train_teacher_range=[float(real[:,i].min()),float(real[:,i].max())],
                   train_max_abs_decoder_units=float(np.max(np.abs((real[:,i]-home[i])/units[i]))))
        row["train_teacher_clip_count"] = int((abs(requested[:,i])>1).sum())
    out = dict(anchor_transfer=anchor, channels=chans, teacher_complete_intervals=len(real),
               teacher_source="contact_held_r1 six nominal train episodes, full intervals only",
               teacher_episode_force_saturation=stats, physics_evaluations=measure_physics(workspace, mapping),
               second_finger_joint_range=model.joint(FINGERS[1]).range.tolist(),
               material="ActionMap full opening = positive finger position minus negative finger position. "
                        "Single positive finger servo target is half of logical opening. Both fingers are measured. "
                        "Motor commands include the existing per-substep qfrc_bias correction except for wheels. "
                        "Policy clip counts compare stored raw vs applied actions. Motor saturation counts use logged substeps in XML actuator order reordered to the 23 logical channels.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
