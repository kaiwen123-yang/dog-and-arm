"""Run a fixed, preregistered pair of genuine standard H32 development pilots."""
import argparse
import copy
from contextlib import ExitStack
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import time
from unittest.mock import patch
import zipfile

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")

import numpy as np
import torch
import warp as wp
import yaml

from learning.b0.contact_model import SCHEMA
from learning.b0.contact_sources import RegisteredWM, native_episodes
from learning.b0.contact_training import ContactRun
from scripts.b0.dynamics_h32_probe import (
    array, assert_draws, checked_first_batch, fork_rng, objective_probe,
    observed_draws, restore_rng, rng_state,
)

OUT = Path("results/b0/standard_dynamics_20261124")
RAW = Path("results/raw_large/b0/dynamics_20261124")
SHARED = RAW / "h32_shared"
REG = OUT / "pilot_execution_lock.json"
ARMS = ("control", "experiment")
DEVICE = "cuda:0"
COUNTERS = ("load_ticks","lost_ticks","slip_ticks","sat_ticks","saturation_time")


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+".tmp")
    temp.write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")
    temp.replace(path)


def append(path, data):
    with path.open("a") as f:
        f.write(json.dumps(data, allow_nan=False)+"\n")


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def resolved(path):
    cfg = yaml.safe_load(Path(path).read_text())
    return resolved(cfg["base"]) | cfg if "base" in cfg else cfg


def register(args):
    if REG.exists():
        raise FileExistsError(REG)
    prereg = OUT/"pilot_registration.json"
    pr = read(prereg)
    if pr["experiment_kind"] != "development_h32_pilot" or pr["training_physics_id"] != args.identity:
        raise ValueError("Mismatch with the prospective H32 registration")
    choice = read(args.selection)
    if not args.identity or not args.config:
        raise ValueError("Both the qualified numerical identity and its config are required")
    checkpoints = {arm: str(Path(choice[f"{arm}_checkpoint"])) for arm in ARMS}
    cfg = resolved(args.config)
    if (cfg["actor_horizon"], cfg["policy_dt"], cfg["preserve_continuous_bias"]) != (32,.02,True):
        raise ValueError("Expected the continuous-bias H32 standard identity")
    write(REG, dict(experiment_kind="development_h32_pilot", seed=0, config=str(args.config),
        physics_identity=args.identity, training_physics_dt=cfg["physics_dt"], policy_dt=cfg["policy_dt"],
        formal_physics="original single-world training-version Warp 2 ms / native MuJoCo 3.3.0",
        historical_selected_wm=None, historical_wm_retention_passed=False,
        pilot_wm=checkpoints["experiment"], checkpoints=checkpoints,
        checkpoint_sha256={k:sha(v) for k,v in checkpoints.items()},
        preregistration=str(prereg), preregistration_sha256=sha(prereg),
        config_sha256=sha(args.config), locked_selection=str(args.selection), selection_sha256=sha(args.selection),
        recipe="4.4 C20+1000 default; one terminal alternative only if all six paired measures meet preregistration",
        max_pilot_updates={"H32":20,"joint_WM":200,"Critic":400}, offline_budget_separate=True,
        initialization="B0-03 standard actor and its unit-preserving gain; common compatible Critic and fresh official optimizers",
        bootstrap_target="abc124c bootstrap and GAE use the current Critic; no distinct target module",
        common_collection="one seed0 initial collection at fixed actor parameters and frozen initial normalization; "
                          "complete Warp Data and lane/counter/replay/sampler/RNG restoration before either branch",
        post_u1="independent live-policy collection with the original normalization update schedule",
        timestamps_unix={"lock_read_and_registration":time.time()}))


def build(arm, collection_config=None):
    if collection_config is None:
        reg = read(REG)
        if sha(reg["locked_selection"]) != reg["selection_sha256"] or sha(reg["checkpoints"][arm]) != reg["checkpoint_sha256"][arm]:
            raise ValueError("Pilot selection or initializer changed after lock")
        if sha(reg["preregistration"]) != reg["preregistration_sha256"] or sha(reg["config"]) != reg["config_sha256"]:
            raise ValueError("Preregistration or configuration changed after lock")
        cfg = resolved(reg["config"]) | {"wm_checkpoint":reg["checkpoints"][arm]}
    else:
        # Frozen physical collection never calls Dynamics.forward. This inherited C20 only
        # supplies the projected network shape while the new-identity paired fits are running.
        cfg = resolved(collection_config) | {"wm_checkpoint":"results/b0/response_wm_v1/wm_000000.pt"}
    if cfg.get("temporal_id","C20")!="C20" or any(cfg.get(k) for k in (
            "calibrated_actor","physical_action_prior","task_reward_scales","peak_force_checkpoint","long_horizon_tcp_wm")):
        raise ValueError("Unexpected standard policy or reward lineage")
    if cfg.get("actor_parameterization") not in (None, "effort_scaled") and cfg.get("actor_parameterization") != "standard_effort_scaled":
        raise ValueError(f"Unexpected actor parameterization: {cfg['actor_parameterization']}")
    torch.manual_seed(0)
    np.random.seed(0)
    torch.set_float32_matmul_precision("high")
    src = torch.load(cfg["actor_checkpoint"], map_location="cpu", weights_only=False)
    base = yaml.safe_load(Path("config/b0/free_servo_cloud.yaml").read_text())
    if (src["seed"],src["updates"],src["collected"],src["cfg"]) != (0,1000,1088000,base):
        raise ValueError("Unexpected B0-03 initializer")
    wm = torch.load(cfg["wm_checkpoint"], map_location="cpu", weights_only=False)
    if wm["schema"] != SCHEMA or wm["seed"] != 0:
        raise ValueError("Unexpected WM initializer")
    refs = [Path(cfg["reference_directory"])/name for name in cfg["references"]]
    paths = refs + [Path(cfg["reference_directory"])/name for name in cfg["additional_teacher_episodes"]]
    run = ContactRun(cfg, refs, paths, src, wm, DEVICE, from_free_anchor=True)
    if collection_config is None and (cfg["training_physics_id"] != reg["physics_identity"]
            or cfg["physics_dt"] != wm.get("physics_dt") or run.rep.substep_coeff != wm.get("substep_coeff")):
        raise ValueError("WM numerical identity differs from the qualified pilot clock")
    if type(run.actor).__name__ != "EffortScaledActor" or run.h32_teacher_batches or run.policy.critic is not run.critic:
        raise ValueError("Unexpected model/target configuration")
    if collection_config is None:
        run.registered_wm = RegisteredWM(cfg, run.model, run.rep, native_episodes(paths, DEVICE), DEVICE)
    return run


def package(run, count):
    return dict(actor=run.actor.state_dict(), critic=run.critic.state_dict(), dyn=run.dyn.state_dict(),
                cfg=run.cfg, updates=count, collected=run.total, seed=0, schema=SCHEMA)


def atomic_torch(obj, p):
    tmp = p.with_suffix(".tmp")
    torch.save(obj,tmp)
    tmp.replace(p)


def records(obj, prefix=""):
    for f in dataclasses.fields(obj):
        value = getattr(obj, f.name)
        name = prefix + f.name
        if isinstance(value, wp.array) and value.size:
            yield name, value
        elif dataclasses.is_dataclass(value):
            yield from records(value, name+".")


def solver_snapshot(run, load):
    """Preserve all nonempty MuJoCo-Warp Data arrays, without forwarding the restored world."""
    path = SHARED/"solver.npz"
    wp.synchronize()
    if load:
        with np.load(path, allow_pickle=False) as archive:
            fields = list(records(run.plant.sim.wp_data))
            if set(archive.files) != {key for key,_ in fields}:
                raise ValueError("Different Warp data schema")
            for key, buf in fields:
                buf.assign(archive[key])
        wp.synchronize()
        return
    temp = path.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for key,buf in records(run.plant.sim.wp_data):
            with archive.open(key+".npy","w",force_zip64=True) as out:
                np.lib.format.write_array(out,buf.numpy(),allow_pickle=False)
    temp.replace(path)


def prepare(config):
    run = build("control", collection_config=config)
    rec = OUT/"shared_collection.json"
    if rec.exists():
        raise FileExistsError(rec)
    SHARED.mkdir(parents=True, exist_ok=True)
    run.compact_directory = SHARED
    original = copy.copy(run.cfg)
    initial_actor = {k:v.clone() for k,v in run.actor.state_dict().items()}
    run.cfg["freeze_actor_statistics"] = True
    wall = time.monotonic()
    while not run.schedule.pending:
        item = run.collect()
        append(OUT/"common_cohorts.jsonl", dict(cohort=run.schedule.cohorts, due=run.schedule.pending, **item))
    run.cfg = original
    equal = all(torch.equal(t,run.actor.state_dict()[k]) for k,t in initial_actor.items())
    if not equal or run.sampler._step or not run.replay.chunks:
        raise ValueError("Common collection changed actor/normalization or has an incomplete boundary")
    # The fine controller can hold a separate lagged bias cache carried between 2ms ticks.
    counters = {k: v.clone() for k,v in vars(run.plant).items()
                if torch.is_tensor(v) and (k in COUNTERS or "bias" in k and k != "bias_gain")}
    basis = dict(actor=run.actor.state_dict(),critic=run.critic.state_dict(),
                 optimizers=[o.state_dict() for o in run.optimizer_list()],
                 replay=list(run.replay.chunks),tail=run.replay.tail,lanes=run.lanes,counters=counters,
                 last_episode=run.last_episode,total=run.total,simulated=run.simulated,
                 ratio=run.schedule.state_dict(),sampler=run.sampler.state_dict(),rng=rng_state())
    atomic_torch(basis, SHARED/"first.pt")
    solver_snapshot(run, False)
    write(rec, dict(collected=run.total, simulated=run.simulated, last_episode=run.last_episode,
        unchanged_actor_and_normalization=equal, optimizers=len(basis["optimizers"]),
        optimizer_state_entries=[len(x["state"]) for x in basis["optimizers"]],
        critic_equals_bootstrap_target=run.policy.critic is run.critic, ratio=basis["ratio"],
        replay_chunks=len(basis["replay"]), tail=len(basis["tail"]), counters=list(counters),
        physics_dt=run.model.opt.timestep, training_physics_id=run.cfg.get("training_physics_id"),
        config=str(config), collection_only_unused_WM_forward_calls=0, prefix_s=.2, elapsed_s=time.monotonic()-wall,
        shared_state=str((SHARED/"first.pt").resolve()), warp_data=str((SHARED/"solver.npz").resolve()),
        source_sha256=sha(SHARED/"first.pt"), solver_sha256=sha(SHARED/"solver.npz")))


def load_common(run):
    s = torch.load(SHARED/"first.pt", map_location=DEVICE, weights_only=False)
    for k in ("actor","critic"):
        state = getattr(run,k).state_dict()
        if list(state) != list(s[k]) or any(not torch.equal(v,s[k][n]) for n,v in state.items()):
            raise ValueError(f"{k} or normalizer differs between the actual arm and seed0 common initialization")
    if not all(len(o.state)==len(v["state"])==0 for o,v in zip(run.optimizer_list(),s["optimizers"],strict=True)):
        raise ValueError("Unexpected prior optimizer steps at pilot start")
    for o,v in zip(run.optimizer_list(),s["optimizers"],strict=True):
        o.load_state_dict(v)
    run.replay.chunks.extend(s["replay"])
    run.replay.tail = s["tail"]
    run.schedule.load_state_dict(s["ratio"])
    run.sampler.load_state_dict(s["sampler"])
    run.lanes = s["lanes"]
    run.last_episode,run.total,run.simulated = s["last_episode"],s["total"],s["simulated"]
    solver_snapshot(run, True)
    for k,v in s["counters"].items():
        current = getattr(run.plant,k,None)
        if current is None:
            setattr(run.plant, k, v)
        else:
            current.copy_(v)
    restore_rng(s["rng"])


def check_shared(config):
    run = build("control", collection_config=config)
    load_common(run)
    with np.load(SHARED/"solver.npz") as z:
        for k,buf in records(run.plant.sim.wp_data):
            np.testing.assert_array_equal(buf.numpy(),z[k],err_msg=k)
        n = len(z.files)
    original = torch.load(SHARED/"first.pt",map_location=DEVICE,weights_only=False)
    for k,v in original["counters"].items():
        torch.testing.assert_close(getattr(run.plant,k),v,rtol=0,atol=0,equal_nan=True)
    cfg_dt = float(run.model.opt.timestep)
    if cfg_dt != read(OUT/"shared_collection.json")["physics_dt"]:
        raise ValueError("Shared physical timestep changed")
    write(OUT/"shared_restore.json",dict(solver_arrays_exact=n,external_state_exact=list(original["counters"]),
        phase="between two complete actor ticks, before any H32 probe",
        physics_dt=cfg_dt,coefficient=run.rep.substep_coeff, collected=run.total,ratio=run.schedule.state_dict(),
        actor_initialization_and_critic_exact=True,training_updates=0))

def locations(arm):
    out, raw = OUT/"h32"/arm, RAW/"h32"/arm
    out.mkdir(exist_ok=True,parents=True)
    raw.mkdir(exist_ok=True,parents=True)
    return out,raw


def preflight(arm):
    out,raw = locations(arm)
    if (out/"preflight.json").exists():
        raise FileExistsError(out/"preflight.json")
    run = build(arm)
    load_common(run)
    starts, draws, noise = checked_first_batch(run)
    np.savez_compressed(out/"preflight_draws.npz",**draws)
    result = objective_probe(run, starts, noise, raw/"preflight_objective.npz")
    write(out/"preflight.json",result)
    print(arm, "preflight", result["finite"], result["objective_mean"], flush=True)


def verify():
    p = OUT/"h32"/"preflight_pair.json"
    arms = [locations(arm) for arm in ARMS]
    before = [read(out/"preflight.json") for out,_ in arms]
    with np.load(arms[0][0]/"preflight_draws.npz") as a, np.load(arms[1][0]/"preflight_draws.npz") as b:
        assert_draws(dict(a),dict(b))
        groups = list(a)
    with np.load(arms[0][1]/"preflight_objective.npz") as a, np.load(arms[1][1]/"preflight_objective.npz") as b:
        identified = [k for k in a if k.startswith("start_") or k in ("first_action_canonical","first_command_physical")]
        for k in identified:
            np.testing.assert_array_equal(a[k], b[k], err_msg=k)
    finite = all(x["finite"] for x in before)
    write(p,dict(passed=finite, ordered_draw_groups_equal=groups, equal_start_inputs=identified,
        elapsed_before_updates=True, baseline_replay=str(SHARED/"first.pt"), same_noise_rng=True,
        numerical_failures={arm:d["nonfinite"] for arm,d in zip(ARMS,before,strict=True) if not d["finite"]}))
    if not finite:
        raise FloatingPointError("Development H32 preflight contains a nonfinite objective or derivative")




def optimizer_steps(run):
    counts = {}
    for name, opts in (("wm",run.learners[7].optimizers),("actor",run.policy.actor_optimizers),
                       ("critic",run.policy.critic_optimizers)):
        steps = [int(state["step"].item()) for opt in opts for state in opt.state.values() if "step" in state]
        counts[name] = max(steps,default=0)
    return counts


def checkpoint(run,count,out,raw):
    weights = package(run,count)
    atomic_torch(weights, raw/f"checkpoint_{count:06}.pt")
    rnd = rng_state()
    state = weights | dict(optimizers=[o.state_dict() for o in run.optimizer_list()],
        replay=list(run.replay.chunks),simulated=run.simulated,cpu_rng=rnd["cpu"],gpu_rng=rnd["gpu"],
        numpy_rng=rnd["numpy"],ratio_state=run.schedule.state_dict(),return_sampler_state=run.sampler.state_dict(),
        lane_boundary=dict(last_episode=run.last_episode,live_lanes=run.n,mode="administrative_restart"))
    atomic_torch(state,raw/"cohort_state.pt")
    write(out/"recovery.json",dict(update=count,complete_state=str((raw/"cohort_state.pt").resolve()),
        policy_checkpoint=str((raw/f"checkpoint_{count:06}.pt").resolve()),ratio=state["ratio_state"],
        live_lanes_on_working_process=run.n, resume="standard train_contact administrative restart with real per-lane 200ms prefixes",
        optimizer_minibatches=optimizer_steps(run)))


def train(arm):
    if not read(OUT/"h32"/"preflight_pair.json")["passed"]:
        raise ValueError("Both matched preflight H32 VJPs must be finite before joint training")
    out, raw = locations(arm)
    if (out/"updates.jsonl").exists():
        raise FileExistsError("Use the committed recovery boundary rather than repeating counted updates")
    run = build(arm)
    load_common(run)
    run.compact_directory = raw
    write(out/"actual_config.json",dict(cfg=run.cfg, common_first="shared_collection.json",
        frozen_initial_normalization_through_first_collection=True,validation_excluded=True,
        branch=arm, training_device=torch.cuda.get_device_name(), original_update="ContactRun.update"))
    (out/"resolved.yaml").write_text(yaml.safe_dump(run.cfg,sort_keys=False))
    checkpoint(run,0,out,raw)
    wall = time.monotonic()
    expected, expected_draws, noise = checked_first_batch(run)
    with np.load(out/"preflight_draws.npz") as pre:
        assert_draws(expected_draws,dict(pre))
    for count in range(1,11):
        try:
            while not run.schedule.pending:
                tick = run.schedule.cohorts+1
                # The common block already has its own authoritative compact archive.
                sampled = run.collect()
                append(out/"cohorts.jsonl",dict(cohort=tick,due=run.schedule.pending,**sampled))
            run.wm_index = (count-1)*10
            with ExitStack() as stack:
                if count==1:
                    def perform_u1():
                        # ContactRun just performed the original ten actual WM minibatches.
                        if optimizer_steps(run) != dict(wm=10,actor=0,critic=0):
                            raise RuntimeError(f"Unexpected u1 intervention point: {optimizer_steps(run)}")
                        atomic_torch(dict(dyn=run.dyn.state_dict(), wm_optimizers=[o.state_dict() for o in run.learners[7].optimizers],
                            rng=rng_state(), wm_index=run.wm_index, online_recovery=str(SHARED/"first.pt")),
                            raw/"u1_after_wm_before_actor.pt")
                        np.savez_compressed(out/"u1_actual_wm_draws.npz",**actual)
                        result = objective_probe(run, expected, noise, raw/"u1_after_wm_objective.npz")
                        write(out/"u1_after_wm_objective.json",result)
                        if not result["finite"]:
                            raise FloatingPointError("True u1 start has nonfinite H32 gradient after joint WM")
                        from learning.b0.contact_gradient import trace_first_update
                        trace_first_update(run,out,raw)
                        return true_policy()
                    true_policy = run.policy.update
                    stack.enter_context(patch.object(run.policy,"update",perform_u1))
                with observed_draws(run) as actual:
                    metrics = run.update()
            run.schedule.pending -= 1
            if count in (1,10):
                checkpoint(run,count,out,raw)
            np.savez_compressed(out/f"draws_u{count:02}.npz",**actual)
            if count==1:
                assert_draws(expected_draws,actual)
                with np.load(raw/"u1_true_actor_batch.npz") as observed, np.load(raw/"u1_after_wm_objective.npz") as pre:
                    for key in ("episode","motion_time","state","history","prev_action"):
                        np.testing.assert_array_equal(observed[key], pre["start_"+key])
                    np.testing.assert_array_equal(observed["first_command"],pre["first_action_canonical"])
                    reference = pre["dobjective_dphysical_action"]
                    err = abs(observed["dreturn_dphysical_complete"]-reference)
                    grad = dict(max_abs=float(np.max(err)),reference_max=float(np.max(abs(reference))),
                        p95_abs=float(np.percentile(err,95)), matches_same_command_and_start=True)
                    write(out/"u1_readonly_vs_actual.json",grad)
            for item in run.registered_wm.rows:
                append(out/"wm_draws.jsonl",dict(update=count, **item))
            run.registered_wm.rows.clear()
            actual_steps = optimizer_steps(run)
            if actual_steps != {"actor":count,"wm":10*count,"critic":20*count}:
                raise RuntimeError(f"Real optimizer counters disagree with budget at u{count}: {actual_steps}")
            row = dict(update=count, optimizer_steps=actual_steps, valid=run.total,simulated=run.simulated,
                ratio=run.schedule.state_dict(),elapsed_s=time.monotonic()-wall,**metrics)
            append(out/"updates.jsonl",row)
            print(arm,f"u{count}",run.total,float(metrics["actor_max_weight_change"]),flush=True)
        except Exception as exc:
            write(out/"failure.json",dict(update_begun=count,exception=repr(exc),actual_steps=optimizer_steps(run),
                last_persisted_checkpoint=read(out/"recovery.json")["update"],valid=run.total))
            raise
    write(out/"outcome.json",dict(arm=arm,seed=0,H32=10,WM=100,Critic=200,
        actual_steps=optimizer_steps(run),valid=run.total,simulated=run.simulated,elapsed_s=time.monotonic()-wall,
        common_interaction_counted_once=read(OUT/"shared_collection.json")["collected"],
        ratio=run.schedule.state_dict(),source="same seed0, distinct WM development mechanisms"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="stage",required=True)
    registry = sub.add_parser("register")
    registry.add_argument("--config",type=Path,required=True)
    registry.add_argument("--identity",required=True)
    registry.add_argument("--selection",type=Path,required=True)
    sub.add_parser("prepare").add_argument("--config", type=Path, required=True)
    sub.add_parser("check-shared").add_argument("--config",type=Path,required=True)
    sub.add_parser("verify")
    for name in ("preflight","train"):
        sub.add_parser(name).add_argument("arm", choices=ARMS)
    args = parser.parse_args()
    if args.stage=="register":
        register(args)
    elif args.stage=="prepare":
        prepare(args.config)
    elif args.stage=="check-shared":
        check_shared(args.config)
    elif args.stage=="preflight":
        preflight(args.arm)
    elif args.stage=="verify":
        verify()
    else:
        train(args.arm)
