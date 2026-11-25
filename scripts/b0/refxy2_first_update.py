"""Read-only observations of the first retained RefXY2 collection and optimizer call."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import patch
import hashlib
import json

import numpy as np
import torch


def array(t):
    return t.detach().contiguous().cpu().numpy().copy()


def digest(a):
    return hashlib.sha256(np.ascontiguousarray(a).view(np.uint8)).hexdigest()


def save(light, raw, name, values, metadata):
    light, raw = Path(light), Path(raw)
    raw.mkdir(parents=True, exist_ok=True)
    light.mkdir(parents=True, exist_ok=True)
    file = raw / (name + ".npz")
    np.savez_compressed(file, **values)
    meta = dict(metadata, arrays=str(file), array_metadata={
        k: dict(shape=list(v.shape), dtype=str(v.dtype), sha256=digest(v))
        for k, v in values.items()})
    (light / (name + ".json")).write_text(json.dumps(meta, indent=2, allow_nan=False) + "\n")


def stats(run):
    return {k:int(v.count.item()) for k,v in {
        "goal":run.actor.goal_normalizers["motion"], "proprio":run.actor.obs_normalizer,
        "wm_state":run.dyn.state_normalizer, "wm_action":run.dyn.action_normalizer}.items()}


@contextmanager
def first_collection(run, light, raw):
    data = {}
    before = stats(run)
    original_actor = run.actor.raw
    original_step = run.plant.step_contact

    def actor(obs):
        command = original_actor(obs)
        data.update(raw_before_noise=array(command), frame=array(run.lanes["frame"]),
                    noisy_history=array(obs["history"]), original_goal=array(obs["goal_motion"][..., :540]),
                    tail=array(obs["goal_motion"][..., 540:]), prefix=array(run.lanes["prefix"]))
        return command

    def step(command, *args, **kwargs):
        data["applied"] = array(command)
        data["physical"] = (data["applied"] * run.plant.mapping.scale + run.plant.mapping.offset)
        return original_step(command, *args, **kwargs)

    with patch.object(run.actor, "raw", actor), patch.object(run.plant, "step_contact", step):
        yield
    save(light, raw, "first_collection_observation", data,
         dict(statistics_before=before, statistics_after=stats(run), tick=run.replay.clock))


@contextmanager
def first_update(run, light, raw):
    data, checks = {}, []
    env = run.policy.wm_env
    weight = run.actor.encoders["motion"][0].weight
    adam, = [o for o in run.policy.actor_optimizers if weight in o.state]
    before = stats(run)
    data["weight_tail_before"] = array(weight[:, 540:])
    sample = env.sample_initial_states
    initial_receipt = run.replay.receipt
    run.replay.receipt = []

    def traced_sample():
        value = sample()
        for key in ("state", "motion_time", "prev_action", "history", "sim_ctx", "episode"):
            data["sample_"+key] = array(value[key])
        return value

    def before_forward(module, inputs):
        obs, = inputs
        goal = obs["goal_motion"]
        with torch.no_grad():
            aux = env.aux_state.detach()
            quat = aux[..., 3:7]
            w,x,y,z = quat.unbind(-1)
            yaw = torch.atan2(2*(w*z+x*y), 1-2*(y*y+z*z))
            dx,dy = (run.bank.root_pos_w[env.motion_times,:2] - aux[..., :2]).unbind(-1)
            c,s = torch.cos(yaw), torch.sin(yaw)
            expect = torch.stack((c*dx+s*dy, -s*dx+c*dy), -1)/.05
            tail = goal[...,540:]
            checks.append(dict(step=len(checks), measured_max_error=float((tail-expect).abs().max()),
                               tail_abs_max=float(tail.abs().max()), aux_requires_grad=env.aux_state.requires_grad,
                               goal_requires_grad=goal.requires_grad,
                               first_motion_frame=int(env.motion_times[0]),
                               first_predicted_root_xy=array(aux[0,:2]).tolist(),
                               first_body_xy=array(tail[0]).tolist()))
            if len(checks)==1:
                data["imagined_initial_goal540"] = array(goal[..., :540])
                data["imagined_initial_tail"] = array(tail)
                data["imagined_initial_noisy_history"] = array(obs["history"])

    def after_forward(module, inputs, action):
        if len(checks)==1:
            data["first_imagined_clipped_command"] = array(action)

    def grad_hook(gradient):
        data["gradient_before_clip"] = array(gradient[:,540:])

    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(env, "sample_initial_states", traced_sample))
            stack.enter_context(weight.register_hook(grad_hook))
            stack.enter_context(run.actor.register_forward_pre_hook(before_forward))
            stack.enter_context(run.actor.register_forward_hook(after_forward))
            yield
        for i, lanes in enumerate(run.replay.receipt):
            data["draw_actor" if i==10 else f"draw_wm_{i+1:02}"] = lanes
        for name in ("exp_avg", "exp_avg_sq"):
            data[name+"_tail"] = array(adam.state[weight][name][:,540:])
        data["weight_tail_after"] = array(weight[:,540:])
        data["gradient_after_clip"] = array(weight.grad[:,540:])
        save(light, raw, "first_retained_update_observation", data,
             dict(draw_count=len(run.replay.receipt), history_length=10,
                  horizon_calls=checks, adam_shared_step=int(adam.state[weight]["step"]),
                  statistics_before=before, statistics_after=stats(run),
                  global_norm_field="updates.jsonl metrics.Policy/grad_norm (before global clipping)"))
    finally:
        run.replay.receipt = initial_receipt
