"""Append an operator/experiment annotation on this host; never control devices."""
import argparse
import json
import time
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("directory", type=Path)
p.add_argument("event")
p.add_argument("--note", default="")
a = p.parse_args()
a.directory.mkdir(parents=True, exist_ok=True)
row = {"event": a.event, "note": a.note, "host_monotonic_ns": time.monotonic_ns(),
       "host_unix_ns": time.time_ns(), "kind": "operator_or_experiment_annotation"}
with (a.directory / "events.jsonl").open("a") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(json.dumps(row, ensure_ascii=False))
