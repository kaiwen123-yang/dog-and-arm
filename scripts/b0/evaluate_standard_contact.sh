#!/usr/bin/env bash
# Evaluate the ten formal nominal physical contacts from a completed checkpoint.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
run=${1:?training run name}
update=${2:?checkpoint update}
backend=${3:-warp}
[[ $run =~ ^[[:alnum:]_-]+$ && $update =~ ^[0-9]+$ ]]
prefix=(bash scripts/b0/env.sh)
case "$backend" in
    warp) ;;
    native) prefix=(bash scripts/project_env.sh) ;;
    *) exit 2 ;;
esac
checkpoint=$(printf 'results/b0/%s/checkpoint_%06d.pt' "$run" "$update")
test -s "$checkpoint"
logs=results/raw_large/b0/pair_nominal_scores
mkdir -p "$logs"
for protocol in v1 hold_margin_v2; do
    label="${run}_u${update}_${backend}_${protocol}"
    (
        flock -n 9
        [[ -f results/b0/$label/evaluation.json && -f results/b0/$label/returns.json ]] && exit 0
        extra=()
        if [[ -d results/b0/$label ]]; then extra+=(--resume); fi
        MUJOCO_GL=egl "${prefix[@]}" python -u scripts/b0/eval_contact_segments.py \
            --backend "$backend" --checkpoint "$checkpoint" --run "$label" \
            --manifest "config/b0/contact_dev_${protocol}.json" \
            --formal-contact --paper-score "${extra[@]}"
    ) 9>"$logs/$label.lock" >> "$logs/$label.log" 2>&1
done
