#!/usr/bin/env bash
set -euo pipefail
export MUJOCO_GL=egl B0_FLOW_SEGMENT=continuation_20261125
raw=results/raw_large/b0/official_flow_continuation_20261125
out=results/b0/standard_official_flow_continuation_20261125
parent=results/b0/standard_official_flow_continuation_20261124/recovery.json
target="${1:-10000}"
case "$target" in
    10000) nodes=(5000 7500 10000) ;;
    15000) nodes=(12500 15000) ;;
    *) exit 2 ;;
esac
test -s "$out/run_manifest.json"
# Keep named resumable states on the persistent AutoFS volume. Rolling
# states use the data disk, which has faster writes and atomic rename.
named=/root/autodl-fs/dog-and-arm/official_flow_continuation_20261125
for u in "${nodes[@]}"; do
    printf -v tag '%06d' "$u"
    mkdir -p "$named/resume_$tag"
    if [[ ! -e "$raw/resume_$tag" ]]; then ln -s "$named/resume_$tag" "$raw/resume_$tag"; fi
    test "$(readlink -f "$raw/resume_$tag")" = "$(readlink -f "$named/resume_$tag")"
done
echo "waiting for the parent run's GPU allocation; stop=$target"
while (( $(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1) < 46300 )); do sleep 15; done
if compgen -G "$out/node_*.json" >/dev/null || compgen -G "$out/rolling_*.json" >/dev/null; then
    args=(--resume)
else
    args=(--parent-recovery "$parent")
fi
date -Is
exec bash scripts/b0/env.sh python -u -m scripts.b0.official_flow "${args[@]}" --stop "$target"
