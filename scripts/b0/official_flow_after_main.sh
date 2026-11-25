#!/usr/bin/env bash
set -euo pipefail
out=results/b0/standard_official_flow_continuation_20261125
raw=results/raw_large/b0/official_flow_continuation_20261125
session=b0-official-20261125
while [[ "$(tmux display-message -p -t "$session:eval" '#{pane_dead}')" == 0 ]]; do sleep 30; done
[[ "$(tmux display-message -p -t "$session:eval" '#{pane_dead_status}')" == 0 ]]
bash scripts/b0/env.sh python -u -m scripts.b0.official_flow_extension_review || { status=$?; if [[ $status == 3 ]]; then echo "Original physical evidence is ready for review; additional updates have not been started."; exit 0; fi; exit "$status"; }
tmux new-window -d -t "$session:" -n eval-extension -c "$PWD" "bash -o pipefail -c 'bash scripts/b0/official_flow_registered_eval.sh 15000 2>&1 | tee -a $raw/tmux_eval_extension.log'"
tmux set-window-option -t "$session:eval-extension" remain-on-exit on
bash scripts/b0/official_flow_registered_train.sh 15000 2>&1 | tee -a "$raw/tmux_train_extension.log"
