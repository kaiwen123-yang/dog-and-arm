#!/usr/bin/env python3
"""Create the project workspace without replacing existing files."""

from pathlib import Path


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    folders = (
        "materials/photos", "assets/accessories", "assets/converted",
        "vendor", "description", "sim/components", "sim/robots", "sim/scenes",
        "controllers", "scripts", "config", "prompts", "docs", "reports",
        "results/assembly", "results/doors", "results/tmp", "results/raw_large",
    )
    for folder in folders:
        (project / folder).mkdir(parents=True, exist_ok=True)
    print(f"Project: {project}")
    print(f"Prepared {len(folders)} directories; existing files were preserved.")
    print("Next: open Codex in this directory and use prompts/FIRST_RUN.txt.")


if __name__ == "__main__":
    main()
