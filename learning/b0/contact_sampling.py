"""Pinned SuperMimic return RSI and replay scheduling on ragged contact cohorts."""
import numpy as np
import torch
from supermimic.runners.reset_sampling import ReturnSampler, ReturnSamplerCfg

from .contact_model import contact_state
from .model import full_state, tensor


class SamplerReference:
    """The real reference on its 2 ms clock, used only for partial physical terminals."""
    def __init__(self, paths, bank, device, clock=None):
        from .contact_clock import ContactClock
        self.clock = ContactClock(.002) if clock is None else clock
        q, v, starts = [], [], []
        offset = 0
        self.bank = bank
        for path, start, end in zip(paths, bank.motion_starts, bank.motion_ends, strict=True):
            n = 10 * int(end - start - 1) + 1
            q.append(np.load(path / "substeps/qpos.npy", mmap_mode="r")[:n])
            v.append(np.load(path / "substeps/qvel.npy", mmap_mode="r")[:n])
            if min(len(q[-1]), len(v[-1])) != n:
                raise ValueError(f"Incomplete 2 ms terminal scoring reference: {path}")
            starts.append(offset)
            offset += n
        self.starts = torch.as_tensor(starts, device=device)
        self.q = tensor(np.concatenate(q), device)
        self.v = tensor(np.concatenate(v), device)

    def rewards(self, rep, full_reward, frames, valid, fail_tick, stop_q, stop_v, action, previous):
        partial = valid & (fail_tick > 0) & (fail_tick < self.clock.policy_steps)
        if not partial.any():
            return full_reward
        clip = torch.searchsorted(self.bank.motion_ends, frames[partial], right=True)
        tick = fail_tick[partial].long()
        stride = self.clock.servo_stride
        query = self.starts[clip] + (frames[partial] - self.bank.motion_starts[clip]) * 10 + tick // stride
        q, v = self.q[query], self.v[query]
        if stride > 1:
            # The frozen reference is sampled every 2 ms. At intermediate endpoints
            # interpolate positions and velocities, using shortest-arc SLERP for the base.
            remainder = tick % stride
            other = query + (remainder > 0).long()
            fraction = remainder[:, None].to(q.dtype) / stride
            q0, q1 = q[:,3:7], self.q[other,3:7]
            dot = (q0*q1).sum(-1,keepdim=True)
            q1 = torch.where(dot < 0, -q1, q1)
            angle = dot.abs().clamp(max=1.).acos()
            den = angle.sin().clamp_min(1e-8)
            rot = torch.where(angle < 1e-4, q0.lerp(q1,fraction),
                              ((1-fraction)*angle).sin()/den*q0 + (fraction*angle).sin()/den*q1)
            q = q.lerp(self.q[other], fraction)
            q[:,3:7] = torch.where(remainder[:,None] > 0, torch.nn.functional.normalize(rot), q0)
            v = v.lerp(self.v[other], fraction)
        ref_state = full_state(q, v)
        target = rep.fk(q[:, :3], q[:, 3:7], q[:, 7:31], ref_state[:, 31:34], ref_state[:, 34:37], v[:, 6:30])
        state = contact_state(stop_q[partial], stop_v[partial])
        observed = rep.represent(state)
        measured = rep.compute_wm_reward_from_reference(observed, state[:, :7], rep.joint_state(observed),
                                                  action[partial], previous[partial], *target)
        score = full_reward.clone()
        score[partial] = measured * (tick / self.clock.policy_steps)
        return score


class EligibleReturnSampler(ReturnSampler):
    """Apply the pinned return update to measured intervals and condition resets on legal starts."""

    def __init__(self, bank, eligible, worlds, step_dt, max_step_reward, device):
        frames = int(bank.motion_ends[-1])
        bins = int(frames // (0.2 / step_dt)) + 1
        super().__init__(ReturnSamplerCfg(), bins, frames, worlds, max_step_reward, device)
        self.ends = bank.motion_ends
        self.eligible = torch.cat(eligible)
        # Fixed mjlab _sample_from_bin_probs maps bin -> [lo, hi) using total-2.
        # ReturnSampler._bins instead uses total; these maps are intentionally distinct.
        edges = torch.arange(bins + 1, device=device) * (frames - 2) // bins
        if torch.any(edges.diff() <= 0) or torch.any(self.eligible >= edges[-1]):
            raise ValueError("Contact clip/start lengths incompatible with fixed bin->frame map")
        self.draw_bins = torch.bucketize(self.eligible, edges[1:], right=True)
        self.draw_span = edges.diff()[self.draw_bins]
        self.probabilities = torch.full_like(self.value, 1 / bins)
        self.valid = torch.zeros_like(self._terminated)

    def sample(self, count):
        # Each proposed frame has mass P(bin)/original span. This is exact
        # conditioning on eligibility, even when clip/phase boundaries split bins.
        weights = self.probabilities[self.draw_bins] / self.draw_span
        return self.eligible[torch.multinomial(weights, count, replacement=True)]

    def record_cohort(self, rows):
        for i, row in enumerate(rows):
            frames, valid = row["motion_time"], row["valid"]
            clip = torch.searchsorted(self.ends, frames, right=True)
            clip_end = valid & (frames + 1 >= self.ends[clip] - 1)
            next_valid = rows[i + 1]["valid"] if i + 1 < len(rows) else torch.zeros_like(valid)
            # The local cohort cut is administrative. A measured physical
            # terminal on its final interval still has zero continuation.
            terminated = valid & row["terminated"] & ~clip_end
            timeout = valid & ~terminated & ~clip_end & ~next_valid
            self.valid[:, self._step] = valid
            distribution = self.record(frames, row["reward"], terminated, clip_end, timeout)
            if distribution is not None:
                self.probabilities = distribution

    def _update(self):
        # The fixed sampler expects an env to reset immediately after failure.
        # Our dead lanes stay allocated until the cohort boundary. Exclude them
        # before the original per-(lane, episode, bin) mean and sample count.
        if not self.valid.any():
            return
        returns = self._returns()
        done = self._dones().long()
        episode = done.cumsum(1) - done
        lanes = torch.arange(done.shape[0], device=done.device)[:, None]
        key = (lanes * self.cfg.horizon + episode) * self.bin_count + self._bins(self._frames)
        keys, reverse, visits = torch.unique(key[self.valid], return_inverse=True, return_counts=True)
        samples = torch.zeros(keys.numel(), device=done.device)
        samples.scatter_add_(0, reverse, returns[self.valid])
        samples /= visits
        bins = keys % self.bin_count
        new = torch.zeros_like(self.count).scatter_add_(0, bins, torch.ones_like(samples))
        total = torch.zeros_like(self.value).scatter_add_(0, bins, samples)
        self.count = self.count.clamp(max=self.cfg.memory) + new
        self.value = torch.where(new > 0, self.value + (total - new * self.value) / self.count, self.value)

    def _distribution(self):
        # Empty masked windows contain no measured policy feedback.
        return super()._distribution() if self.valid.any() else self.probabilities

    def state_dict(self):
        return {key: getattr(self, key) for key in (
            "value", "count", "effort", "_frames", "_rewards", "_terminated",
            "_clip_end", "_timed_out", "_step", "valid", "probabilities")}

    def load_state_dict(self, state):
        for key in self.state_dict():
            setattr(self, key, state[key])


class ContactUpdateSchedule:
    """Use the official Ratio clock, in complete replay insertions, at cohort boundaries."""

    def __init__(self, run):
        from supermimic.runners.supermimic_runner import Ratio
        # Count both online and offline positions in the joint WM update.
        self.positions = run.b * (2 * 2 + run.seven_batches * 8 + run.h32_teacher_batches * 33)
        if run.cfg.get("execution_recipe") == "official_flow_s0_v1":
            cfg = run.learners[7].cfg
            self.positions = cfg.batch_size * cfg.num_batches * cfg.horizon
        self.ratio = Ratio(run.cfg["replay_ratio"] / self.positions)
        self.pending = 0
        self.cohorts = 0

    def add_cohort(self, cumulative_before, valid_per_tick):
        self.cohorts += 1
        clock = cumulative_before
        for count in valid_per_tick:
            # One physical tick is zero-based in O1; count insertions before
            # that tick to reproduce its first-call rule and cumulative clock.
            if count:
                self.pending += self.ratio(clock)
                clock += count

    def state_dict(self):
        return dict(previous_clock=self.ratio._prev, pending=self.pending, cohorts=self.cohorts)

    def load_state_dict(self, state):
        self.ratio._prev = state["previous_clock"]
        self.pending = state["pending"]
        self.cohorts = state["cohorts"]
