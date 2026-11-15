#!/usr/bin/env python3
"""Fetch the two pinned model repositories; keep existing checkouts untouched."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def git(directory: Path, *arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(directory), *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    return result.stdout.strip() if capture else ""


def fetch_repository(specification: dict) -> dict:
    destination = ROOT / specification["destination"]
    revision = specification["revision"]
    existing_checkout = (destination / ".git").exists()

    head_probe = None
    if existing_checkout:
        head_probe = subprocess.run(
            ["git", "-C", str(destination), "rev-parse", "--verify", "HEAD"],
            text=True, capture_output=True,
        )

    if existing_checkout and head_probe.returncode == 0:
        # Deliberately do not reset, stash, clean, fetch, or change this checkout.
        actual_head = git(destination, "rev-parse", "HEAD", capture=True)
        action = "kept_existing_checkout"
    else:
        if not existing_checkout and destination.exists() and any(destination.iterdir()):
            raise RuntimeError(
                f"{destination} contains files but is not a Git checkout; "
                "keep those files and choose a separate destination in sources.lock.json."
            )
        destination.mkdir(parents=True, exist_ok=True)
        if not existing_checkout:
            git(destination, "init", "--quiet")
            git(destination, "remote", "add", "origin", specification["url"])
        elif git(destination, "status", "--porcelain", capture=True):
            raise RuntimeError(f"{destination} has no HEAD but contains local files; keep them and finish its checkout manually.")
        git(destination, "config", "remote.origin.promisor", "true")
        git(destination, "config", "remote.origin.partialclonefilter", "blob:none")
        git(destination, "sparse-checkout", "init", "--cone")
        git(destination, "sparse-checkout", "set", *specification["sparse_paths"])
        git(destination, "fetch", "--filter=blob:none", "--depth=1", "origin", revision)
        git(destination, "checkout", "--detach", "FETCH_HEAD")
        actual_head = git(destination, "rev-parse", "HEAD", capture=True)
        action = "fetched_pinned_checkout"

    dirty = bool(git(destination, "status", "--porcelain", capture=True))
    return {
        "key": specification["key"],
        "source_url": specification["url"],
        "destination": specification["destination"],
        "requested_revision": revision,
        "actual_head": actual_head,
        "matches_requested_revision": actual_head == revision,
        "local_changes_present": dirty,
        "action": action,
        "sparse_paths_requested": specification["sparse_paths"],
    }


def main() -> None:
    configuration = json.loads((ROOT / "config/sources.lock.json").read_text())
    report_path = ROOT / "reports/source_versions.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"repositories": []}

    # Keep successfully fetched repositories recorded if a later download fails.
    for specification in configuration["repositories"]:
        result = fetch_repository(specification)
        report["repositories"].append(result)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(f"{result['key']}: {result['action']}; {result['destination']}")
        if not result["matches_requested_revision"]:
            print("  Existing revision differs from the requested revision; preserved and recorded.")
        if result["local_changes_present"]:
            print("  Local changes are preserved.")

    print(f"Wrote {report_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
