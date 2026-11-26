#!/usr/bin/env bash
# Detached run/resume. A second invocation asks the active supervisor to recover failed units.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
run=${1:-/root/autodl-tmp/mm03-20261126}
session=${MM03_TMUX_SESSION:-dog-arm-mm03-20261126}
cd "$repo"
mkdir -p "$run/logs"
export PYTHONPATH="$repo:$repo/scripts"
unset PYTHONHOME
if [[ -s "$run/performance/20261126-cf-latency/native_wheel_results.json" && -x .venv/bin/python ]]; then
    if ! .venv/bin/python -m scripts.multimodal.mm03_wheel_contacts --root "$run" >>"$run/logs/native-wheel-reader.log" 2>&1; then
        printf 'Native wheel reader is optional; load details are in %s.\n' "$run/logs/native-wheel-reader.log"
    fi
fi
publish_repo=${MM03_PUBLISH_REPO:-"$(dirname "$repo")/dog-and-arm-mm03-publish"}
if [[ -d "$publish_repo" ]] && ! tmux has-session -t "=${session}-publish" 2>/dev/null; then
    printf -v publisher 'cd %q && export MUJOCO_GL=egl OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=%q MM03_INFERENCE_SOCKET=%q && exec %q -u -m scripts.multimodal.mm03_publish watch --root %q --repo %q >>%q 2>&1' \
        "$repo" "$repo:$repo/scripts" "$run/service/policy.sock" "$repo/.venv/bin/python" "$run" "$publish_repo" "$run/logs/publication.log"
    tmux new-session -d -s "${session}-publish" -c "$repo" "$publisher"
fi
printf -v line 'cd %q && export PYTHONPATH=%q && unset PYTHONHOME && exec %q -u -m scripts.multimodal.mm03_launch run --root %q >>%q 2>&1' \
    "$repo" "$repo:$repo/scripts" "$repo/.venv/bin/python" "$run" "$run/logs/supervisor.log"
if tmux has-session -t "=$session" 2>/dev/null; then
    if .venv/bin/python -c 'import sys; from pathlib import Path; from scripts.multimodal.mm03_launch import alive,read; sys.exit(0 if alive(read(Path(sys.argv[1])/"status/supervisor.json")) else 1)' "$run"; then
        exec .venv/bin/python -u -m scripts.multimodal.mm03_launch run --root "$run"
    fi
    tmux new-window -d -t "$session" -n supervisor -c "$repo" "$line"
else
    tmux new-session -d -s "$session" -c "$repo" "$line"
fi
printf 'tmux %s\nlog %s\n' "$session" "$run/logs/supervisor.log"
