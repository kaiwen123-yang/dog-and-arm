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
if tmux has-session -t "=$session" 2>/dev/null; then
    exec .venv/bin/python -u -m scripts.multimodal.mm03_launch run --root "$run"
fi
printf -v line 'cd %q && export PYTHONPATH=%q && unset PYTHONHOME && exec %q -u -m scripts.multimodal.mm03_launch run --root %q >>%q 2>&1' \
    "$repo" "$repo:$repo/scripts" "$repo/.venv/bin/python" "$run" "$run/logs/supervisor.log"
tmux new-session -d -s "$session" -c "$repo" "$line"
printf 'tmux %s\nlog %s\n' "$session" "$run/logs/supervisor.log"
