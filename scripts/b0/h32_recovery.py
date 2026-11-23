"""Controlled seed0 replay, H32 gradient decomposition, and official joint updates."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
from types import MethodType

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
from learning.b0.contact_model import SCHEMA
from learning.b0.contact_training import ContactRun
from learning.b0.contact_warp import PHASE_ID


def write(path, record):
    with path.open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write("\n")


def gradient_audit(run, batch, output):
    """One sampled graph, including the same noisy histories, for all components."""
    env, policy = run.policy.wm_env, run.policy
    cfg = policy.cfg
    env.dynamics.eval().requires_grad_(False)
    env.representation.eval().requires_grad_(False)
    run.actor.train()
    obs = env.reset(batch)
    actions = []
    survival = torch.ones(len(batch), device=env.device)
    returns = survival * 0
    aux = returns
    prior = returns
    for t in range(cfg.horizon):
        a = run.actor(obs)
        actions.append(a)
        obs, reward, done, _ = env.step(a)
        returns = returns + cfg.gamma**t * survival * reward
        survival = survival * (1 - done)
        aux = aux + run.actor.auxiliary_loss()
        if hasattr(run.actor, "training_action_prior"):
            prior = prior + run.actor._physical_prior_cost
    from supermimic.learners.policy_learner import ActorCriticPolicyLearner
    boot = ActorCriticPolicyLearner._bootstrap(policy, obs, survival, done)
    raw_value = run.critic(obs["critic"]).squeeze(-1)
    tensors = list(run.actor.parameters())
    gradients = {}
    for key, x in [("tracking", returns), ("bootstrap", boot), ("physical_prior_cost", prior), ("other_aux_cost", aux-prior)]:
        if not x.requires_grad:
            gradients[key] = {"actor_l2": 0., "first_action_l2": 0.}
            continue
        grads = torch.autograd.grad(x.mean(), tensors + [actions[0]], allow_unused=True, retain_graph=True)
        flat = torch.cat([torch.zeros_like(p).flatten() if g is None else g.detach().flatten()
                          for p, g in zip(tensors, grads[:-1])])
        g = grads[-1]
        gradients[key] = {"actor_l2": flat.norm().item(),
                          "first_action_l2": 0. if g is None else g.norm().item(),
                          "flat": flat}
    g, b = gradients["tracking"]["flat"], gradients["bootstrap"]["flat"]
    cosine = torch.nn.functional.cosine_similarity(g,b,dim=0).item()
    for item in gradients.values():
        item.pop("flat", None)
    def values(x):
        return x.detach().cpu().tolist()
    write(output, dict(horizon=cfg.horizon, gamma=cfg.gamma, observed_replay_frames=values(batch["motion_time"]),
                       measured_start_interval_terminal=values(batch["terminated"]), phases=values(run.phases[batch["motion_time"],0]),
                       cumulative_discounted_immediate=values(returns), raw_terminal_critic=values(raw_value),
                       clipped_discounted_bootstrap=values(boot), final_survival=values(survival),
                       prior_cost=values(prior), other_aux=values(aux-prior), actor_gradient_cosine_tracking_bootstrap=cosine,
                       gradient=gradients, frozen_world_model=all(not p.requires_grad for p in run.dyn.parameters())))


def checkpoint(run, count, out):
    state = dict(actor=run.actor.state_dict(), critic=run.critic.state_dict(), dyn=run.dyn.state_dict(),
                 cfg=run.cfg, updates=count, collected=run.total, seed=0, schema=SCHEMA)
    torch.save(state, out / f"checkpoint_{count:06d}.pt")
    state.update(optimizers=[o.state_dict() for o in run.optimizer_list()], replay=list(run.replay.chunks),
                 simulated=run.simulated, cpu_rng=torch.get_rng_state(), gpu_rng=torch.cuda.get_rng_state(),
                 numpy_rng=np.random.get_state())
    torch.save(state, out / "cohort_state.tmp")
    (out / "cohort_state.tmp").replace(out / "cohort_state.pt")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--anchor", type=Path, default=Path("results/b0/full_s0_joint_warp_prior_r1/checkpoint_000000.pt"))
    p.add_argument("--references", type=Path, default=Path("results/raw_large/b0/full_warp_hold_park_r1"))
    p.add_argument("--run", required=True)
    p.add_argument("--updates", type=int, default=1)
    p.add_argument("--worlds", type=int, default=64)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--variant", choices=("tracking", "detached_bootstrap", "physical_prior", "real_td_terminal", "real_td_continue"), required=True)
    p.add_argument("--full-wm", type=Path, help="Separate single-variable WM initialization experiment")
    p.add_argument("--resume", type=Path)
    p.add_argument("--matched-detached", action="store_true", help="Fork the first actual post-WM batch and RNG for an auxiliary detached-bootstrap Actor/Critic update")
    a = p.parse_args()
    if Path(a.run).name != a.run or a.run in ("", ".", "..") or min(a.batch,a.worlds,a.updates)<1:
        p.error("Specify a fresh run name and positive dimensions")
    device = "cuda:0"
    torch.manual_seed(0)
    np.random.seed(0)
    torch.set_float32_matmul_precision("high")
    frozen = torch.load(a.anchor, weights_only=False, map_location="cpu")
    cfg = dict(frozen["cfg"], reference_directory=str(a.references), cohort_steps=40,
               worlds=a.worlds, wm_batch=a.batch, actor_batch=a.batch, recovery_variant=a.variant)
    if a.variant != "physical_prior":
        cfg.pop("physical_action_prior", None)
    paths = [a.references/name for name in cfg["references"]]
    wm=frozen
    if a.full_wm:
        wm=torch.load(a.full_wm,weights_only=False,map_location="cpu")
        if wm["schema"]!=frozen["schema"]:
            raise ValueError("WM schema mismatch")
        cfg["full_wm_initializer"]=str(a.full_wm)
    run = ContactRun(cfg, paths, paths, frozen, wm, device)
    # ContactRun normally migrates the B0-03 critic; the exact entire full u0 critic is required here.
    run.critic.load_state_dict(frozen["critic"], strict=True)
    out = Path("results/b0")/a.run
    raw = Path("results/raw_large/b0")/a.run
    out.mkdir(exist_ok=False)
    raw.mkdir(exist_ok=False)
    write(out/"actual_config.json", dict(cfg=cfg, anchor=str(a.anchor), references=[str(x) for x in paths],
          variant=a.variant, initialization="Complete frozen Actor/WM/Critic including normalizers; fresh seed0 RNG and optimizers except explicit recovery resume.",
          resume=str(a.resume) if a.resume else None, training="Pinned O1 H32; 10 WM and 20 Critic minibatches per update, first update Actor before Critic. 40 physical intervals per cohort."))
    start=0
    if a.resume:
        st=torch.load(a.resume,weights_only=False,map_location=device)
        if st["cfg"]!=cfg or st["schema"]!=SCHEMA:
            raise ValueError("Resume requires exact recovery config")
        for name in ("actor","critic","dyn"):
            getattr(run,name).load_state_dict(st[name])
        for opt,state in zip(run.optimizer_list(),st["optimizers"],strict=True):
            opt.load_state_dict(state)
        run.replay.chunks.extend(st["replay"])
        run.total,run.simulated=st["collected"],st["simulated"]
        torch.set_rng_state(st["cpu_rng"].cpu())
        torch.cuda.set_rng_state(st["gpu_rng"].cpu())
        np.random.set_state(st["numpy_rng"])
        start=st["updates"]
        del st
    if a.updates<=start:
        raise ValueError("Specify an update beyond the resume boundary")
    checkpoint(run,start,out)
    original = run.policy._bootstrap
    if a.variant == "detached_bootstrap":
        def detached(self, obs, survival, term):
            return original(obs,survival,term).detach()
        run.policy._bootstrap = MethodType(detached,run.policy)
    td_stats={}
    if a.variant in ("real_td_terminal","real_td_continue"):
        from scripts.b0.h32_real_critic import fit_real_critic
        original_update=run.policy.update
        def real_td_then_policy():
            td_stats.clear()
            td_stats.update(fit_real_critic(run,a.variant=="real_td_terminal"))
            return original_update()
        run.policy.update=real_td_then_policy
    with (out/"updates.jsonl").open("x",buffering=1) as log:
        for count in range(start+1,a.updates+1):
            capture = count in (1,5,10,50)
            raw_cohort = raw/f"cohort_{count:06d}" if capture else None
            metrics=run.collect(raw_cohort)
            if count==1 and a.variant not in ("real_td_terminal","real_td_continue"):
                # Audit the exact starts of the first actual Actor update, after that update's WM fit.
                # Restore RNG so the official learner reuses the same start selection and sensor noise.
                default=run.policy.update
                def traced_update():
                    cpu,gpu,numpy_state=torch.get_rng_state(),torch.cuda.get_rng_state(),np.random.get_state()
                    batch=run.policy.wm_env.sample_initial_states()
                    noise_rng=torch.cuda.get_rng_state()
                    gradient_audit(run,batch,out/"first_gradient.json")
                    if a.matched_detached:
                        if a.variant!="tracking":
                            raise ValueError("The fork requires the no-prior tracking control")
                        fork=out/"matched_detached"
                        fork.mkdir()
                        modules=[run.actor,run.critic]
                        snapshots=[deepcopy(m.state_dict()) for m in modules]
                        opts=[*run.policy.actor_optimizers,*run.policy.critic_optimizers]
                        opt_state=[deepcopy(o.state_dict()) for o in opts]
                        torch.cuda.set_rng_state(noise_rng)
                        run.policy._bootstrap=lambda obs,surv,term:original(obs,surv,term).detach()
                        stat=run.policy._train_batch(batch)
                        run.policy._bootstrap=original
                        run.cfg=dict(cfg,recovery_variant="matched_detached_bootstrap")
                        checkpoint(run,count,fork)
                        write(fork/"first_update.json",dict(metrics={k:float(v) for k,v in stat.items()},
                              batch_frames=batch["motion_time"].cpu().tolist(),trained_critic=True,
                              origin="same first actual post-WM replay batch, identical Actor/Critic and RNG, last value detached for Actor only"))
                        run.cfg=cfg
                        for module,weights in zip(modules,snapshots):
                            module.load_state_dict(weights)
                        for opt, weights in zip(opts,opt_state):
                            opt.load_state_dict(weights)
                    torch.set_rng_state(cpu)
                    torch.cuda.set_rng_state(gpu)
                    np.random.set_state(numpy_state)
                    return default()
                run.policy.update=traced_update
            if capture:
                before={name:p.detach().clone() for name,p in (("wm",run.dyn.mlp[-1].weight),("critic",run.critic[-1].weight))}
            update=run.update()
            if count==1 and a.variant not in ("real_td_terminal","real_td_continue"):
                run.policy.update=default
            if capture:
                update["wm_output_max_delta"]=(run.dyn.mlp[-1].weight.detach()-before["wm"]).abs().max().item()
                update["critic_output_max_delta"]=(run.critic[-1].weight.detach()-before["critic"]).abs().max().item()
            row=dict(update=count,**metrics,**update,**td_stats)
            log.write(json.dumps(row,allow_nan=False)+"\n")
            if capture or count==a.updates:
                checkpoint(run,count,out)
                print(json.dumps(row),flush=True)
    write(out/"outcome.json",dict(completed=a.updates,valid_transitions=run.total,
          simulated=run.simulated, gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated(),
          first_new_update=start+1))

if __name__=="__main__":
    main()
