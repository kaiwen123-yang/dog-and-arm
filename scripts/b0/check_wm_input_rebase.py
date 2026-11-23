"""Replay an actual standard collection batch and test preservation of the frozen WM function."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from supermimic.learners.wm_learner import WorldModelLearner
from supermimic.models import Dynamics

from learning.b0.contact_model import ContactRepresentation, ContactWorldModelCfg, contact_context, contact_state
from learning.b0.contact_training import rebase_wm_input_layer, wm_input_coordinates
from learning.b0.model import tensor
from learning.b0.physics import ActionMap, make_model


@torch.no_grad()
def check(run, cohort):
    cfg = json.loads((run / "actual_config.json").read_text())["cfg"]
    wm = torch.load(cfg["wm_checkpoint"], map_location="cpu", weights_only=False)
    model = make_model()
    mapping = ActionMap(model)
    rep = ContactRepresentation(model, "cpu")
    dyn = Dynamics(rep, 23, 5, tensor(mapping.scale, "cpu"), tensor(mapping.offset, "cpu"), tuple(cfg["wm_hidden"]))
    dyn.load_state_dict(wm["dyn"])
    learner = WorldModelLearner(dyn, rep, ContactWorldModelCfg(batch_size=cfg["wm_batch"]), "cpu")
    dyn.eval()
    def read(name):
        return torch.from_numpy(np.load(cohort / f"{name}.npy"))
    valid = read("valid")
    q = read("qpos")
    v = read("qvel")
    state = contact_state(q, v)
    action = read("clipped")
    refs = [Path(cfg["reference_directory"]) / name for name in cfg["references"]]
    boundaries = np.cumsum([1 + int(np.load(p / "valid_full_interval.npy").sum()) for p in refs])
    ids = np.searchsorted(boundaries, read("frame")[valid].numpy(), side="right")
    ctx = torch.stack([contact_context(model, json.loads((p / "metadata.json").read_text())["task"], "cpu") for p in refs])[ids]
    physical = rep.represent(state[valid])
    aux = state[valid][:, :7]
    a = action[valid]

    def outputs():
        first_inputs = torch.cat((dyn.state_normalizer(physical), dyn.action_normalizer(dyn.proc(a)), ctx), -1)
        root, represented = dyn(physical, a, aux, ctx)
        tcp, _ = rep.tcp_pose(root, represented[:, 10:34])
        return dict(first_preactivation=dyn.mlp[0](first_inputs), predicted_aux=root,
                    predicted_representation=represented, tcp_m=tcp, hinge_rad=represented[:,58])

    before = outputs()
    coords = wm_input_coordinates(dyn)
    context_weight = dyn.mlp[0].weight[:, rep.rep_state_dim+23:].clone()
    for k, mask in enumerate(valid):
        if mask.any():
            learner.update_normalization(state[k,mask], action[k,mask])
    stats_only = outputs()
    rebase_wm_input_layer(dyn, coords)
    corrected = outputs()
    torch.testing.assert_close(context_weight, dyn.mlp[0].weight[:, rep.rep_state_dim+23:], atol=0., rtol=0.)
    def change(sample):
        return {key: dict(max_absolute_component=float((value-before[key]).abs().max()),
                          rmse=float((value-before[key]).square().mean().sqrt())) for key,value in sample.items()}
    for key in ("predicted_aux", "tcp_m", "hinge_rad"):
        torch.testing.assert_close(corrected[key], before[key], atol=1e-5, rtol=1e-6)
    return dict(run=str(run), cohort=str(cohort), wm=cfg["wm_checkpoint"], valid_states=int(valid.sum()),
                control_steps=valid.shape[0], lanes=valid.shape[1], precision="CPU float32",
                optimizer_steps=0, processed_columns=[rep.rep_state_dim,23], unchanged_context_columns=ctx.shape[-1],
                state_eps=dyn.state_normalizer.eps, action_eps=dyn.action_normalizer.eps,
                stats_only_vs_frozen=change(stats_only), stats_and_affine_vs_frozen=change(corrected))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "cohort", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    summary = check(args.run, args.cohort)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    print(json.dumps(summary))
