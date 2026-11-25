#!/usr/bin/env bash
# Score named immutable snapshots in separate processes on the registered GPU.
set -euo pipefail
export B0_FLOW_SEGMENT=continuation_20261125 MUJOCO_GL=egl
out=results/b0/standard_official_flow_continuation_20261125
run() { bash scripts/b0/env.sh python -u -m "scripts.b0.$1" "${@:2}"; }
wait_node() {
    local marker
    printf -v marker '%s/node_%06d.json' "$out" "$1"
    until [[ -s "$marker" ]]; do sleep 15; done
}
case "${1:-10000}" in
    10000)
        wait_node 5000
        until grep -q '"update": 5001,' "$out/updates.jsonl"; do sleep 10; done
        while (( $(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1) < 24576 )); do sleep 15; done
        [[ -s "$out/restored_u005000.json" ]] || run official_flow_restore_check 5000
        bash scripts/b0/official_flow_continuation_nodes.sh 5000 7500
        run official_flow_continuation_index 7500
        target=10000 ;;
    15000)
        bash scripts/b0/official_flow_continuation_nodes.sh 12500
        run official_flow_continuation_index 12500
        target=15000 ;;
    *) exit 2 ;;
esac
bash scripts/b0/official_flow_continuation_nodes.sh "$target"
run official_flow_restore_check "$target"
run official_flow_archive "$target"
run official_flow_continuation_index "$target"
echo "Finished original evaluations, recovery check and accounting at u$target"
