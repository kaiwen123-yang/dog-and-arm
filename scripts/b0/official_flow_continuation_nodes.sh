#!/usr/bin/env bash
# Sequential physical evaluation of immutable snapshots while the main process trains.
set -euo pipefail
export B0_FLOW_SEGMENT="${B0_FLOW_SEGMENT:-continuation}" MUJOCO_GL=egl
out=results/b0/standard_official_flow_continuation_20261124
raw=results/raw_large/b0/official_flow_continuation_20261124
if [[ "$B0_FLOW_SEGMENT" == continuation_20261125 ]]; then
    out=results/b0/standard_official_flow_continuation_20261125
    raw=results/raw_large/b0/official_flow_continuation_20261125
fi
run() { bash scripts/b0/env.sh python -u -m "scripts.b0.$1" "${@:2}"; }
for u in "$@"; do
    printf -v tag '%06d' "$u"
    until test -s "$out/node_$tag.json"; do sleep 10; done
    if [[ "$B0_FLOW_SEGMENT" == continuation_20261125 ]]; then
        case "$u" in 5000|7500|10000|12500|15000) ;; *) exit 2 ;; esac
        if [[ "$u" == 5000 ]]; then
            run official_flow_coverage "$u"
            [[ -f "$out/current_policy/u$tag/scores.json" ]] || run official_flow_current_policy "$u"
            continue
        fi
        test -s "$out/tracking_windows.json"
    fi
    for backend in warp native; do
        run official_flow_eval "$u" full --backend "$backend"
        if [[ "$backend" == warp || "$u" == 3000 || "$u" == 5000 || "$u" == 10000 || "$u" == 15000 || "$u" == "${B0_FLOW_FINAL_NODE:-0}" ]]; then
            run official_flow_eval "$u" formal --backend "$backend"
        fi
    done
    if [[ ! -f "$out/free/u$tag/evaluation.json" ]]; then
        run official_flow_free "$u" --references /root/autodl-tmp/dog-and-arm-b0/results/raw_large/b0/native_teacher_20261121_r1
    fi
    run official_flow_servo "$u"
    run official_flow_coverage "$u"
    if [[ "$u" == 3000 || "$u" == 5000 || "$u" == 10000 || "$u" == 15000 ]]; then
        [[ -f "$out/current_policy/u$tag/scores.json" ]] || run official_flow_current_policy "$u"
    fi
    if [[ "$B0_FLOW_SEGMENT" == continuation_20261125 ]]; then
        run official_flow_readiness "$u"
        run official_flow_tracking "$u"
    fi
    echo "completed physical evaluation u$u"
done
