"""Read the pinned H32 objective on the actual draw without stepping an optimizer."""

from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import numpy as np
import torch
from supermimic.learners import policy_learner
from learning.b0.contact_replay_draw import LaneAgeIndex
from learning.b0.contact_reward import reward_terms
from learning.b0.physics import ActionMap


def rng_state():
    return dict(cpu=torch.get_rng_state(), gpu=torch.cuda.get_rng_state(), numpy=np.random.get_state())


def restore_rng(state):
    torch.set_rng_state(state["cpu"].cpu())
    torch.cuda.set_rng_state(state["gpu"].cpu())
    np.random.set_state(state["numpy"])


@contextmanager
def fork_rng():
    state = rng_state()
    try:
        yield
    finally:
        restore_rng(state)


def array(value):
    return value.detach().cpu().numpy().copy()


@contextmanager
def observed_draws(run):
    """Record the ordered indices returned by the original offline and online samplers."""
    results = {}
    scope = ["actor"]
    pool = run.registered_wm
    old_draw = pool.draw
    old_lane_draw = LaneAgeIndex.draw

    def draw(h, index, count, replay=None):
        scope[0] = f"wm_{index:03}_h{h}"
        try:
            return old_draw(h, index, count, replay)
        finally:
            scope[0] = "actor"

    def draw_lanes(index, count):
        result = old_lane_draw(index, count)
        if result is not None:
            results[scope[0] + "_online"] = array(result)
        return result

    def observe_pool(name, original):
        def sample(count):
            start, lane = original(count)
            results[scope[0]+"_"+name] = array(torch.stack((start,lane), 1))
            return start, lane
        return sample

    with ExitStack() as stack:
        stack.enter_context(patch.object(pool, "draw", draw))
        stack.enter_context(patch.object(LaneAgeIndex, "draw", draw_lanes))
        for (name, _h), source in pool.pools.items():
            stack.enter_context(patch.object(source, "sample_indices", observe_pool(name, source.sample_indices)))
        yield results


class _ReadOnlyComplete(Exception):
    pass


def checked_first_batch(run):
    """Predict the real draw at u1. The pinned WM learner consumes no RNG during optimization."""
    with fork_rng(), observed_draws(run) as draws:
        before = len(run.registered_wm.rows)
        try:
            for index, h in enumerate([7] * run.seven_batches + [1, 1]):
                run.registered_wm.draw(h, index, run.b, run.replay)
            first = run.policy.wm_env.sample_initial_states()
            noise_rng = rng_state()
        finally:
            del run.registered_wm.rows[before:]
    return first, draws, noise_rng


def assert_draws(left, right):
    if left.keys() != right.keys():
        raise ValueError(f"Draw group mismatch: {left.keys() ^ right.keys()}")
    for key in left:
        np.testing.assert_array_equal(left[key], right[key], err_msg=key)


def objective_probe(run, starts, noise_rng, npz):
    """Invoke the actual policy _train_batch, stopping inside _optimize_step before it mutates anything."""
    policy = run.policy
    env = policy.wm_env
    mapping = ActionMap(run.model)
    result, data = {}, {}
    first, reward_values, survivals, term_values, aux_values = [], [], [], [], []
    physical = starts["state"].detach().clone().requires_grad_(True)
    official_ports, physical_map = [], []
    original_unpack, original_step, original_boot = env._unpack_initial_states, env.step, policy._bootstrap
    term_sums = {}
    survival = None
    before_rng = rng_state()
    modules = [run.actor, run.dyn, run.rep, run.critic]
    before_values = [[(key, v.detach().clone()) for key,v in module.state_dict().items()] for module in modules]
    flags = [(m, m.training) for root in modules for m in root.modules()]
    requires = [(p, p.requires_grad) for root in modules for p in root.parameters()]

    def unpack(batch):
        # The training graph treats replay states as constants. Only this separate
        # probe attaches a physical-input leaf, retaining exactly the same values.
        detached = original_unpack(batch)
        live = (run.rep.extract_aux_state(physical), run.rep.represent(physical))
        # Use exact official (detached) numeric values for the rollout. Evaluate
        # the external q/v-to-representation VJP separately at the same q/v.
        for ref,value in zip(detached,live,strict=True):
            official_ports.append(ref.detach().requires_grad_(True))
            physical_map.append(value)
        result["independent_input_map_max_abs_difference"]=[float((a.detach()-b.detach()).abs().max())
                                                            for a,b in zip(detached,live,strict=True)]
        return tuple(official_ports)

    def observed_step(action):
        nonlocal survival
        prev, target = env.last_actions, env._ref_body_state
        obs, reward, done, info = original_step(action)
        if not first:
            first.append(action)
            survival = torch.ones_like(reward)
        terms = reward_terms(run.rep, env.rep_state, env.aux_state, action, prev, target,
                             coordinates=run.rep.reward_coordinates)
        # Extra decomposition needs values only and must not retain extra backward graphs.
        weight = (policy.cfg.gamma ** len(reward_values)) * survival
        for key, value in terms.items():
            term_sums[key] = term_sums.get(key, 0.) + weight.detach()*value.detach()
            if not reward_values:
                data["instant_"+key] = array(value)
        reward_values.append(reward.detach())
        survivals.append(survival)
        term_values.append(done.detach())
        aux_values.append(run.actor.auxiliary_loss().detach())
        survival = survival * (1.-done.detach())
        return obs, reward, done, info

    def bootstrap(obs, alive, done):
        value = original_boot(obs, alive, done)
        data["terminal_critic_contribution"] = array(value)
        return value

    def stop(optimizers, loss, params, max_norm, clip_value):
        # autograd.grad does not write to .grad, change optimizer state or step any module.
        derivative = torch.autograd.grad(-loss, [first[0], *official_ports, *policy.actor_params], allow_unused=True)
        ga=derivative[0]
        gs=torch.autograd.grad(physical_map,physical,grad_outputs=derivative[1:3])[0]
        if ga is None or gs is None:
            raise RuntimeError("Missing physical-state or first-action H32 path")
        n = len(physical)
        data["first_action_canonical"] = array(first[0])
        data["first_command_physical"] = data["first_action_canonical"] * mapping.scale + mapping.offset
        data["dobjective_dphysical_action"] = array(ga*n) / mapping.scale
        data["dobjective_dphysical_state"] = array(gs*n)
        data["start_state"] = array(physical)
        for k in ("episode","motion_time","prev_action","history","draw_phase","draw_mode","sim_ctx","terminated"):
            data["start_"+k] = array(starts[k])
        data["reward"] = array(torch.stack(reward_values))
        data["softdone"] = array(torch.stack(term_values))
        data["survival"] = array(torch.stack(survivals))
        data["auxiliary_cost_sum"] = array(sum(aux_values))
        for k, value in term_sums.items():
            data["discounted_"+k] = array(value)
        actor_grads = [p.detach() for p in derivative[3:] if p is not None]
        actor_finite = bool(all(torch.isfinite(p).all().item() for p in actor_grads))
        actor_norm = float(sum(p.double().square().sum() for p in actor_grads).sqrt())
        data["objective_from_components"] = (sum(array(s)*policy.cfg.gamma**i * array(v)
            for i,(s,v) in enumerate(zip(survivals, reward_values, strict=True)))
            + data["terminal_critic_contribution"] - data["auxiliary_cost_sum"])
        def avg(x):
            val = float(np.mean(x, dtype=np.float64))
            return val if np.isfinite(val) else None
        nonfinite = {k:int((~np.isfinite(x)).sum()) for k,x in data.items() if not np.isfinite(x).all()}
        obj = float(-loss.detach())
        result.update(horizon=len(reward_values), batch=n, objective_mean=obj if np.isfinite(obj) else None,
            component_reconstruction_mean=avg(data["objective_from_components"]),
            mean_immediate_components={k[8:]:avg(v) for k,v in data.items() if k.startswith("instant_")},
            mean_discounted_components={k[11:]:avg(v) for k,v in data.items() if k.startswith("discounted_")},
            terminal_critic_mean=avg(data["terminal_critic_contribution"]),
            first_physical_action_channel_max=np.nan_to_num(abs(data["dobjective_dphysical_action"])).max(0).tolist(),
            actor_preclip_grad_l2=actor_norm if np.isfinite(actor_norm) else None,
            actor_grad_nonfinite=not actor_finite, nonfinite=nonfinite,
            finite=bool(actor_finite and np.isfinite(obj) and not nonfinite),
            action_units="per rad / m (wheel angular-velocity channel per rad/s); state derivatives in 63 recorded physical coordinates",
            objective_definition="mean discounted survival-weighted tracking plus terminal Critic minus auxiliary",
            state_vjp="physical replay state perturbed at fixed replay history, prev_action, reference and RNG",
            raw=str(npz), optimizer_steps=0)
        np.savez_compressed(npz, **data)
        raise _ReadOnlyComplete()

    try:
        with fork_rng(), ExitStack() as stack:
            restore_rng(noise_rng)
            run.actor.train()
            run.dyn.eval().requires_grad_(False)
            run.rep.eval().requires_grad_(False)
            stack.enter_context(patch.object(env, "_unpack_initial_states", unpack))
            stack.enter_context(patch.object(env, "step", observed_step))
            stack.enter_context(patch.object(policy, "_bootstrap", bootstrap))
            stack.enter_context(patch.object(policy_learner, "_optimize_step", stop))
            try:
                policy._train_batch(starts)
            except _ReadOnlyComplete:
                pass
    finally:
        for m, flag in flags:
            m.training = flag
        for p, flag in requires:
            p.requires_grad_(flag)
    after_rng = rng_state()
    rng_equal = (torch.equal(before_rng["cpu"],after_rng["cpu"]) and torch.equal(before_rng["gpu"],after_rng["gpu"])
                 and all(np.array_equal(a,b) for a,b in zip(before_rng["numpy"],after_rng["numpy"],strict=True)))
    equal_state = all(torch.equal(module.state_dict()[key],value) for module,old in zip(modules,before_values,strict=True)
                      for key,value in old)
    result.update(training_rng_unchanged=rng_equal, actor_critic_rep_wm_state_unchanged=equal_state)
    if not (equal_state and rng_equal):
        raise RuntimeError("Read-only H32 probe changed parameters, buffers, or training RNG")
    if result.get("horizon") != 32:
        raise RuntimeError("Incomplete read-only official H32")
    return result
