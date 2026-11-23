"""Index completed physical judgments. Preserve nominal, subset, and full-C denominators."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def table(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases, variants = [], []
    for run in sorted(args.runs):
        if not (run / "evaluation.json").exists():
            raise ValueError(f"Missing completed evaluation manifest for {run}")
        evaluation = read(run / "evaluation.json")
        records = sorted(run.glob("*/full/*/result.json"))
        if len(records) != evaluation["evaluated"]:
            raise ValueError(f"Incomplete completed-case table in {run}")
        for path in records:
            side, _, case = path.relative_to(run).parts[:3]
            d = read(path)
            if d["prefix_physics_steps"] != 0 or d["start_substep"] != 0:
                raise ValueError(path)
            events = {e["phase"]: e for e in d["events"]}
            if d["passed"]:
                if (len(events) != 13 or events["post_release_hold"]["ticks"] < 1500 or
                        events["final"]["ticks"] < 1500):
                    raise ValueError(f"Missing full-task requirements in {path}")
            failure = d["first_failure"] or {}
            cases.append(dict(run=run.name, checkpoint=evaluation["checkpoint"], backend=d["backend"],
                mujoco=d["mujoco"], side=side, case=case, passed=int(d["passed"]), steps=d["physics_steps"],
                last_angle_deg=d["final_door_deg"], reached_phases=len(events), first_failure=failure.get("reason",""),
                failure_phase=failure.get("phase",""), post_release_ticks=events.get("post_release_hold",{}).get("ticks",""),
                final_ticks=events.get("final",{}).get("ticks",""), result=str(path), raw=d.get("raw_directory","")))
        for side in sorted({row["side"] for row in cases if row["run"] == run.name}):
            selected = [row for row in cases if row["run"] == run.name and row["side"] == side]
            nominal = [row for row in selected if row["case"] == "nominal"]
            if len(nominal) != 1:
                raise ValueError(f"Missing or duplicated nominal for {run}/{side}")
            dev = [row for row in selected if row["case"] != "nominal"]
            ids = [row["case"] for row in dev]
            if len(set(ids)) != len(ids) or not set(ids) <= {f"C{i:02d}" for i in range(1,21)}:
                raise ValueError(f"Invalid development IDs {ids}")
            reasons = Counter(row["first_failure"] for row in dev if not row["passed"])
            base = nominal[0]
            variants.append(dict(run=run.name, checkpoint=base["checkpoint"],backend=base["backend"],
                    mujoco=base["mujoco"],side=side,nominal=base["passed"],nominal_steps=base["steps"],
                    nominal_degrees=base["last_angle_deg"],nominal_failure=base["first_failure"],
                    development_scope="full" if len(ids)==20 else ("subset" if ids else "unmeasured"),
                    C_pass=sum(row["passed"] for row in dev) if ids else "",C_tested=len(dev),
                    C_ids=" ".join(ids),passed_C=" ".join(row["case"] for row in dev if row["passed"]),
                    failure_counts=json.dumps(reasons,sort_keys=True)))
    args.output.mkdir(parents=True, exist_ok=True)
    table(args.output / "case_index.csv", cases)
    table(args.output / "scores.csv", variants)


if __name__ == "__main__":
    main()
