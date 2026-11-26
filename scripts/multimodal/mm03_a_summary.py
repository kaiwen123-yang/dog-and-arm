"""Publish compact channel-rescue evidence and verify the legacy L16 transfer."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from scripts.multimodal.mm03_a import emit


def summary(root):
    base = root/"A"
    rescue = []
    for path in sorted((base/"rescue").glob("*/result.json")):
        r = json.loads(path.read_text())
        logfile = path.parent/"physics_2ms"/"wheel_normal_n.npy"
        normal = np.load(logfile, mmap_mode="r")
        rescue.append({k:r[k] for k in ("id", "side", "goal", "source", "variant", "branch", "success",
            "events", "first_failure", "teacher_failure", "teacher_query_steps", "executor_source_mask",
            "physics_steps", "decisions", "checkpoint_sha256", "wheel_order",
            "unsupported_samples", "max_incomplete_support_s", "self_collision_points")} |
            dict(last_50_steps_below_1N=(normal[-50:]<1.).sum(0).tolist(),
                 last_wheel_normal_n=normal[-1].tolist(), physics_log=str(logfile.parent),
                 raw_episode=str(path.parent/"episode"), result=str(path)))
    if len(rescue)!=44:
        raise ValueError("Channel-rescue table requires all 44 completed native trials")
    cells = []
    for branch, variant in sorted({(r["branch"],r["variant"]) for r in rescue}):
        group = [r for r in rescue if r["branch"]==branch and r["variant"]==variant]
        cells.append(dict(branch=branch, variant=variant, n=len(group), success=sum(r["success"] for r in group),
                          completed_settle=sum(len(r["events"])>=2 for r in group),
                          first_failure=dict(Counter((r["first_failure"] or {}).get("reason", "success") for r in group))))
    cmd = [json.loads(f.read_text()) for f in sorted((base/"command_teacher").glob("*/result.json"))]
    if len(cmd)!=96:
        raise ValueError("Command baseline requires all 96 planned trials")
    key = ("scene", "side", "goal", "arm", "gain", "command", "stop_s")
    by_condition = {tuple(r[k] for k in key):r for r in cmd}
    design = json.loads((base/"design.json").read_text())
    dev = [by_condition[cond] for r in design["development_design"] if (cond:=tuple(r[k] for k in key)) in by_condition]
    adapter = []
    for f in sorted((root/"B"/"teachers").glob("teacher_26112600_tr_nominal_*/result.json")):
        x = json.loads(f.read_text())
        adapter.append(dict(id=x["id"], success=x["success"], events=len(x["events"]), physics_steps=x["physics_steps"],
                            source=str(f), counted_in="B complete teacher collection"))
    parity_path = base/"cpu_parity"/"comparison.json"
    emit(base/"channel_results.json", dict(
        schema="MM03-A-channel-interventions-v1", cases=rescue, grouped=cells,
        physical_steps=sum(r["physics_steps"] for r in rescue),
        cpu_repeat=json.loads(parity_path.read_text()) if parity_path.is_file() else None,
        nominal_local_adapter_reference=adapter,
        comparison_scope="MM03 batched GPU equal-condition channel intervention; CPU-policy repeat is additional",
        normal_window="solved last 50 intervals before original scorer terminates; wheel order FAR,FBL,RAR,RBL"))
    emit(base/"command_reference.json", dict(cases=cmd, successes=sum(r["success"] for r in cmd),
         physical_steps=sum(r["physics_steps"] for r in cmd), total_rows=sum(r["decisions"] for r in cmd),
         eligible_bc_rows=sum(r["eligible_rows"] for r in cmd),
         exact_development_condition_overlap=[dict(id=r["id"], success=r["success"]) for r in dev],
         matched_development_successes=sum(r["success"] for r in dev), matched_development_cases=len(dev),
         maximum_teacher_successes_out_of_40_from_observed_failures=40-sum(not r["success"] for r in dev)))


def transfer(root):
    import torch
    from learning.multimodal.mm03_low import LowPolicy
    from scripts.multimodal.mm03_a_train import causal_features
    torch.set_num_threads(1)
    source = next(iter(sorted((root/"A"/"command_teacher").glob("*forward_left_stop*/result.json")))).parent
    p = np.load(source/"proprio.npy")
    prev = np.load(source/"previous.npy")
    cmd = np.load(source/"command.npy")
    indices = np.linspace(0, len(p)-1, 128).astype(int)
    samples = torch.tensor(causal_features(p, prev)[indices], device="cuda")
    rates = torch.tensor(cmd[indices], device="cuda")
    checks = []
    for seed in (1701, 1702, 1703):
        full = root/"A"/"low"/f"seed{seed}"/"block0"/"latest.pt"
        ck = torch.load(full, map_location="cpu", weights_only=False)
        assert not any(k.startswith("stationary.") for k in ck["model"])
        model = LowPolicy().cuda()
        assert model.inherit(ck["model"])
        with torch.no_grad():
            z = ((samples-model.feature_mean)/model.feature_std).clamp(-8., 8.)
            est = model.estimator(z)*model.velocity_units
            request = rates/model.velocity_units
            out = model.control(torch.cat((z, request, est/model.velocity_units), dim=-1))
            prev16 = samples[:, 104:120]
            gate = (request.abs().sum(-1, keepdim=True)+8*prev16[:, 12:].abs().mean(-1, keepdim=True)).clamp(max=1.)
            reference = torch.cat((prev16[:, :12]+gate*out[:, :12]*model.leg_increment_scale,
                                   request[:, :1]*out[:, 12:16]+request[:, 1:]*out[:, 16:20]), -1).clamp(-1, 1)
            actual, _ = model.from_features(samples, rates)
            err = float((actual-reference).abs().max())
            assert torch.equal(actual, reference)
            reload = LowPolicy.load(full, "cuda")
            assert all(torch.equal(v, reload.state_dict()[k]) for k,v in model.state_dict().items())
        zero = samples.clone()
        zero[:, 116:120]=0
        legs, _ = model.from_features(zero, torch.zeros_like(rates))
        grad = torch.autograd.grad(legs[:, :12].sum(), model.stationary[-1].weight)[0]
        assert grad.norm().item()>0
        old_opt = ck["optimizer"]
        opt = torch.optim.Adam(model.parameters(), lr=.0004)
        ids = opt.state_dict()["param_groups"][0]["params"]
        assert old_opt["param_groups"][0]["params"] == ids[:-4]
        old_opt["param_groups"][0]["params"]=ids
        opt.load_state_dict(old_opt)
        now = opt.state_dict()
        assert set(now["state"].keys())==set(old_opt["state"].keys())
        for idx in now["state"]:
            for key, val in now["state"][idx].items():
                assert torch.equal(val.cpu(), old_opt["state"][idx][key].cpu())
        checks.append(dict(seed=seed, old_checkpoint=str(full), update=ck["update"], sample_count=len(indices),
                           max_absolute_output_difference=err, same_embedded_reload=True,
                           zero_command_stationary_head_gradient_norm=grad.norm().item(),
                           inherited_Adam_states=len(now["state"]), added_Adam_states_before_update=0,
                           old_trained_parameters=sum(v.numel() for k,v in model.named_parameters() if not k.startswith("stationary.")),
                           expanded_trainable_parameters=sum(v.numel() for v in model.parameters())))
    emit(root/"A"/"low"/"compatibility.json", dict(checks=checks, source=str(source), rows=indices.tolist(),
         physics_steps=0, optimizer_updates=0, architecture="old 20-output head intact; additional leg feedback residual, stateless causal features"))


def low_scores(root):
    """Read the causal velocity estimator against complete physical development trials."""
    import torch
    from learning.multimodal.mm03_low import LowPolicy
    from scripts.multimodal.mm03_a_train import causal_features
    torch.set_num_threads(1)
    low = root/"A"/"low"
    packages = []
    result_path = low/"development_results.json"
    saved = json.loads(result_path.read_text())["packages"] if result_path.exists() else []
    complete = {x["deploy"]:x for x in saved if x["dev_total"]==40}
    for deploy in sorted(low.glob("seed*/block*/deploy.pt")):
        if str(deploy) in complete:
            packages.append(complete[str(deploy)])
            continue
        files = sorted((deploy.parent/"development").glob("*/result.json"))
        if len(files)!=40:
            continue
        model = LowPolicy.load(deploy, "cuda")
        rows, measures = [], {}
        for f in files:
            result = json.loads(f.read_text())
            p = np.load(f.parent/"proprio.npy")
            prev = np.load(f.parent/"previous.npy")
            true = np.load(f.parent/"velocity.npy")
            rates = np.load(f.parent/"command.npy")
            with torch.inference_mode():
                x = torch.tensor(causal_features(p, prev), device="cuda")
                z = ((x-model.feature_mean)/model.feature_std).clamp(-8., 8.)
                estimated = (model.estimator(z)*model.velocity_units).cpu().numpy()
            diff = estimated.astype(np.float64)-true
            motion = np.any(abs(rates)>0., axis=1)
            for group, mask in (("all", np.ones(len(p), dtype=bool)), ("moving_request", motion),
                                ("stopped_request", ~motion), ("arm_moving", np.max(abs(p[:, 39:45]), axis=1)>.01)):
                n, e, sq = measures.get(group, (0, np.zeros(2), np.zeros(2)))
                measures[group] = (n+int(mask.sum()), e+np.abs(diff[mask]).sum(0), sq+np.square(diff[mask]).sum(0))
            # Earlier stop/recovery followed by another disturbance is outside this measure.
            delay = (max(0., result["duration_s"]-result["stable_at_end_s"]-result["stop_s"])
                     if result["stable_at_end_s"]+1e-9 >= 1. else None)
            rows.append(dict(id=result["id"], scene=result["scene"], arm=result["arm"], command=result["command"],
                       success=result["success"], first_failure=result["first_failure"], physics_steps=result["physics_steps"],
                       supported_fraction=result["all_supported_fraction"], min_wheel_load_n=result["minimum_wheel_load_n"],
                       max_incomplete_support_s=result["max_incomplete_support_s"], last_second_peak_speed_m_s=result["last_second_peak_speed_m_s"],
                       final_sustained_settle_delay_from_stop_s=delay, max_stop_drift_m=result["max_stop_drift_m"],
                       median_velocity_to_command_vx_wz=result["median_motion_velocity_to_request_vx_wz"],
                       estimator_mae=np.abs(diff).mean(0).tolist(), estimator_rmse=np.sqrt(np.square(diff).mean(0)).tolist()))
        groups = {name:dict(rows=n, mae=(e/n).tolist(), rmse=np.sqrt(sq/n).tolist()) for name,(n,e,sq) in measures.items() if n}
        packages.append(dict(deploy=str(deploy), seed=result["seed"], block=result["block"],
                             dev_success=sum(r["success"] for r in rows), dev_total=len(rows), estimator_error=groups, cases=rows))
    emit(result_path, dict(packages=packages, estimator_error_units=["body-forward m/s", "vertical rad/s"],
         sample_clock="20ms actual development observations, including failures, same causal state/action window as deployment",
         arm_moving_definition="any actual arm joint speed exceeds 0.01 rad/s", extra_optimizer_updates=0,
         physical_steps=0, offline_estimator_evaluations=sum(g["estimator_error"]["all"]["rows"] for g in packages)))


def budget(root):
    base = root/"A"
    groups = {}
    def count(name, items):
        rows = [json.loads(p.read_text()) for p in sorted(items) if not p.parent.name.startswith(".")]
        groups[name] = dict(cases=len(rows), successes=sum(r["success"] for r in rows),
                            decisions=sum(r["decisions"] for r in rows), physics_steps=sum(r["physics_steps"] for r in rows))
    count("rescue44", (base/"rescue").glob("*/result.json"))
    count("command_reference96", (base/"command_teacher").glob("*/result.json"))
    count("independent_cpu_repeat", (base/"cpu_parity").glob("*/result.json"))
    for seed_root in sorted((base/"low").glob("seed*")):
        for block in sorted(seed_root.glob("block*")):
            for stage in ("development","correction","oracle"):
                path = block/stage
                if path.exists():
                    count(f"{seed_root.name}/{block.name}/{stage}", path.glob("*/result.json"))
    training = [json.loads(f.read_text()) for f in sorted((base/"low").glob("seed*/block*/train_result.json"))]
    failed = []
    for f in sorted(base.rglob("exception.json")):
        x = json.loads(f.read_text())
        steps = x.get("completed_physics_steps")
        reason = x["traceback"].strip().splitlines()[-1]
        # The old 20-output model could never be bound by the briefly deployed
        # 32-output loader, so those native workers failed at their first request.
        first_query = (steps is None and "size mismatch for control.4.bias" in x["traceback"]
                       and "in run_command" in x["traceback"])
        failed.append(dict(source=str(f), steps=0 if first_query else steps,
                           reason=reason, proof="initial inference could not load model" if first_query else "saved attempt counter"))
    off = base/"low"/"development_results.json"
    scores = json.loads(off.read_text()) if off.exists() else {}
    known_extra = sum(x["steps"] for x in failed if x["steps"] is not None)
    unknown = sum(x["steps"] is None for x in failed)
    emit(base/"budget.json", dict(groups=groups, training_blocks=training, failed_native_attempts=failed,
         completed_scored_cases=sum(g["cases"] for g in groups.values()),
         completed_physics_steps=sum(g["physics_steps"] for g in groups.values()),
         failed_attempt_physics_steps_known=known_extra, failed_attempts_without_substep_counter=unknown,
         bc_updates=sum(x["updates"] for x in training), bc_samples=sum(x["bc_rows"] for x in training),
         offline_estimator_evaluations=scores.get("offline_estimator_evaluations",0),
         additional_shared_B_adapter_episodes_charged_to_A=0, hardware_motion_commands=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--transfer", action="store_true")
    parser.add_argument("--low-scores", action="store_true")
    parser.add_argument("--budget", action="store_true")
    args = parser.parse_args()
    (transfer if args.transfer else low_scores if args.low_scores else budget if args.budget else summary)(args.root)
