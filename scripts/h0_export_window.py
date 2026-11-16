"""Export an inspectable short window from locally preserved H0 recordings."""
import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("events", type=Path)
    p.add_argument("destination", type=Path)
    p.add_argument("--padding", type=float, default=3)
    a = p.parse_args()
    events = [json.loads(x) for x in a.events.read_text().splitlines()]
    lo = min(r["host_monotonic_ns"] for r in events) - int(a.padding * 1e9)
    hi = max(r["host_monotonic_ns"] for r in events) + int(a.padding * 1e9)
    a.destination.mkdir(parents=True, exist_ok=False)
    report = {"source_directory": str(a.source), "event_file": str(a.events),
              "window_monotonic_ns": [lo, hi], "padding_s": a.padding,
              "samples": [], "csv_rows": {}}
    for name in ("stream_timing.csv", "joints.csv", "gripper.csv", "can_errors.csv"):
        with (a.source / name).open() as f, (a.destination / name).open("w", newline="") as out:
            r = csv.DictReader(f)
            w = csv.DictWriter(out, fieldnames=r.fieldnames)
            w.writeheader()
            n = 0
            for row in r:
                if lo <= int(row["host_monotonic_ns"]) <= hi:
                    w.writerow(row)
                    n += 1
            report["csv_rows"][name] = n
    with (a.destination / "arm_snapshots.jsonl").open("w") as out:
        for line in (a.source / "arm_snapshots.jsonl").open():
            if lo <= json.loads(line)["host_monotonic_ns"] <= hi:
                out.write(line)
    shutil.copy2(a.events, a.destination / "events.jsonl")
    for name in ("color_camera_info.json", "depth_camera_info.json", "camera_summary.json", "arm_summary.json"):
        if (a.source / name).exists():
            # Full-run summaries retain their original scope/name and are not window statistics.
            target = "full_run_" + name if name.endswith("summary.json") else name
            shutil.copy2(a.source / name, a.destination / target)
    for name in ("motion_summary.json", "motion_commands.csv", "motion_sdk_tx.csv", "motion_observation.json"):
        if (a.events.parent / name).exists():
            shutil.copy2(a.events.parent / name, a.destination / name)
    # Preserve representative original arrays, each with its actual timing gap.
    samples = [json.loads(x) for x in (a.source / "sample_index.jsonl").read_text().splitlines()]
    selected = set()
    for event in events:
        if event["event"] not in ("initial_read", "j6_slow_out_end", "stop_at_offset_end",
                                   "gripper_open_end", "gripper_close_end", "gripper_reopen_end"):
            continue
        for stream in ("color", "depth"):
            candidates = [s for s in samples if s["stream"] == stream]
            if not candidates:
                continue
            s = min(candidates, key=lambda r: abs(r["host_monotonic_ns"] - event["host_monotonic_ns"]))
            path = a.destination / s["path"]
            path.parent.mkdir(exist_ok=True)
            if s["path"] not in selected:
                shutil.copy2(a.source / s["path"], path)
                selected.add(s["path"])
            report["samples"].append({"event": event["event"], **s,
                "sample_minus_event_ms": (s["host_monotonic_ns"] - event["host_monotonic_ns"]) / 1e6,
                "note": "nearest periodic sample; use actual timestamp, not an assertion of event simultaneity"})
    frames = list(csv.DictReader((a.source / "video_frames.csv").open()))
    kept = [r for r in frames if lo <= int(r["color_host_monotonic_ns"]) <= hi]
    if kept:
        first, last = int(kept[0]["video_index"]), int(kept[-1]["video_index"])
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(first / 30),
                        "-i", str(a.source / "preview.avi"), "-frames:v", str(last - first + 1),
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(a.destination / "clip.mp4")], check=True)
        with (a.destination / "video_frames.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["clip_index", *kept[0]])
            w.writeheader()
            for i, row in enumerate(kept):
                w.writerow({"clip_index": i, **row})
        report["video"] = {"source_first_frame": first, "source_last_frame": last,
                           "fixed_playback_fps": 30, "clock_mapping": "video_frames.csv"}
    (a.destination / "window_manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    subprocess.run(["/usr/bin/python3", str(Path(__file__).with_name("h0_analyze.py")), str(a.destination)], check=True)


if __name__ == "__main__":
    main()
