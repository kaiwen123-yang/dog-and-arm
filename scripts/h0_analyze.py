"""Recompute H0 reception timing from saved real rows (no device access)."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np


def intervals(values, scale=1e6, clock="host_monotonic"):
    t = np.asarray(values, dtype=np.int64)
    if len(t) < 2:
        return {"count": len(t), "clock": clock}
    gap = np.diff(t) / scale
    span = (int(t[-1]) - int(t[0])) / 1e9
    return {"count": len(t), "span_s": span,
            "receive_hz": (len(t) - 1) / span if span > 0 else None,
            "interval_ms": {k: float(v) for k, v in zip(("median", "p95", "max"), np.percentile(gap, [50, 95, 100]))},
            "backwards": int((gap < 0).sum()), "equal_timestamps": int((gap == 0).sum()),
            "gaps_over_100ms": int((gap > 100).sum()), "gaps_over_500ms": int((gap > 500).sum()),
            "clock": clock, "first_timestamp_ns": int(t[0]), "last_timestamp_ns": int(t[-1])}


def nearest(source, target):
    s, t = np.array(source, dtype=np.int64), np.array(target, dtype=np.int64)
    if not len(s) or not len(t):
        return None
    # Restrict association to the overlapping interval; no extrapolation.
    s = s[(s >= t.min()) & (s <= t.max())]
    if not len(s):
        return None
    idx = np.searchsorted(t, s)
    left, right = t[np.clip(idx - 1, 0, len(t) - 1)], t[np.clip(idx, 0, len(t) - 1)]
    delta = np.minimum(np.abs(s - left), np.abs(s - right)) / 1e6
    return {"count": len(s), "absolute_ms": dict(zip(("median", "p95", "max"), map(float, np.percentile(delta, [50, 95, 100])))),
            "meaning": "Nearest callback/receive time on same host, not exposure synchronization or latency"}


def read_csv(path):
    return list(csv.DictReader(path.open())) if path.exists() else []


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    a = p.parse_args()
    d = a.directory
    summary = {"source": str(d), "streams": {}, "issues": [], "timing_findings": [],
               "issues_scope": "Recorder errors only. Interval observations are separate, not universal pass/fail thresholds."}
    rows = read_csv(d / "stream_timing.csv")
    streams = {s: [r for r in rows if r["stream"] == s] for s in sorted({r["stream"] for r in rows})}
    mono = {s: [int(r["host_monotonic_ns"]) for r in rs] for s, rs in streams.items()}
    for s, rs in streams.items():
        summary["streams"][s] = {"receive": intervals(mono[s]),
            "header": intervals([int(r["header_ns"]) for r in rs], clock="original_ros_header"),
            "modes": sorted({(r["encoding"], int(r["width"]), int(r["height"]), r["frame_id"]) for r in rs})}
        n = summary["streams"][s]["receive"].get("gaps_over_100ms", 0)
        if n:
            summary["timing_findings"].append({"stream": s, "gaps_over_100ms": n,
                "note": "Inspect whether gaps are transport bursts, intentional restart or missing data"})
    joints, gripper = read_csv(d / "joints.csv"), read_csv(d / "gripper.csv")
    for name, rs in (("joints", joints), ("gripper", gripper)):
        mono[name] = [int(r["host_monotonic_ns"]) for r in rs]
        summary[name] = intervals(mono[name])
    if joints:
        q = np.array([[float(r[f"q{i}_rad"]) for i in range(1, 7)] for r in joints])
        summary["joint_deg"] = {"first": np.degrees(q[0]).tolist(), "last": np.degrees(q[-1]).tolist(),
                                "range": np.degrees(np.ptp(q, axis=0)).tolist()}
        spans = np.array([float(r["can_last_s"]) - float(r["can_first_s"]) for r in joints])
        summary["joint_group_max_span_ms"] = float(spans.max() * 1000)
        summary["joint_groups_over_20ms"] = int((spans > .02).sum())
    if gripper:
        w = np.array([float(r["width_m"]) for r in gripper]) * 1000
        summary["gripper_width_mm"] = {"first": w[0], "last": w[-1], "min": w.min(), "max": w.max()}
    summary["association"] = {"color_depth": nearest(mono.get("color", []), mono.get("depth", [])),
                              "color_joints": nearest(mono.get("color", []), mono.get("joints", []))}
    summary["depth_samples"] = []
    for path in sorted((d / "samples").glob("depth_*.npy")):
        arr = np.load(path, allow_pickle=False)
        valid = arr[arr > 0]
        summary["depth_samples"].append({"file": str(path.relative_to(d)), "shape": list(arr.shape),
            "dtype": str(arr.dtype), "nonzero_fraction": float(np.count_nonzero(arr) / arr.size),
            "nonzero_mm_percentiles_5_50_95": np.percentile(valid, [5, 50, 95]).tolist() if len(valid) else []})
    info = {}
    for s in ("color", "depth"):
        path = d / f"{s}_camera_info.json"
        if path.exists():
            info[s] = json.loads(path.read_text())
            stream = streams.get(s, [])
            matched = all((int(r["width"]), int(r["height"]), r["frame_id"]) ==
                          (info[s]["width"], info[s]["height"], info[s]["header"]["frame_id"]) for r in stream)
            summary[f"{s}_info_check"] = {"image_dimensions_and_frame_match": bool(stream) and matched,
                                          "fx_nonzero": info[s]["k"][0] != 0}
    for f in ("camera_summary.json", "arm_summary.json"):
        if (d / f).exists():
            meta = json.loads((d / f).read_text())
            summary[f.removesuffix(".json")] = meta
            for key in ("error", "worker_error", "raw_error", "queue_drops", "can_error_frames"):
                if meta.get(key):
                    summary["issues"].append({"file": f, "field": key, "value": meta[key]})
    (d / "timing_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for s, value in summary["streams"].items():
        print(s, json.dumps(value["receive"]))
    print("joints", json.dumps(summary["joints"]))
    print("association", json.dumps(summary["association"]))
    print("issues", summary["issues"])


if __name__ == "__main__":
    main()
