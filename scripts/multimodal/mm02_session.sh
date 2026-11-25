#!/usr/bin/env bash
# One detached session owns the optimizer, scoring, recovery receipts and the final publication.
set -euo pipefail
run=$1
publish=$2
repo=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo"
export PYTHONPATH=.:scripts MUJOCO_GL=egl OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
unset PYTHONHOME
exec > >(tee -a "$run/logs/tmux.log") 2>&1
phase=handoff
trap 'rc=$?; printf "%s phase=%s exit=%s\n" "$(date -Is)" "$phase" "$rc" | tee "$run/session_exit.txt"' EXIT
if [[ -s "$run/handoff_processes.json" ]]; then
    .venv/bin/python - "$run/handoff_processes.json" <<'PY'
import json, pathlib, sys, time
jobs = json.loads(pathlib.Path(sys.argv[1]).read_text())
def running(job):
    try:
        fields = pathlib.Path(f'/proc/{job["pid"]}/stat').read_text().rsplit(")",1)[1].split()
        return fields[0] != 'Z' and fields[19] == job['starttime']
    except FileNotFoundError:
        return False
while any(map(running,jobs)):
    time.sleep(2)
print("Prior in-flight optimizer blocks have exited. Continuing from durable stage receipts.", flush=True)
PY
fi
phase=experiment
.venv/bin/python -u -m scripts.multimodal.mm02_run "$run" --workers 10
phase=score
.venv/bin/python -u -m scripts.multimodal.mm02_summary "$run" "$run/aggregates" --final
torchpy=.conda/envs/arm-and-dog/bin/python
"$torchpy" -u -m scripts.multimodal.mm02_learning_evidence "$run"
"$torchpy" -u -m scripts.multimodal.mm02_dynamics_summary "$run"
phase=publish
.venv/bin/python -u -m scripts.multimodal.mm02_publish "$run" "$publish" final
phase=complete
