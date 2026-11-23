#!/usr/bin/env bash
# Receive compact artifacts from the simulation node and publish a normal closeout commit.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
base=$(pwd)
handoff=$(git rev-parse HEAD)
cloud=/root/autodl-tmp/dog-and-arm-b0-standard
raw=results/raw_large/b0/standard_handoff_20261123
mkdir -p "$raw"
exec 8>"$raw/receive.lock"
flock -n 8
net=(ssh -o BatchMode=yes -o ConnectTimeout=12 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
filters=(-rtm --include='/standard*/' --exclude='/*' --exclude='*.pt' --exclude='*.log' --include='*/' --include='*.json' --include='*.jsonl' --include='*.csv' --include='*.mp4' --exclude='*')
while true; do
  if state=$("${net[@]}" -n autodl-dog-arm "cd $cloud && if test -s $raw/finished; then echo finished; elif test -s $raw/failed; then echo failed; else echo running; fi"); then
    if rsync "${filters[@]}" "autodl-dog-arm:$cloud/results/b0/" results/b0/; then
      printf '%s %s\n' "$(TZ=Asia/Shanghai date -Is)" "$state" > "$raw/received.txt"
      if [[ $state == finished || $state == failed ]]; then break; fi
    fi
  fi
  sleep 30
done
if [[ $state == failed ]]; then
  "${net[@]}" -n autodl-dog-arm "cd $cloud && tail -30 $raw/events.log"
  exit 1
fi
# The active project can continue changing while the registered run is in flight.
receipt="$base/../dog-and-arm-standard-delivery-${handoff:0:9}"
git worktree add --detach "$receipt" "$handoff"
rsync "${filters[@]}" results/b0/ "$receipt/results/b0/"
cd "$receipt"
python3 scripts/b0/index_standard_transfer.py --closeout > "$base/$raw/final-index.log"
git add -- DAILY_WORK_LOG.md PROJECT_STATE.md prompts/NEXT_RUN.txt reports/B0_STANDARD_TRANSFER_RESULTS.md ':(glob)results/b0/standard*/**'
git -c user.name=Codex -c user.email=codex@users.noreply.github.com commit -m 'Collect completed standard B0 contact checkpoints and physical evaluation denominators'
tip=$(git rev-parse HEAD)
ref="refs/heads/codex/b0-standard-closeout-${handoff:0:9}"
git push "autodl-dog-arm:$cloud" "HEAD:$ref"
# Use the authenticated publishing host. Non-fast-forward leaves main intact and retains the delivery branch.
"${net[@]}" autodl-dog-arm bash -s -- "$cloud" "$tip" "$ref" <<'PUBLISH' | tee "$base/$raw/published.txt"
set -euo pipefail
cd "$1"
tip=$2
ref=$3
export HTTPS_PROXY=http://127.0.0.1:7890
auth=(git -c http.version=HTTP/1.1 -c credential.helper= -c 'credential.helper=!gh auth git-credential')
for attempt in 1 2 3; do
  if "${auth[@]}" push origin "$tip:refs/heads/main"; then
    observed=$(gh api repos/kaiwen123-yang/dog-and-arm/commits/main --jq .sha)
    echo "published $tip; observed origin/main $observed"
    gh api "repos/kaiwen123-yang/dog-and-arm/commits/$tip" --jq .sha
    exit 0
  fi
  sleep 20
done
"${auth[@]}" push origin "$tip:$ref"
echo "published $tip on $ref; main needs integration"
PUBLISH
