#!/usr/bin/env bash
# Sequential physical evaluation of immutable snapshots while the main process trains.
set -euo pipefail
export B0_FLOW_SEGMENT=continuation MUJOCO_GL=egl
out=results/b0/standard_official_flow_continuation_20261124
raw=results/raw_large/b0/official_flow_continuation_20261124
run() { bash scripts/b0/env.sh python -u -m "scripts.b0.$1" "${@:2}"; }
for u in "$@"; do
    printf -v tag '%06d' "$u"
    until test -s "$out/node_$tag.json"; do sleep 10; done
    for backend in warp native; do
        run official_flow_eval "$u" full --backend "$backend"
        if [[ "$backend" == warp || "$u" == 3000 || "$u" == 5000 ]]; then
            run official_flow_eval "$u" formal --backend "$backend"
        fi
    done
    if [[ ! -f "$out/free/u$tag/evaluation.json" ]]; then
        run official_flow_free "$u" --references /root/autodl-tmp/dog-and-arm-b0/results/raw_large/b0/native_teacher_20261121_r1
    fi
    run official_flow_servo "$u"
    run official_flow_coverage "$u"
    if [[ "$u" == 3000 || "$u" == 5000 ]]; then
        run official_flow_current_policy "$u"
    fi
    echo "completed physical evaluation u$u"
done
