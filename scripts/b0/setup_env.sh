#!/usr/bin/env bash
# Install the historical O1 runtime in a dedicated environment. Invoke from any cwd.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH VIRTUAL_ENV CONDA_PREFIX
export PYTHONNOUSERSITE=1
store=vendor/b0
mkdir -p "$store"
python_bin="${B0_PYTHON:-python3.13}"
if [[ ! -x .venv-b0/bin/python ]]; then
    "$python_bin" -m venv .venv-b0
fi
py=.venv-b0/bin/python
"$py" -c 'import sys; assert sys.version_info[:2] == (3,13), sys.version'
"$py" -m pip install --disable-pip-version-check 'uv==0.13.9'
uv=.venv-b0/bin/uv
# Do not edit either upstream source tree. Download only the O1 metadata used here.
"$py" - <<'PY'
import json
import subprocess
from pathlib import Path

lock = json.loads(Path("config/b0/source_lock.json").read_text())
sources = {**lock["upstream"], "o1": lock["o1_records"]}
for name, source in sources.items():
    repo = Path("vendor/b0") / name

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

    if not (repo / ".git").exists():
        repo.mkdir(exist_ok=True)
        if any(repo.iterdir()):
            raise SystemExit(f"{repo} contains files outside a checkout")
        git("init", "-q")
        git("remote", "add", "origin", source["url"] + ".git")
        if name == "o1":
            paths = [source["resolved_lock"], source["metadata_patch"], *source["documents"]]
            paths += [source["campaign_dir"] + "/" + p for p in source["input_files"]]
            git("sparse-checkout", "set", "--no-cone", *("/"+p for p in paths))
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
                          text=True, capture_output=True)
    if head.returncode != 0:
        git("fetch", "--depth=1", "--filter=blob:none", "origin", source["commit"])
        git("checkout", "--detach", source["commit"])
    elif head.stdout.strip() != source["commit"]:
        raise SystemExit(f"{repo} has a different checkout at {head.stdout.strip()}")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit(f"{repo} has modified tracked source files")
PY
# The old algorithm's own uv.lock points at mjlab 1.5. O1 resolved the published 1.6 fork.
resolved="$store/o1-resolved"
mkdir -p "$resolved"
cp "$store/supermimic/pyproject.toml" "$resolved/pyproject.toml"
cp "$store/o1/configs/o1_official_resolved.uv.lock" "$resolved/uv.lock"
"$uv" export --project "$resolved" --frozen --no-dev --no-emit-project \
    --no-emit-package mjlab --no-hashes -o "$store/pinned.txt" >/dev/null
"$uv" pip install --python "$py" --default-index "${B0_INDEX_URL:-https://pypi.org/simple}" \
    -r "$store/pinned.txt" -e "$store/mjlab_research" -e "$store/supermimic"
