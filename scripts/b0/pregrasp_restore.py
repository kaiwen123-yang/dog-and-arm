"""Read-only u10000 recovery at the registered online boundary, with a new receipt."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import torch
import yaml

from scripts.b0 import official_flow as flow
from scripts.b0 import official_flow_restore_check as checks

OUT = Path("results/b0/standard_pregrasp_compatibility_20261125")


def equal_tensor(a, b):
    a = a.detach().cpu().contiguous()
    b = b.detach().cpu().contiguous()
    return (a.shape == b.shape and a.dtype == b.dtype and
            torch.equal(a.reshape(-1).view(torch.uint8), b.reshape(-1).view(torch.uint8)))


def main():
    start = datetime.now(timezone.utc)
    parent = flow.io.read(flow.OUT / "node_010000.json")
    assert parent == flow.io.read(flow.OUT / "recovery.json")
    assert (parent["update"], parent["clock"], parent["valid"]) == (10000, 26988, 102414758)
    run, _ = flow.build(yaml.safe_load(flow.CONFIG.read_text()))
    assert flow.restore(run, parent) == 10000
    with patch.object(checks, "OUT", OUT):
        checks.verify_loaded(run, parent)
    state = torch.load(Path(parent["state"]) / "state.pt", map_location="cpu", mmap=True, weights_only=False)
    model = torch.load(parent["checkpoint"], map_location="cpu", mmap=True, weights_only=False)
    network_counts = {}
    for name in ("dyn", "actor", "critic"):
        live = getattr(run, name).state_dict()
        assert live.keys() == model[name].keys()
        assert all(equal_tensor(value, model[name][k]) for k, value in live.items())
        network_counts[name] = len(live)
    for name, value in state["lanes"].items():
        assert equal_tensor(run.lanes[name], value), name
    for name, value in state["counters"].items():
        assert equal_tensor(getattr(run.plant, name), value), name
    pages = state["replay"]["pages"]
    count = 0
    for key, saved in pages.items():
        for field, value in saved.items():
            assert equal_tensor(run.replay.pages[key][field], value), (key, field)
            count += 1
    valid_per_update = run.schedule.positions / run.cfg["replay_ratio"]
    next_threshold = int(valid_per_update - (run.total - parent["ratio"]["previous_clock"]))
    assert next_threshold == 5722
    flow.io.write(OUT / "parent_recovery.json", dict(
        parent=parent, backing=str(Path(parent["state"]).resolve()), executed_start_utc=start.isoformat(),
        executed_end_utc=datetime.now(timezone.utc).isoformat(), networks_and_buffers_exact=network_counts,
        replay_pages_exact=len(pages), replay_field_tensors_exact=count, lanes_exact=list(state["lanes"]),
        physical_counters_exact=list(state["counters"]), valid_to_next_ratio=next_threshold,
        additional_optimizer_steps=0, existing_boundary_check="restored_u010000.json",
    ))


if __name__ == "__main__":
    main()
