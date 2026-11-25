"""Fit one corrected arm-hold candidate on the common student's own approach states."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import torch
import torch.nn.functional as F

from learning.multimodal.actor import load_actor
from learning.multimodal.dataset import EpisodeDataset
from scripts.multimodal.train_actor import atomic_json, atomic_save, bc_objective, peak, synchronize


ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "config/multimodal/approach_repair.json"
ARM = slice(16, 22)
J2 = 17


def read(path):
    return json.loads(path.read_text())


def load(path, field):
    return np.load(path / f"{field}.npy", mmap_mode="r", allow_pickle=False)


def phase_rows(path, meta):
    return np.flatnonzero(load(path, "valid_transition") &
                          (load(path, "phase") == meta["phases"].index("approach_base")))


def j2_drift(path, rows, home):
    cmd, prop = load(path, "physical_target"), load(path, "proprio")
    t = load(path, "t")
    q = prop[rows, J2]
    u = cmd[rows, J2]
    return dict(rows=len(rows), approach_last_valid_end_s=float(t[rows[-1]+1]),
                j2_command_p95_abs_error_rad=float(np.quantile(np.abs(u-home), .95)),
                j2_measured_p95_abs_error_rad=float(np.quantile(np.abs(q-home), .95)),
                j2_command_min_max_rad=[float(u.min()), float(u.max())],
                j2_state_min_max_rad=[float(q.min()), float(q.max())],
                last_valid_successor_j2_rad=float(prop[rows[-1]+1, J2]),
                samples=[dict(t_s=float(t[k]), physical_command_rad=float(cmd[k, J2]),
                              measured_rad=float(prop[k, J2])) for k in (0,100,200,250,350,500,750)
                         if k in rows])


def inspect_sources(root, spec):
    out = {}
    for identity in spec["feedback_ids"]:
        path = root/"data"/identity
        meta = read(path/"metadata.json")
        if (meta["source"] != "MM01_frozen_common_12000" or meta["split"] != "train"
                or meta["scene_id"] != "tr_nominal" or meta["checkpoint_sha256"] != spec["parent_sha256"]
                or load(path, "action_supervision_mask").any()):
            raise ValueError(f"Incorrect feedback source or inherited expert label in {identity}")
        demo_id = f"tr_nominal_{meta['side']}_{meta['target_deg']}_held"
        demo = root/"data"/demo_id
        teacher = read(demo/"metadata.json")
        if teacher["source"] != "P6_held_20ms" or not teacher["success"] or teacher["split"] != "train":
            raise ValueError(demo_id)
        teacher_rows = phase_rows(demo, teacher)
        rows = phase_rows(path, meta)
        target = load(demo, "physical_target")[teacher_rows, 16:23]
        home = load(demo, "proprio")[0, 16:23]
        if not np.allclose(target, home, atol=1e-6, rtol=0):
            raise ValueError(f"Teacher hold target changed inside approach in {demo_id}")
        channels = meta["action_channels"][16:22]
        physical = home[:6]
        normalized = (physical-np.array([c["offset"] for c in channels]))/np.array([c["scale"] for c in channels])
        if not np.allclose(normalized, load(demo, "action_clipped")[teacher_rows, ARM], atol=1e-6):
            raise ValueError(f"Action units differ in {demo_id}")
        if not len(rows) or load(path, "contact")[rows].max() > .01:
            raise ValueError(f"Contact occurred during approach in {identity}")
        out[identity] = dict(teacher_episode=demo_id, teacher_arm_and_full_jaw_home=home.tolist(),
                             normalized_arm_target=normalized.tolist(),
                             max_observed_teacher_command_deviation_from_home=float(np.max(np.abs(target-home))),
                             common_parent=j2_drift(path, rows, float(home[1])),
                             p6_teacher=j2_drift(demo, teacher_rows, float(home[1])))
    return out


def train(root, output, spec, reg, resume):
    torch.set_num_threads(1)
    torch.set_float32_matmul_precision("high")
    torch.manual_seed(spec["seed"])
    device = torch.device("cuda:0")
    torch.cuda.set_device(device)
    torch.cuda.reset_peak_memory_stats(device)
    parent = root/spec["parent_path"]
    if hashlib.sha256(parent.read_bytes()).hexdigest() != spec["parent_sha256"]:
        raise ValueError("The parent checkpoint changed")
    actor, vocab, full = load_actor(resume or parent, device)
    membership = full["membership"]
    if membership != read(ROOT/"config/multimodal/actor_run.json")["membership"]:
        raise ValueError("The inherited expert split changed")
    original = EpisodeDataset(root/"data", "train", vocab, device, membership["train"])
    feedback = EpisodeDataset(root/"data", "train", vocab, device, spec["feedback_ids"])
    valid_rows, early_rows, targets = [], [], []
    for start, (path, meta) in zip(feedback.starts, feedback.episodes):
        rows = phase_rows(path, meta)
        valid_rows.extend(start + rows)
        early_rows.extend(start + rows[load(path, "t")[rows] <= spec["feedback_early_seconds"]])
        targets.append(reg["feedback_labels"][meta["episode_id"]]["normalized_arm_target"])
    targets = torch.tensor(targets, dtype=torch.float32, device=device)
    valid_rows, early_rows = np.asarray(valid_rows), np.asarray(early_rows)
    actor.freeze_encoders()
    actor.train()
    opt = torch.optim.AdamW(actor.parameters(), lr=spec["lr"], weight_decay=spec["weight_decay"])
    opt.load_state_dict(full["optimizer"])
    for group in opt.param_groups:
        group["lr"] = spec["lr"]
    rng = np.random.default_rng(spec["seed"])
    start, previous_elapsed, records = 0, 0., []
    if resume:
        if full["configuration"]["repair_registration"] != reg:
            raise ValueError("Resume checkpoint belongs to a different registration")
        start, records = full["update"], full["updates"]
        rng.bit_generator.state = full["sampler_state"]
        previous_elapsed = records[-1]["elapsed_s"]
    if (output/"final.pt").exists():
        raise FileExistsError(output/"final.pt")
    configuration = dict(repair_registration=reg, old_train_episodes=original.episode_ids,
                         expert_rows=len(original.expert_rows), auxiliary_rows=len(valid_rows),
                         auxiliary_early_rows=len(early_rows), torch_version=torch.__version__)
    atomic_json(output/"configuration.json", configuration)
    sums = torch.zeros(3, device=device)
    synchronize(device)
    begin = time.perf_counter()
    since = 0
    for step in range(start+1, spec["updates"]+1):
        old_batch = original.sample(spec["expert_batch"], rng)
        half = spec["feedback_batch"] // 2
        indices = np.r_[rng.choice(valid_rows, spec["feedback_batch"]-half), rng.choice(early_rows, half)]
        indices = torch.as_tensor(indices, device=device)
        auxiliary = feedback.batch_rows(indices)
        original_loss = bc_objective(actor, actor(old_batch), old_batch["action"])
        target = targets[feedback.states["episode"][indices]]
        residual = (actor(auxiliary)[:, ARM] - target) / actor.residual_std[ARM]
        correction = F.smooth_l1_loss(residual, torch.zeros_like(residual), beta=.5)
        loss = original_loss + spec["auxiliary_weight"] * correction
        opt.zero_grad(set_to_none=True)
        loss.backward()
        norm = torch.nn.utils.clip_grad_norm_(actor.parameters(), 2., error_if_nonfinite=True)
        opt.step()
        sums += torch.stack((original_loss.detach(), correction.detach(), norm.detach()))
        since += 1
        if step % 200 == 0 or step == spec["updates"]:
            synchronize(device)
            old, aux, grad = (sums/since).cpu().tolist()
            elapsed = time.perf_counter()-begin+previous_elapsed
            records.append(dict(update=step, elapsed_s=elapsed, expert_loss=old, auxiliary_arm_loss=aux,
                                gradient_norm=grad, **peak(device)))
            print(json.dumps(records[-1]), flush=True)
            sums.zero_()
            since = 0
        if step % spec["save_every"] == 0 or step == spec["updates"]:
            checkpoint = dict(schema=full["schema"], actor=actor.state_dict(), vocabulary=vocab.tokens,
                              optimizer=opt.state_dict(), membership=membership, configuration=configuration,
                              update=step, inherited_actor_updates=12000, updates=records,
                              sampler_state=rng.bit_generator.state)
            atomic_save(output/("final.pt" if step == spec["updates"] else f"step_{step:06}.pt"), checkpoint)
            atomic_json(output/"progress.json", dict(update=step, updates=records))


def score(root, output, spec):
    eval_spec = spec["evaluation"]
    candidate = output/"final.pt"
    checkpoint_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    cases = [(scene, side, goal) for scene in eval_spec["scenes"]
             for side in eval_spec["sides"] for goal in eval_spec["goals"]]
    def one_case(case):
        scene, side, goal = case
        identity = f"{spec['candidate']}_{scene}_{side}_{goal}"
        case_dir = root/"repair_cases"/identity
        if not (case_dir/"result.json").exists():
            cmd = [str(ROOT/".venv/bin/python"), "-m", "scripts.multimodal.evaluate", "--branch", spec["candidate"],
                   "--checkpoint", str(candidate), "--scene", scene, "--side", side, "--goal", str(goal),
                   "--actor-python", str(ROOT/".conda/envs/arm-and-dog/bin/python"),
                   "--output", str(root/"repair_cases"), "--first-video-dir", str(root/"videos/student")]
            with (root/"logs"/f"{identity}.log").open("a") as f:
                subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=True)
        result = read(case_dir/"result.json")
        if result["checkpoint_sha256"] != checkpoint_hash:
            raise ValueError(f"Different checkpoint already evaluated at {case_dir}")
        episode = Path(result["raw_episode"])
        rows = phase_rows(episode, read(episode/"metadata.json"))
        result["approach_j2"] = j2_drift(episode, rows, .8)
        print(json.dumps({k: result[k] for k in ("case_id", "success", "next_phase", "first_failure")}), flush=True)
        return result
    with ThreadPoolExecutor(max_workers=eval_spec["workers"]) as workers:
        results = list(workers.map(one_case, cases))
    atomic_json(output/"development_physics.json", dict(cases=len(results), full_successes=sum(r["success"] for r in results),
                checkpoint=str(candidate), sha256=checkpoint_hash, rows=results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["register","train","score"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    output = args.root/"approach_repair"
    output.mkdir(exist_ok=True)
    spec = read(SPEC)
    if args.stage == "register":
        receipt = output/"registration.json"
        if receipt.exists():
            raise FileExistsError(receipt)
        reg = dict(registered_at_beijing=datetime.now(timezone(timedelta(hours=8))).isoformat(), specification=spec,
                   feedback_labels=inspect_sources(args.root, spec),
                   source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        atomic_json(receipt, reg)
    elif args.stage == "train":
        reg = read(output/"registration.json")
        if reg["specification"] != spec:
            raise ValueError("The registered training recipe changed")
        train(args.root, output, spec, reg, args.resume)
    else:
        score(args.root, output, spec)


if __name__ == "__main__":
    main()
