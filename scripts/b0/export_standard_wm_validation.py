"""Export measured WM results with one coverage table and shared kinematic baselines."""
import argparse
import csv
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text())


def records(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_table(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def export(output, scores):
    output.mkdir(parents=True, exist_ok=True)
    runs, datasets, coverage, losses, metrics = {}, {}, {}, [], []
    baseline_seen = set()
    definition = read(scores[0] / "state_loss_definition.json")
    axes = ["side", "h", "stratum", "label"]
    exposure = ["available", "available_lanes", "scored", "scored_lanes"]
    for folder in scores:
        meta, cost = read(folder / "sources.json"), read(folder / "scoring_cost.json")
        if read(folder / "state_loss_definition.json") != definition:
            raise ValueError(f"Different state loss in {folder}")
        source = Path(meta["data"])
        data_id = source.name
        rows = [r for r in read(source / "cohorts.json") if r["split"] == "validation"]
        dataset = dict(data_path=str(source), registration=meta["registration"], interval_counts=meta["counts"],
                       validation_cohorts=rows, cap=meta["window_cap"], sampling_seed=meta["sampling_seed"])
        if (source / "collection_cost.json").is_file():
            dataset["collection_cost"] = read(source / "collection_cost.json")
        if data_id in datasets and datasets[data_id] != dataset:
            raise ValueError(f"Inconsistent physical cohort metadata for {data_id}")
        datasets[data_id] = dataset
        runs[folder.name] = dict(source_path=str(folder), wm=meta["wm"], validation=data_id, cost=cost)
        for table, destination in (("state_loss.csv", losses), ("errors.csv", metrics)):
            for row in records(folder / table):
                key = (data_id, *(row[k] for k in axes))
                denominator = {k: row[k] for k in exposure}
                if key in coverage and coverage[key] != denominator:
                    raise ValueError(f"Nonmatching scored window identity at {key}")
                coverage[key] = denominator
                if not int(row["scored"]):
                    continue
                # Hold and constant velocity use the very same real states at
                # each checkpoint. Retain them once per evaluation dataset.
                if row["predictor"] != "wm" and data_id in baseline_seen:
                    continue
                values = {k: v for k, v in row.items() if k not in exposure and k != "stored_frames"}
                destination.append(dict(data=data_id, source_run=folder.name, **values))
        baseline_seen.add(data_id)
    coverage_rows = [dict(zip(("data", *axes), key, strict=True), **denom) for key, denom in coverage.items()]
    write_table(output / "coverage.csv", coverage_rows)
    write_table(output / "state_loss.csv", losses)
    write_table(output / "physical_errors.csv", metrics)
    (output / "index.json").write_text(json.dumps(dict(definition=definition, scores=runs, datasets=datasets,
        usage="Join CSVs on data/side/h/stratum/label. Each scored window has h successors and h+1 frames. Shared kinematic controls are reported once per dataset."),
        indent=2, allow_nan=False) + "\n")


def compare_statistics(output, checkpoints):
    import torch

    comparisons = {}
    for path in checkpoints:
        ck = torch.load(path, map_location="cpu", weights_only=False)
        anchor_path = ck["cfg"]["wm_checkpoint"]
        initial = torch.load(anchor_path, map_location="cpu", weights_only=False)["dyn"]
        dyn = ck["dyn"]
        buffers, mlp = {}, {}
        for name, v in dyn.items():
            if name.startswith(("state_normalizer.", "action_normalizer.", "mlp.")):
                before = initial[name]
                difference = float((v.double() - before.double()).abs().max())
                dest = mlp if name.startswith("mlp.") else buffers
                dest[name] = dict(identical=torch.equal(v, before), max_abs_delta=difference)
                if name.endswith(".count"):
                    dest[name].update(before=float(before.item()), after=float(v.item()))
        comparisons[str(path)] = dict(anchor=anchor_path, update=ck["updates"], buffers=buffers,
                                      mlp_tensors=mlp, all_buffers_identical=all(v["identical"] for v in buffers.values()),
                                      changed_mlp_tensors=sum(not v["identical"] for v in mlp.values()))
    (output / "wm_statistics.json").write_text(json.dumps(comparisons, indent=2, allow_nan=False)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scores", type=Path, nargs="+", required=True)
    parser.add_argument("--compare-stats", type=Path, nargs="+",
                        help="Check actual WM statistics and MLP state against each run's held-action anchor")
    args = parser.parse_args()
    export(args.output, args.scores)
    if args.compare_stats:
        compare_statistics(args.output, args.compare_stats)
