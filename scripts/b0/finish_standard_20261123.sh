#!/usr/bin/env bash
# Finish the registered standard contact diagnostics after the current SSH session.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
raw=results/raw_large/b0/standard_handoff_20261123
note=results/b0/standard_handoff_20261123
mkdir -p "$raw" "$note"
exec 9>"$raw/worker.lock"
flock -n 9
state() { printf '%s %s\n' "$(TZ=Asia/Shanghai date -Is)" "$*" | tee -a "$raw/events.log"; }
trap 'rc=$?; if ((rc)); then state "failed rc=$rc line=$LINENO"; printf "%s\n" "$rc" > "$raw/failed"; fi' EXIT
wait_session() {
  while tmux has-session -t "=$1" 2>/dev/null; do sleep 10; done
}
eval_at() {
  local run=$1 u=$2 protocol=$3 backend=${4:-warp}
  local ck out
  ck=$(printf 'results/b0/%s/checkpoint_%06d.pt' "$run" "$u")
  out="${run}_u${u}_${backend}_${protocol}"
  [[ -s "results/b0/$out/evaluation.json" ]] && return 0
  local argv=(bash scripts/b0/env.sh python -u)
  if [[ $backend == native ]]; then argv=(bash scripts/project_env.sh python -u); fi
  argv+=(scripts/b0/eval_contact_segments.py --backend "$backend" --checkpoint "$ck" --run "$out" --manifest "config/b0/contact_dev_${protocol}.json")
  if [[ -d "results/b0/$out" ]]; then argv+=(--resume); fi
  state "evaluate $out"
  MUJOCO_GL=egl "${argv[@]}" > "$raw/$out.log" 2>&1
}
wm_at() {
  local run=$1 u=$2 label=$3 data=$4 ck out
  ck=$(printf 'results/b0/%s/checkpoint_%06d.pt' "$run" "$u")
  out="standard_transfer_wm_${label}_${run}_u${u}"
  [[ -s "results/b0/$out/errors.csv" ]] && return 0
  state "score $out"
  OMP_NUM_THREADS=3 bash scripts/b0/env.sh python -m scripts.b0.standard_contact_validation score --wm "$ck" --data "$data" --device cpu --run "$out" > "$raw/$out.log" 2>&1
}
state 'started'
# The initial physical screens are already managed by separate sessions. Join them before reuse.
for job in data-eval data50-eval pad-eval native50; do wait_session "b0-standard-$job"; done
for entry in 'gripdata_r1 data 50' 'padding_r1 padding 50' 'wmcoords_r1 coords 50' 'gain32_to200_r1 gain200 200'; do
  read -r suffix job endpoint <<< "$entry"
  run=standard_s0_$suffix
  wait_session "b0-standard-$job"
  test -s "results/b0/$run/outcome.json"
  points=(0 1 5 10 50)
  if [[ $endpoint == 200 ]]; then points=(200); fi
  for u in "${points[@]}"; do
    for protocol in v1 hold_margin_v2; do eval_at "$run" "$u" "$protocol"; done
  done
  if [[ $job == coords || $job == gain200 ]]; then
    for split in standard challenge; do
      if [[ $split == standard ]]; then data=results/b0/standard_transfer_wm_validation_control10_r1; else data=/root/autodl-tmp/dog-and-arm-b0-recovery/results/b0/recovery_b_grip_challenge_r1; fi
      wm_at "$run" "$endpoint" "$split" "$data"
    done
  fi
done
run=standard_s0_gain32_to200_r1
eval_at "$run" 200 v1 native
eval_at "$run" 200 hold_margin_v2 native
state 'compare transfer and u200 on the same real grip entries'
probe="$note/gain200_entry.json"
if [[ ! -s $probe ]]; then
  bash scripts/b0/env.sh python -m scripts.b0.compare_contact_entry_reward --initial results/b0/standard_s0_gain32_r1/checkpoint_000000.pt --updated "results/b0/$run/checkpoint_000200.pt" --output "$probe" > "$raw/entry.log" 2>&1
fi
state 'all registered diagnostics finished'
date -Is > "$raw/finished"
