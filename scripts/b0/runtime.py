"""Print the installed runtime and the CUDA devices used by the fixed sources."""
import argparse
import json
from importlib import metadata
from pathlib import Path
import platform
import subprocess
import sys

import torch
import warp as wp
from mjlab.sim import Simulation
from supermimic.envs.multi_task_world_model_env import MultiTaskWorldModelEnv
from supermimic.learners.policy_learner import ActorCriticPolicyLearner
from supermimic.learners.wm_learner import WorldModelLearner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save a JSON record of this runtime")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if Path(sys.prefix).resolve() != root / ".conda/envs/arm-and-dog":
        raise RuntimeError("Launch with bash scripts/b0/env.sh python scripts/b0/runtime.py")
    wp.init()
    gpu = torch.cuda.get_device_properties(0)
    # The policy uses fused Adam and Muon. Verify CUDA math through both optimizers.
    from supermimic.learners.learner_utils import build_optimizers

    torch.manual_seed(0)
    model = torch.nn.Sequential(
        torch.nn.Linear(4, 8), torch.nn.SiLU(), torch.nn.Linear(8, 8),
        torch.nn.SiLU(), torch.nn.Linear(8, 1)
    ).cuda()
    before = model[2].weight.detach().clone()
    optimizers = build_optimizers([model], 2e-4, device="cuda:0")
    model(torch.ones(2, 4, device="cuda")).sum().backward()
    for optimizer in optimizers:
        optimizer.step()
    delta = (model[2].weight - before).abs().max().item()
    if not (0 < delta < float("inf")):
        raise RuntimeError(f"Unexpected CUDA weight delta: {delta}")
    versions = {d.metadata["Name"].lower(): d.version for d in metadata.distributions()}
    record = {
        "conda_environment": "arm-and-dog",
        "python_prefix": sys.prefix,
        "warp_cache": wp.config.kernel_cache_dir,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "gpu": gpu.name,
        "torch_cuda_build": torch.version.cuda,
        "torch_device_capability": torch.cuda.get_device_capability(0),
        "gpu_total_memory_bytes": gpu.total_memory,
        "driver_version": subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            text=True).strip(),
        "warp_device": str(wp.get_cuda_device(0)),
        "optimization_probe": {"optimizers": [type(o).__name__ for o in optimizers],
                               "hidden_weight_max_delta": delta},
        "fixed_source_types": [f"{cls.__module__}.{cls.__name__}" for cls in
                               [Simulation, MultiTaskWorldModelEnv, WorldModelLearner,
                                ActorCriticPolicyLearner]],
        "packages": dict(sorted(versions.items())),
    }
    output = json.dumps(record, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
