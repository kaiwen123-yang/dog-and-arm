"""Fit a fixed-clock, approach-only residual to measured perturbed wheel targets."""
import argparse
import json
from pathlib import Path

import torch
from supermimic.tasks.task_spec import build_actor_obs_td

from learning.b0.contact_policy import APPROACH_WHEEL, DoorMotions, ReferenceResidualActor, build_actor
from learning.b0.model import RobotRepresentation
from learning.b0.physics import make_model
from scripts.b0.recovery_bc import ANCHOR, AUGMENT, DESIGN, REF, REFERENCE, dump, episode, merge, migrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if Path(args.run).name != args.run:
        parser.error("Expected a fresh run name")
    out = Path("results/b0") / args.run
    out.mkdir(exist_ok=False)
    device = "cuda:0"
    torch.manual_seed(231123)
    torch.set_float32_matmul_precision("highest")
    frozen = torch.load(ANCHOR, weights_only=False, map_location="cpu")
    cfg = dict(frozen["cfg"], actor_goal_schema=APPROACH_WHEEL, reference_directory=str(REFERENCE),
               additional_bc_run=args.run)
    model = make_model()
    rep = RobotRepresentation(model, device)
    bank = DoorMotions([REFERENCE / name for name in REF.values()], rep, device, actor_schema=APPROACH_WHEEL)
    actor, _ = build_actor(rep, cfg, model, device)
    migrate(frozen["actor"], actor)
    actor.eval().requires_grad_(False)
    actor.wheel_feedback.requires_grad_(True)
    groups = {"train": [], "validation": []}
    frames = {}
    with torch.no_grad():
        for case in json.loads(DESIGN.read_text())["cases"]:
            path = AUGMENT / case["episode_id"]
            g, h, act = episode(path, case["split"], bank, rep, device)
            active = g[:, -1].bool()
            g, h, act = g[active], h[active], act[active]
            obs = build_actor_obs_td({"motion": g}, h)
            x, gate = actor.wheel_inputs(obs)
            baseline = ReferenceResidualActor.raw(actor, obs)[:, 12:16]
            residual = (act[:, 12:16] - baseline) * 6
            frames[path.name] = len(x)
            groups[case["split"]].append((x, gate, residual))
    train = merge(groups["train"])
    val = merge(groups["validation"])
    def error(data):
        x, gate, y = data
        return (gate * actor.wheel_feedback(x) - y).square().mean()
    initial = error(val).detach().sqrt().item()
    optimizer = torch.optim.Adam(actor.wheel_feedback.parameters(), lr=.002)
    for step in range(1200):
        ix = torch.randint(len(train[0]), (128,), device=device)
        optimizer.zero_grad(set_to_none=True)
        loss = error([a[ix] for a in train])
        loss.backward()
        optimizer.step()
    dump(out / "actual_config.json", dict(source=str(ANCHOR), cfg=cfg, updates=1200, h32_updates=0,
            fitting="final iterate Adam .002, sample 128 in same-phase reference approach; axes x,y,yaw, reference lookahead, yaw rate, previous wheel actions and reference wheel velocities",
            architecture="frozen original Actor, zero-initialized final layer of 9-32-32-4 wheel residual in rad/s, fixed 1mm and .002rad nominal deadband; no intervention outside reference approach",
            episode_frames=frames, train_rmse_rad_s=error(train).detach().sqrt().item(),
            validation_before_rad_s=initial, validation_after_rad_s=error(val).detach().sqrt().item()))
    torch.save(dict(frozen, cfg=cfg, actor=actor.state_dict(), source=str(ANCHOR),
                    additional_bc_updates=1200, additional_bc_variant="approach_wheel_residual"),
               out / "checkpoint_000000.pt")
    torch.save(dict(optimizer=optimizer.state_dict(), rng=torch.cuda.get_rng_state(), step=1200),
               out / "bc_optimizer_rng.pt")


if __name__ == "__main__":
    main()
