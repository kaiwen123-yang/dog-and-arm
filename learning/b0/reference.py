"""Load name-indexed, per-episode native MuJoCo reference and transition arrays."""
from pathlib import Path
import json

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/b0/reference_manifest.json"


def load_episode(path, mmap_mode="r"):
    """Policy-rate arrays. qpos[k], qvel[k] precede physical_target[k].

    Native P6 door reference actions vary at 500 Hz. They live exclusively in
    substeps/ and must never be read as a 20 ms held-action replay.
    """
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    with (path / "metadata.json").open() as file:
        metadata = json.load(file)
    if not metadata["finished"]:
        raise ValueError(f"Incomplete collection in {path}")
    return {name.stem: np.load(name, mmap_mode=mmap_mode, allow_pickle=False)
            for name in sorted(path.glob("*.npy"))}


def reference_entries(manifest=MANIFEST):
    with Path(manifest).open() as file:
        return json.load(file)["references"]
