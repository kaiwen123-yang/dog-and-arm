"""Evaluate the original finger position/velocity tradeoff on measured 20 ms windows."""
import argparse
import json

import yaml
from pathlib import Path

import numpy as np
import torch

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg, contact_context
from learning.b0.contact_replay import ContactEpisode
from scripts.b0.score_temporal_wm import validation_episodes
from scripts.b0.train_temporal_pair import RAW as WEIGHTS

OUT = Path("results/b0/standard_dynamics_20261124")
RAW = Path("results/raw_large/b0/dynamics_20261124")
DEVICE = "cuda:0"


def fixed_validation(model, rep, recipe, response_registration, response_dir):
    rows = json.loads((Path("results/b0/lanes_wm_v1") / "config.json").read_text())["sources"]
    for item in rows:
        if item["split"] == "validation":
            yield "native", ContactEpisode.read(item["path"], DEVICE)
    sources = [(name,str(Path(recipe[name]["directory"]).resolve())) for name in ("grip","multimode")]
    for source, folder in sources:
        for ep in validation_episodes(folder, model, rep, DEVICE):
            yield source, ep
    for row in json.loads(response_registration.read_text())["starts"]:
        if row["split"] != "validation":
            continue
        folder = response_dir / row["id"]
        rec = json.loads((folder / "receipt.json").read_text())
        if rec.get("rejected"):
            continue
        with np.load(folder / "dynamics.npz") as d:
            state = torch.as_tensor(d["state"], device=DEVICE)
            action = torch.as_tensor(d["action"], device=DEVICE)
            valid = d["valid"]
        for i, label in enumerate(rec["labels"]):
            if label[1] == "repeat":
                continue
            ep = ContactEpisode(folder, row["id"] + f"/b{i}", "validation", row["side"],
                                state[:, i], action[:, i], contact_context(model, row["side"], DEVICE),
                                valid[:, i], np.full(len(valid), "unused"))
            yield "response", ep


def summary(values):
    return {k: dict(n=len(x), median_signed=float(np.median(x)), p95_abs=float(np.percentile(abs(x), 95)),
                    rms=float(np.sqrt(np.mean(x*x))), max_abs=float(abs(x).max()))
            for k, x in values.items()}


@torch.no_grad()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current",action="store_true",help="Score the locked training physical identity and its matched +1000 control.")
    args=parser.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    from scripts.b0.dynamics_c20_pair import build, checkpoint, load_registration, model_and_rep, new_wm
    if args.current:
        info = load_registration()
        recipe_path = Path(info["data_recipe"])
        cp = checkpoint(info,"C20",1000)
        model,rep = model_and_rep(info["physics_dt"])
        identity = info["physics_identity"]
        tag = "matched_c20"
    else:
        from scripts.b0.train_temporal_pair import RECIPE
        recipe_path = RECIPE
        cp = WEIGHTS / "C20/wm_001000.pt"
        model,rep = model_and_rep(.002)
        identity = "historical Warp 2ms + registered native"
        tag = "old_2ms"
    recipe_cfg = yaml.safe_load(recipe_path.read_text())
    sources = recipe_cfg["wm_data_recipe"]["sources"]
    response_dir = Path(sources["response"]["raw"])
    response_registration = Path(sources["response"]["registration"])
    cfg = ContactWorldModelCfg()
    dyn = new_wm(model,rep,torch.load(cp,map_location="cpu",weights_only=False)).eval()
    torch.set_float32_matmul_precision("highest")
    pool = build(recipe_cfg,model,rep)
    train = [(name, ep) for name in ("native", *pool.recipe["sources"])
             for ep in pool.pools[name, 1].episodes]
    eps = train + list(fixed_validation(model,rep,sources,response_registration,response_dir))
    a = rep.dt * rep.substep_coeff
    qscale, vscale = cfg.nominal_error_finger_pos, cfg.nominal_error_finger_vel
    ratio = 1 / (1 + (a*vscale/qscale)**2)
    groups, episodes, samples, hold = {}, [], [], {}
    for id_ep, (source, ep) in enumerate(eps):
        group = (ep.split, source, ep.side)
        inds = ep.starts(1)
        if not len(inds):
            continue
        if ep.split == "train" and not any(ep is e for e in pool.pools[source, 1].episodes):
            raise ValueError("Unexpected train identity")
        ix = torch.as_tensor(inds, device=DEVICE)
        x, y = ep.state[ix], ep.state[ix+1]
        aux, r = dyn(rep.represent(x), ep.action[ix], x[:, :7], ep.context.expand(len(ix), -1))
        z = rep.reconstruct_full_state(aux, r)
        q0, v0 = [x[:, sl].double() for sl in (slice(29,31), slice(59,61))]
        q1, v1 = [y[:, sl].double() for sl in (slice(29,31), slice(59,61))]
        residual = q0 + rep.dt*v0 + a*(v1-v0) - q1
        ev = z[:, 59:61].double() - v1
        eq = z[:, 29:31].double() - q1
        ev_opt = -a*residual / (a*a + (qscale/vscale)**2)
        eq_opt = residual * ratio
        err = (residual + a*ev - eq).abs().max().item()
        if err > 1e-6:
            raise ValueError(f"Finger closure {err} m at {ep.group}")
        blocks = {"residual_m":residual, "model_v_error_m_s":ev, "model_q_error_m":eq,
                  "component_optimal_v_error_m_s":ev_opt, "component_optimal_q_error_m":eq_opt}
        nums = {}
        for name, val in blocks.items():
            for j in (0, 1):
                nums[name+f"_finger{j+1}"] = val[:, j].cpu().numpy()
            nums[name+"_opening"] = (val[:, 0]-val[:, 1]).cpu().numpy()
        groups.setdefault(group, []).append(nums)
        episodes.append(dict(id=id_ep, split=ep.split, source=source, side=ep.side, group=ep.group, path=str(ep.path)))
        samples.append(dict(episode=np.full(len(ix), id_ep, dtype=np.int32),
                            physical_input_index=inds.astype(np.int32), **nums))
        if ep.split == "validation" and source == "response" and inds[0] == 0:
            rec = json.loads((ep.path/"receipt.json").read_text())
            lane = int(ep.group.rsplit("/b", 1)[-1])
            if rec["row"]["phase"]=="hold" and rec["labels"][lane][:2]==["u0", "actor"]:
                hold[ep.side] = {key:float(val[0]) for key,val in nums.items() if key.endswith("_opening")}
    archive = RAW / f"{tag}_finger_component_tradeoff.npz"
    np.savez_compressed(archive, **{key:np.concatenate([s[key] for s in samples]) for key in samples[0]})
    (RAW / f"{tag}_tradeoff_episodes.json").write_text(json.dumps(episodes))
    reduced = {"/".join(group):summary({k:np.concatenate([row[k] for row in members]) for k in members[0]})
               for group,members in groups.items()}
    report = dict(physics=identity, dt=rep.dt, c=rep.substep_coeff,
                  formula="residual=q0+dt*v0+dt*c*(v1-v0)-q1; eq=residual+dt*c*ev",
                  scales=dict(position_m=qscale, velocity_m_s=vscale), component_optimal_residual_fraction=ratio,
                  meaning="Independent unconstrained two-term finger position/velocity quadratic at its free terminal velocity; excludes all other channels and cross-time losses.",
                  population="One row per legal episode-local H1 input, including valid full first terminal intervals. Repeats, invalid intervals and subsequent terminal tails excluded.",
                  prediction_checkpoint=str(cp), per_sample=str(archive), episode_keys=str(RAW/f"{tag}_tradeoff_episodes.json"),
                  sample_count=sum(len(s["episode"]) for s in samples), groups=reduced, validation_hold_u0=hold)
    (OUT / f"{tag}_finger_component_tradeoff.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps(dict(n=report["sample_count"], fraction=ratio, hold=hold)), flush=True)


if __name__ == "__main__":
    main()
