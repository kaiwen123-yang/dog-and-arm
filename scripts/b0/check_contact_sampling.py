"""Audit return RSI, replay Ratio and tail goals on a recorded physical contact cohort."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
from supermimic.runners.reset_sampling import ReturnSampler, ReturnSamplerCfg

from learning.b0.contact_model import ContactRepresentation, contact_state
from learning.b0.contact_policy import DoorMotions
from learning.b0.contact_sampling import ContactUpdateSchedule, EligibleReturnSampler, SamplerReference
from learning.b0.contact_reward import reward_terms
from learning.b0.model import full_state
from learning.b0.physics import make_model


@torch.no_grad()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--actual-config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.actual_config.read_text())["cfg"]
    paths = [Path(cfg["reference_directory"]) / name for name in cfg["references"]]
    rep = ContactRepresentation(make_model(), "cpu")
    rep.reward_coordinates = "fixed_effort"
    bank = DoorMotions(paths, rep, "cpu")
    physical_ref = SamplerReference(paths,bank,"cpu")
    eligible = []
    for path, start, end in zip(paths, bank.motion_starts, bank.motion_ends, strict=True):
        n = int(end - start - 1)
        phase = np.load(path/"substeps/phase.npy")[:10*n:10]
        use = np.isin(np.asarray(bank.metas[path.name]["phases"])[phase], cfg["rsi_phases"])
        frames = np.flatnonzero(use & (np.arange(n) >= 11) & (np.arange(n) < n-33-cfg["cohort_steps"]))
        eligible.append(torch.as_tensor(frames) + start)

    def load(name):
        return torch.from_numpy(np.load(args.cohort/(name + ".npy")))

    frames, valid, tick = load("frame"), load("valid"), load("first_fail_substep")
    terminated = tick > 0
    q, v, action, previous = (load(key) for key in ("next_qpos", "next_qvel", "clipped", "prev_action"))
    rows = []
    subq, subv = load("sub_qpos_post"), load("sub_qvel_post")
    max_change = 0.
    partial_count = 0
    for i in range(len(frames)):
        state = contact_state(q[i], v[i])
        r = rep.represent(state)
        reward = rep.compute_wm_reward_from_reference(r, state[:, :7], rep.joint_state(r),
                    action[i], previous[i], *bank.body_state(frames[i]+1))
        stop = (tick[i].long()-1).clamp(min=0)
        lanes = torch.arange(len(stop))
        stop_q, stop_v = subq[i,lanes,stop], subv[i,lanes,stop]
        partial = valid[i] & terminated[i] & (tick[i] < 10)
        corrected = physical_ref.rewards(rep,reward,frames[i],valid[i],tick[i],stop_q,stop_v,
                                         action[i],previous[i])
        if partial.any():
            ids = lanes[partial]
            clip = torch.searchsorted(bank.motion_ends,frames[i,ids],right=True)
            qr,vr = [],[]
            for j,k in zip(ids.tolist(),clip.tolist(),strict=True):
                at = int((frames[i,j]-bank.motion_starts[k])*10+tick[i,j])
                for values,key in ((qr,"qpos"),(vr,"qvel")):
                    values.append(np.load(paths[k]/"substeps"/(key+".npy"),mmap_mode="r")[at])
            qr,vr = [torch.as_tensor(np.stack(x),dtype=torch.float32) for x in (qr,vr)]
            ref = full_state(qr,vr)
            target = rep.fk(qr[:,:3],qr[:,3:7],qr[:,7:31],ref[:,31:34],ref[:,34:37],vr[:,6:30])
            observed = contact_state(stop_q[ids],stop_v[ids])
            terms = reward_terms(rep,rep.represent(observed),observed[:,:7],action[i,ids],previous[i,ids],
                                 target,coordinates="fixed_effort",dt=tick[i,ids].float()*.002)
            torch.testing.assert_close(corrected[ids],sum(terms.values()),rtol=2e-5,atol=2e-6)
            max_change = max(max_change,float((corrected[ids] - reward[ids]).abs().max()))
            partial_count += len(ids)
        rows.append(dict(motion_time=frames[i], valid=valid[i], terminated=terminated[i], reward=corrected))
    worlds = valid.shape[1]

    def sampler(n):
        return EligibleReturnSampler(bank, eligible, n, cfg["policy_dt"], .1, "cpu")

    full, masked = sampler(worlds), sampler(worlds)
    full.record_cohort(rows)
    masked.record_cohort([dict(row, reward=row["reward"].masked_fill(~row["valid"], torch.nan)) for row in rows])
    for key in ("value", "count", "effort", "probabilities"):
        torch.testing.assert_close(getattr(full, key), getattr(masked, key), rtol=0, atol=0)

    # For lanes valid over the whole cohort the adapted update must equal the
    # unmodified pin, including time-out bootstrap at the administrative cut.
    lanes = valid.all(0)
    n = int(lanes.sum())
    if not n:
        raise ValueError("Choose a recorded cohort with complete lanes for the fixed-source comparison")
    dense = sampler(n)
    official = ReturnSampler(ReturnSamplerCfg(), full.bin_count, full.frame_count, n, .1, "cpu")
    dense.record_cohort([{k: field[lanes] for k, field in row.items()} for row in rows])
    for i, row in enumerate(rows):
        term = row["terminated"][lanes]
        timeout = torch.full_like(term, i == len(rows)-1) & ~term
        official.record(frames[i,lanes], row["reward"][lanes], term, torch.zeros_like(term), timeout)
    for key in ("value", "count", "effort"):
        torch.testing.assert_close(getattr(dense, key), getattr(official, key), rtol=0, atol=0)

    torch.manual_seed(301)
    starts = full.sample(16384)
    if not torch.isin(starts, full.eligible).all():
        raise ValueError("Invalid return-sampled reset")
    ends = bank.motion_ends - 1
    zero_wm, zero_actor = bank.goals(rep, ends, bank.qpos[ends,:7])
    bank.reference_tail = "official_clip_last"
    wm, actor = bank.goals(rep, ends, bank.qpos[ends,:7])
    for field, widths in ((wm, (48,3,6)), (actor, (48,6))):
        for block, width in zip(field.split([10*w for w in widths], -1), widths, strict=True):
            slots = block.unflatten(-1,(10,width))
            torch.testing.assert_close(slots, slots[:,:1].expand_as(slots), rtol=0, atol=0)
    if torch.equal(actor, zero_actor) or torch.equal(wm, zero_wm):
        raise ValueError("At the real clip ends zero-tail control did not differ")
    # Check the uninterrupted all-valid horizon against a serialized partial buffer.
    split = 13
    prefix = sampler(n)
    for i in range(split):
        prefix.valid[:, prefix._step] = True
        zeros = torch.zeros(n, dtype=torch.bool)
        prefix.record(frames[i,lanes], rows[i]["reward"][lanes], zeros, zeros, zeros)
    restored = sampler(n)
    restored.load_state_dict(prefix.state_dict())
    restored.record_cohort([{k: field[lanes] for k, field in row.items()} for row in rows[split:]])
    for key in ("value", "count", "effort"):
        torch.testing.assert_close(getattr(dense, key), getattr(restored, key), rtol=0, atol=0)
    # Eligible training starts leave H32 room, so clip_end is absent from
    # these cohorts. Check that boundary separately at a real clip's end.
    boundary = sampler(3)
    boundary.value.copy_(torch.linspace(0, 1, boundary.bin_count))
    probe_frames = torch.tensor([frames[0,0], bank.motion_ends[0]-2, frames[0,0]])
    probe_reward = rows[0]["reward"][valid[0]][0].expand(3)
    boundary.record_cohort([dict(motion_time=probe_frames, valid=torch.ones(3,dtype=torch.bool),
                               terminated=torch.tensor([True,False,False]),reward=probe_reward)])
    bootstrap = torch.stack((torch.tensor(0.),boundary.value.mean(),
                             boundary.value[boundary._bins(probe_frames[2] + 1)]))
    torch.testing.assert_close(boundary._returns()[:,0],probe_reward+boundary.cfg.gamma*bootstrap)
    run = SimpleNamespace(cfg=cfg, b=cfg["wm_batch"], seven_batches=8, h32_teacher_batches=0)
    schedule = ContactUpdateSchedule(run)
    ticks = valid.sum(1).tolist()
    schedule.add_cohort(0, ticks)
    continued = ContactUpdateSchedule(run)
    continued.load_state_dict(schedule.state_dict())
    duplicate = ContactUpdateSchedule(run)
    duplicate.add_cohort(0, ticks)
    for item in (continued, duplicate):
        item.pending -= 1
        item.add_cohort(sum(ticks), ticks)
    if continued.state_dict() != duplicate.state_dict():
        raise ValueError("Ratio clock/pending repeats failed checkpoint continuation")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x") as out:
        json.dump(dict(cohort=str(args.cohort),actual_config=str(args.actual_config),seed=301,
              frame_count=full.frame_count,bin_count=full.bin_count,eligible_by_motion=[len(x) for x in eligible],
              valid_intervals=int(valid.sum()),attempted_intervals=valid.numel(),
              sampler_reward_coordinates="fixed_effort",physical_partial_terminals=partial_count,
              max_partial_terminal_difference_from_20ms_diagnostic_reward=max_change,
              complete_lanes_matching_pinned_return=n,invalid_reward_nan_exclusion_checked=True,
              serialized_partial_return_buffer_verified_at=split,
              clip_end_mean_value_terminal_zero_timeout_next_value_boundary_check=True,
              ratio_clock_and_pending_repeats_resume_check=True,
              measured_bins=int((full.count>0).sum()),per_bin_episode_samples=int(full.count.sum()),
              draws_per_motion=torch.bincount(torch.searchsorted(bank.motion_ends, starts, right=True),
                                              minlength=len(paths)).tolist(),
              tail_clips_checked=len(paths),tail_policy_steps_extended=0,
              total_window_positions=schedule.positions,due_updates=schedule.pending,
              replay_ratio=cfg["replay_ratio"],cumulative_clock=schedule.ratio._prev),out,indent=2)
        out.write("\n")


if __name__ == "__main__":
    main()
