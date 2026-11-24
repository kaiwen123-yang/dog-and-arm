"""One train-input reparameterization and the registered C20 offline comparison."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
import yaml
from supermimic.learners import wm_learner
from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg, SCHEMA
from learning.b0.contact_sources import RegisteredWM, native_episodes
from learning.b0.contact_training import rebase_wm_input_layer, wm_input_coordinates
from learning.b0.physics import ActionMap, make_model
from learning.b0.temporal_dynamics import make_dynamics
from scripts.b0 import train_temporal_pair as prior

OUT = Path("results/b0/standard_dynamics_20261124")
RAW = Path("results/raw_large/b0/dynamics_20261124")
LOCK = OUT / "c20_data_identity.json"
DEVICE = "cuda:0"
NAMES = ["native", "grip", "multimode", "response"]


def write(path, value, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write("\n")


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def model_and_rep(dt):
    model = make_model()
    model.opt.timestep = dt
    rep = ContactRepresentation(model, DEVICE)
    n = round(rep.dt / dt)
    if not np.isclose(rep.dt, n * dt) or abs(rep.substep_coeff - (n + 1) / (2 * n)) > 1e-9:
        raise ValueError(f"Training representation does not match physics dt={dt}, c={rep.substep_coeff}")
    return model, rep


def build(cfg, model, rep):
    original = json.loads(Path("results/b0/lanes_wm_v1/config.json").read_text())
    paths = [Path(ep["path"]) for ep in original["sources"] if ep["split"] == "train"]
    return RegisteredWM(cfg, model, rep, native_episodes(paths, DEVICE), DEVICE)


def inventory(pool):
    return {name: [dict(group=e.group, path=str(e.path), n=len(e.state), side=e.side)
                   for e in pool.pools[name, 1].episodes] for name in NAMES}


def source_hashes(pool):
    result = {}
    for name in NAMES:
        h = hashlib.sha256()
        group = pool.pools[name,1]
        for tensor in (group.state, group.action, group.context, group.starts, pool.pools[name,7].starts):
            array = tensor.detach().contiguous().cpu().numpy()
            h.update(str((array.shape,array.dtype.str)).encode())
            h.update(memoryview(array).cast("B"))
        result[name] = h.hexdigest()
    return result


def open_draws(info, pool):
    reg = json.loads(Path(info["source_order"]).read_text())
    if "source_tensor_hashes" in info and source_hashes(pool) != info["source_tensor_hashes"]:
        raise ValueError("Registered source data values or valid-window masks changed")
    if reg["names"] != NAMES or inventory(pool) != reg["inventory"]:
        raise ValueError("Training source paths, order or episode boundaries changed")
    if digest(info["indices"]) != info["indices_sha256"]:
        raise ValueError("Registered draw bytes changed")
    with np.load(info["indices"]) as arr:
        src, ids = arr["source"], arr["start"]
    if src.shape != (1000,256) or ids.shape != src.shape or np.any(np.diff(src.astype(int), axis=1) < 0):
        raise ValueError("Expected source-ordered 1000 x 256 original draws")
    row = np.arange(1000) % 10
    for i, name in enumerate(NAMES):
        for h in (1, 7):
            mask = (row < 2 if h == 1 else row >= 2)[:, None] & (src == i)
            if not np.isin(ids[mask], pool.pools[name, h].starts.cpu().numpy()).all():
                raise ValueError(f"Illegal {name}/H{h} start in persisted draws")
    return src, ids


def verify_new_sources(recipe, dt, coeff):
    clocks = {}
    n = round(.020/dt)
    for name, source in recipe["sources"].items():
        reg = Path(source["registration"]) if "registration" in source else Path(source["directory"])/"registration.json"
        j=json.loads(reg.read_text())
        clock=j["contact_clock"]
        if (clock["physics_dt"],clock["servo_dt"],clock["policy_dt"],clock["substep_coeff"],
            clock["physics_steps_per_policy"],clock["physical_prefix_steps"]) != (dt,.002,.02,coeff,n,10*n):
            raise ValueError(f"Wrong physical clock in {reg}")
        if name=="response":
            if j["solver_schema"]!="continuous_bias_v1":
                raise ValueError("Unexpected response solver/cache schema")
            naccepted=0
            for row in j["starts"]:
                rec=json.loads((Path(source["raw"])/row["id"]/"receipt.json").read_text())
                if rec["row"] != row:
                    raise ValueError("Response case does not match the registration")
                naccepted += not rec.get("rejected",False)
            clocks[name]=dict(clock=clock,configuration=str(reg),registered=len(j["starts"]),accepted=naccepted)
        else:
            cohorts=json.loads((Path(source["directory"])/"cohorts.json").read_text())
            if [[r["split"],r["seed"]] for r in cohorts] != j["allocation"]:
                raise ValueError(f"{name} train or validation allocation changed")
            for cohort in cohorts:
                fg=np.load(Path(cohort["path"])/"sub_finger_load_N.npy",mmap_mode="r")
                if fg.shape[-2]!=n:
                    raise ValueError(f'{cohort["path"]} has {fg.shape[-2]} samples per 20 ms')
            clocks[name]=dict(clock=clock,configuration=str(reg),cohorts=len(cohorts))
    return clocks


def args_identity(args):
    dt = args.dt_ms / 1000
    old = dt == .002
    if old and args.recipe != prior.RECIPE:
        raise ValueError("Original dt must inherit the exact registered source recipe")
    if not old and args.recipe == prior.RECIPE:
        raise ValueError("Refined physics requires a new four-source data recipe")
    cfg = yaml.safe_load(args.recipe.read_text())
    if not old and (cfg.get("physics_dt") != dt or cfg.get("training_physics_id") != args.identity or cfg.get("preserve_continuous_bias") is not True):
        raise ValueError("New cfg, physical timestep/identity or continuous bias setting differ")
    if list(cfg["wm_data_recipe"]["sources"]) != NAMES[1:]:
        raise ValueError("Training source identities or order changed")
    legacy = yaml.safe_load(prior.RECIPE.read_text())["wm_data_recipe"]
    if any(cfg["wm_data_recipe"][k] != legacy[k] for k in ("warm", "joint", "split")):
        raise ValueError("Training source schedule changed")
    model, rep = model_and_rep(dt)
    clocks = {} if old else verify_new_sources(cfg["wm_data_recipe"],dt,rep.substep_coeff)
    pool = build(cfg, model, rep)
    if old:
        regdir = prior.OUT
    else:
        regdir = OUT / "offline_draws"
        regdir.mkdir(exist_ok=True)
        if not (regdir / "paired_indices.npz").exists():
            with patch.multiple(prior, OUT=regdir, RAW=RAW/"offline_registered", RECIPE=args.recipe):
                prior.register_draws(pool)
    info = dict(physics_dt=dt, policy_dt=rep.dt, substep_coeff=rep.substep_coeff,
                physics_identity=args.identity, original_2ms=old, data_recipe=str(args.recipe),
                recipe_sha256=digest(args.recipe), init=str(prior.SOURCE), init_sha256=digest(prior.SOURCE),
                source_order=str(regdir/"paired_sources.json"), indices=str(regdir/"paired_indices.npz"),
                indices_sha256=digest(regdir/"paired_indices.npz"), node_schedule=[0,50,200,1000],
                source_counts=pool.inventory, source_clocks=clocks, source_tensor_hashes=source_hashes(pool), stats_weight="One per legal source / episode / physical input index",
                optimizer="Fresh official Muon + Adam; both H1/H7 learners share one optimizer pair",
                frozen_stat_recipe=True, original_selected_wm=None, older_eligible_gate_pass=False,
                predeclared_h32_experiment="C20+1000 by default, replace only with same-identity rebased +1000 when both u0/hold first TCP errors and both sides of each grip/multimode two-finger H32 TCP P95 are no worse modulo same-sample repeat error, with no new nonfinite or recurrence instability. Control is same-identity C20+0.",
                wm_caps={"C20":0 if old else 1000,"rebase":1000}, development_h32_caps={"h32":20,"joint_wm":200,"critic":400})
    src, ids = open_draws(info, pool)
    info["first_actual_batch_digests"] = {}
    for h,k in ((1,0),(7,2)):
        td=prior.replay_batch(pool,NAMES,src[k],ids[k],h)
        info["first_actual_batch_digests"]["H"+str(h)] = {key:hashlib.sha256(memoryview(td[key].detach().contiguous().cpu().numpy()).cast("B")).hexdigest() for key in ("state","action","sim_ctx")}
    if old:
        a = torch.load(prior.SOURCE, map_location="cpu", weights_only=False)
        b = torch.load(prior.RAW/"C20/wm_000000.pt", map_location="cpu", weights_only=False)
        if set(a["dyn"]) != set(b["dyn"]) or not all(torch.equal(v,b["dyn"][k]) for k,v in a["dyn"].items()):
            raise ValueError("Original C20 source and control step 0 differ")
        if not all(len(o["state"]) == 0 for o in b["optimizers"]):
            raise ValueError("Historical C20 control did not start with fresh optimizer states")
        info["old_c20_initial_state_verified_equal"] = True
    write(LOCK, info, exclusive=True)
    return info


def load_registration():
    info = json.loads(LOCK.read_text())
    if digest(info["data_recipe"]) != info["recipe_sha256"] or digest(info["init"]) != info["init_sha256"]:
        raise ValueError("Offline configuration or initialization changed")
    return info


def checkpoint(info, arm, step):
    if arm == "C20" and info["original_2ms"]:
        return prior.RAW / "C20" / f"wm_{step:06}.pt"
    return RAW / "offline_wm" / arm / f"wm_{step:06}.pt"


def new_wm(model, rep, weight):
    dyn = make_dynamics(model, rep, ActionMap(model), weight["hidden"], "C20", DEVICE)
    dyn.load_state_dict(weight["dyn"])
    return dyn


@torch.no_grad()
def replace_stats(pool, rep, dyn):
    old = wm_input_coordinates(dyn)
    context = dyn.mlp[0].weight[:,98:].clone()
    rows, counts = [], {}
    for name in NAMES:
        group = pool.pools[name, 1]
        idx = group.starts
        if any(ep.split!="train" for ep in group.episodes) or len(idx.unique()) != len(idx):
            raise ValueError("Duplicate episode/input identity in H1")
        rows.append(torch.cat((rep.represent(group.state[idx]), dyn.proc(group.action[idx])), dim=-1).double())
        counts[name] = len(idx)
    joined = torch.cat(rows)
    if not torch.isfinite(joined).all():
        raise FloatingPointError("Nonfinite physical inputs to statistics")
    var, mean = torch.var_mean(joined, dim=0, correction=0)
    std = var.sqrt()
    for norm, part in ((dyn.state_normalizer, slice(0,75)), (dyn.action_normalizer, slice(75,98))):
        norm._mean.copy_(mean[part].reshape_as(norm._mean))
        norm._var.copy_(var[part].reshape_as(norm._var))
        norm._std.copy_(std[part].reshape_as(norm._std))
        norm.count.fill_(len(joined))
    rebase_wm_input_layer(dyn, old)
    torch.testing.assert_close(dyn.mlp[0].weight[:,98:], context, rtol=0, atol=0)
    return dict(unique_inputs=len(joined), source_counts=counts, source_weights={k:v/len(joined) for k,v in counts.items()},
                accumulation="FP64 population mean/variance over all unique legal keys; stored FP32 once; no clipping",
                trained_columns=dict(represented_states=75, processed_physical_actions=23, unchanged_context=5),
                eps=[n.eps for n in dyn.normalizers()], old_mean=old[0].tolist(),
                old_std_plus_eps=old[1].tolist(), new_mean=mean.tolist(), new_std=std.tolist())


def jacobian_rows(model, rep, dyn, pool, src, ids):
    """Complete one-step physical-state and processed-command Jacobians at one fixed H1 row per source."""
    values = {}
    for i, name in enumerate(NAMES):
        at = int(ids[0, np.flatnonzero(src[0]==i)[0]])
        group = pool.pools[name, 1]
        context = group.context[at]
        x = group.state[at].detach()
        p = dyn.proc(group.action[at]).detach()
        def physical_step(state, processed):
            canonical = (processed-dyn.action_offset)/dyn.action_scale
            aux, r = dyn(rep.represent(state[None]), canonical[None], state[None,:7], context[None])
            return rep.reconstruct_full_state(aux,r)[0]
        result = physical_step(x, p)
        jac = torch.autograd.functional.jacobian(physical_step,(x,p),vectorize=False)
        values[name] = (at, result.detach(), *(a.detach() for a in jac))
    return values


def compare_jacobians(before, after):
    checks, arrays = {}, {}
    for name, (at,*v) in before.items():
        checks[name] = dict(absolute_start=at)
        for label, a, b in zip(("next_state", "dnext_dphysical_state", "dnext_dprocessed_action"),v,after[name][1:], strict=True):
            diff = (b-a).double()
            rel_l2 = float(diff.norm() / a.double().norm().clamp_min(1e-14))
            checks[name][label] = dict(max_abs=float(diff.abs().max()), relative_l2=rel_l2)
            arrays[name+"_"+label+"_before"] = a.cpu().numpy()
            arrays[name+"_"+label+"_after"] = b.cpu().numpy()
            if not torch.isfinite(diff).all() or rel_l2 > 2e-4:
                raise ValueError(f"Step-zero physical mapping changed at {name}/{label}: {rel_l2}")
    np.savez_compressed(RAW/"rebase_step0_jacobians.npz", **arrays)
    return checks


def physical_probe(learners, rep, dyn, pool, src, ids):
    """Loss VJPs w.r.t. full physical initial state and actual processed control sequence at fixed H1/H7."""
    result = {}
    for h,k in ((1,0),(7,2)):
        batch = prior.replay_batch(pool, NAMES, src[k], ids[k], h)
        result[h] = {}
        for i,name in enumerate(NAMES):
            take = torch.as_tensor(src[k]==i, device=DEVICE)
            td = batch[take]
            x = td["state"][:,0].detach().requires_grad_()
            action = td["action"].detach().requires_grad_()
            truth = td["state"][:,1:]
            learner = learners[h]
            r, aux = learner._rollout(rep.represent(x), action, x[:,:7], td["sim_ctx"][:,0])
            loss = learner._compute_losses(r, aux, rep.represent(truth), truth[...,:7])[0]
            dx, da = torch.autograd.grad(loss, (x, action))
            # Action in normalized policy coordinates is affine in the processed joint command.
            dp = da[:,:h]/dyn.action_scale
            y = rep.reconstruct_full_state(aux[:,-1],r[:,-1])
            truth_end = truth[:,-1]
            tcp = rep.tcp_pose(y[:,:7], y[:,7:31])[0]
            actual = rep.tcp_pose(truth_end[:,:7], truth_end[:,7:31])[0]
            outcome = {"samples":len(x), "loss":float(loss.detach()), "mean_tcp_error_mm":float((tcp-actual).detach().norm(dim=-1).mean()*1000),
                       "finger_q_rms_mm":float((y[:,29:31]-truth_end[:,29:31]).detach().square().mean().sqrt()*1000),
                       "finger_v_rms_m_s":float((y[:,59:61]-truth_end[:,59:61]).detach().square().mean().sqrt()),
                       "state_vjp_l2":float(dx.double().norm()), "first_processed_action_vjp_l2":float(dp[:,0].double().norm()),
                       "all_processed_action_vjp_l2":float(dp.double().norm()),
                       "state_vjp_abs_max_per_channel":dx.abs().amax(0).tolist(),
                       "actual_action_vjp_abs_max_per_channel":dp.abs().amax((0,1)).tolist()}
            if not all(np.isfinite(np.asarray(v)).all() for v in outcome.values()):
                raise FloatingPointError(f"Nonfinite original-unit fixed probe at {name}/H{h}")
            result[h][name] = outcome
    return result


def optim_settings(optimizers):
    return [dict(type=type(o).__name__, groups=[
        {k:(v.detach().cpu().tolist() if torch.is_tensor(v) else v) for k,v in g.items() if k!="params"}
        for g in o.param_groups]) for o in optimizers]


def train(args):
    info = load_registration()
    if info["original_2ms"] and args.arm == "C20":
        raise ValueError("The registered C20 control has already consumed its 1000 updates")
    if (args.start,args.stop) not in ((0,50),(50,200),(200,1000)):
        raise ValueError("Training must stop at the next registered checkpoint for review")
    if (OUT/f"{args.arm}_train_{args.start:06}_{args.stop:06}.jsonl").exists():
        raise FileExistsError("An attempted interval already has an actual update log")
    cfg = yaml.safe_load(Path(info["data_recipe"]).read_text())
    model, rep = model_and_rep(info["physics_dt"])
    pool = build(cfg, model, rep)
    src, ids = open_draws(info,pool)
    init = torch.load(info["init"], map_location="cpu", weights_only=False)
    weight = (torch.load(checkpoint(info,args.arm,args.start), map_location="cpu", weights_only=False) if args.start else init)
    dyn = new_wm(model,rep,weight)
    learners = {h:wm_learner.WorldModelLearner(dyn,rep,ContactWorldModelCfg(batch_size=256,horizon=h+1,num_batches=1),DEVICE)
                for h in (1,7)}
    optimizers = learners[7].optimizers
    learners[1].optimizers = optimizers
    def save(k):
        path = checkpoint(info,args.arm,k)
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            raise FileExistsError(path)
        temp = path.with_suffix(".pending")
        torch.save(dict(dyn=dyn.state_dict(),schema=SCHEMA,temporal_id="C20",seed=0,hidden=init["hidden"],
                        physics_dt=info["physics_dt"],policy_dt=rep.dt,substep_coeff=rep.substep_coeff,
                        physics_identity=info["physics_identity"],minibatches=k,initializer=info["init"],
                        offline_arm=args.arm,optimizers=[o.state_dict() for o in optimizers],
                        cpu_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state()),temp)
        temp.replace(path)
    if args.start:
        for o, saved in zip(optimizers,weight["optimizers"],strict=True):
            o.load_state_dict(saved)
        torch.set_rng_state(weight["cpu_rng"])
        torch.cuda.set_rng_state(weight["cuda_rng"])
    else:
        torch.set_float32_matmul_precision("highest")
        if args.arm == "rebase":
            before = jacobian_rows(model,rep,dyn,pool,src,ids)
            stats = replace_stats(pool,rep,dyn)
            after = jacobian_rows(model,rep,dyn,pool,src,ids)
            stats["step0_original_unit_full_jacobians"] = compare_jacobians(before,after)
            write(OUT/"c20_rebase_statistics.json",stats)
        write(OUT/f"{args.arm}_optimizer.json",dict(optimizers=optim_settings(optimizers),
                   empty_state=all(len(o.state)==0 for o in optimizers),clip=1.0,train_precision="high"))
        write(OUT/f"{args.arm}_fixed_probe_000000.json",physical_probe(learners,rep,dyn,pool,src,ids))
        save(0)
    torch.set_float32_matmul_precision("high")
    norm = torch.zeros((), device=DEVICE)
    original = wm_learner._optimize_step
    def observe(*a, **kw):
        value = original(*a, **kw)
        norm.copy_(value.detach())
        return value
    rows = []
    start = time.monotonic()
    log = OUT/f"{args.arm}_train_{args.start:06}_{args.stop:06}.jsonl"
    with patch.object(wm_learner,"_optimize_step",observe), log.open("x",buffering=1) as f:
        for k in range(args.start,args.stop):
            h = 1 if k%10 <2 else 7
            td = prior.replay_batch(pool,NAMES,src[k],ids[k],h)
            metrics = learners[h].update([td])
            row = dict(k=k+1,h=h,grad_norm=float(norm),losses={key:float(v) for key,v in metrics.items()},
                       peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                       elapsed_s=time.monotonic()-start)
            if not np.isfinite([row["grad_norm"], *row["losses"].values()]).all():
                (OUT/f"{args.arm}_nonfinite_attempt_{k+1:06}.json").write_text(json.dumps(row))
                raise FloatingPointError(f"Nonfinite at {args.arm}/{k+1}")
            rows.append(row)
            f.write(json.dumps(row,allow_nan=False)+"\n")
    if not all(p.isfinite().all() for p in dyn.parameters()):
        raise FloatingPointError("Nonfinite model parameter at interval end")
    save(args.stop)
    write(OUT/f"{args.arm}_gradients_{args.stop:06}.json",prior.interval_diagnostics(rows))
    torch.set_float32_matmul_precision("highest")
    write(OUT/f"{args.arm}_fixed_probe_{args.stop:06}.json",physical_probe(learners,rep,dyn,pool,src,ids))
    print(f"{args.arm} +{args.stop} saved, matched rows={len(rows)}",flush=True)


def probe_control(archived=False):
    if archived:
        info = dict(original_2ms=True, data_recipe=str(prior.RECIPE), physics_dt=.002,
                    source_order=str(prior.OUT/"paired_sources.json"), indices=str(prior.OUT/"paired_indices.npz"),
                    indices_sha256=digest(prior.OUT/"paired_indices.npz"))
    else:
        info = load_registration()
    if not info["original_2ms"]:
        raise ValueError("Fresh matched C20 receives probes during training")
    model, rep = model_and_rep(info["physics_dt"])
    pool = build(yaml.safe_load(Path(info["data_recipe"]).read_text()),model,rep)
    src, ids = open_draws(info,pool)
    for k in prior.NODES:
        w = torch.load(checkpoint(info,"C20",k),map_location="cpu",weights_only=False)
        dyn = new_wm(model,rep,w)
        learners={h:wm_learner.WorldModelLearner(dyn,rep,ContactWorldModelCfg(batch_size=256,horizon=h+1),DEVICE) for h in (1,7)}
        name = "archived_2ms_C20" if archived else "C20"
        write(OUT/f"{name}_fixed_probe_{k:06}.json",physical_probe(learners,rep,dyn,pool,src,ids))
        if archived and k == 0:
            jac = jacobian_rows(model,rep,dyn,pool,src,ids)
            write(OUT/"archived_2ms_jacobians.json", {source:dict(absolute_start=row[0],
                  state_matrix_dimensions=list(row[2].shape),action_matrix_dimensions=list(row[3].shape),
                  max_abs_state_sensitivity=float(row[2].abs().max()),max_abs_action_sensitivity=float(row[3].abs().max()))
                  for source,row in jac.items()})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest="cmd",required=True)
    reg=subs.add_parser("register")
    reg.add_argument("--recipe",required=True,type=Path)
    reg.add_argument("--dt-ms",required=True,type=float)
    reg.add_argument("--identity",required=True)
    t=subs.add_parser("train")
    t.add_argument("--arm",choices=("C20","rebase"),required=True)
    t.add_argument("--start",type=int,required=True)
    t.add_argument("--stop",type=int,required=True)
    subs.add_parser("probe-reused-control")
    subs.add_parser("inspect-archived")
    args=parser.parse_args()
    torch.manual_seed(0)
    torch.set_float32_matmul_precision("highest")
    if args.cmd=="register":
        print(json.dumps(args_identity(args)),flush=True)
    elif args.cmd=="train":
        train(args)
    else:
        probe_control(args.cmd=="inspect-archived")


if __name__=="__main__":
    main()
