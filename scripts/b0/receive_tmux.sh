#!/usr/bin/env bash
# Second-platform receiver for the finite AutoDL handoff. Run inside detached tmux.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
base=$(pwd)
handoff=$(git rev-parse HEAD)
cloud=/root/autodl-tmp/dog-and-arm-b0-recovery
raw=results/raw_large/b0/recovery_tmux_20261123
note=results/b0/recovery_tmux_20261123
localrun=recovery_planar_arm_screen_warp_r1
mkdir -p "$raw" "$note"
exec 9>"$raw/receiver.lock"
flock -n 9
net=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
while true; do
  if ! "${net[@]}" autodl-dog-arm "cat $cloud/$raw/status.json" > "$raw/cloud_status.tmp"; then sleep 45; continue; fi
  python3 -m json.tool "$raw/cloud_status.tmp" > "$raw/cloud_status.json"
  mapfile -t names < <(python3 -c 'import json,sys; print("\n".join(sorted({r["job"].split("/")[0] for r in json.load(open(sys.argv[1]))["jobs"]})))' "$raw/cloud_status.json")
  ready=1
  for name in "${names[@]}"; do
    mkdir -p "results/b0/$name"
    if ! rsync -rt --timeout=45 --prune-empty-dirs --include='*/' --include='*.json' --include='*.csv' --include='*.jsonl' --include='*.mp4' --exclude='*'          "autodl-dog-arm:$cloud/results/b0/$name/" "results/b0/$name/"; then ready=0; fi
  done
  date --iso-8601=seconds
  if [[ "$ready" = 1 ]] && python3 -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1]))["finished"])' "$raw/cloud_status.json"; then
    # The other development run already has its own local process.
    if [[ -f results/b0/$localrun/evaluation.json ]] || ! pgrep -f -- "scripts.b0.eval_contact_segments.*--run $localrun" >/dev/null; then break; fi
  fi
  sleep 60
done
# Use an isolated delivery checkout; preserve the operator's active working tree.
receipt="$base/../dog-and-arm-b0-delivery-${handoff:0:10}"
git worktree add --detach "$receipt" "$handoff"
for name in "${names[@]}" "$localrun"; do
  rsync -rt --prune-empty-dirs --include='*/' --include='*.json' --include='*.csv' --include='*.jsonl' --include='*.mp4' --exclude='*' "results/b0/$name/" "$receipt/results/b0/$name/"
done
cp "$raw/cloud_status.json" "$receipt/$note/outcome.json"
cd "$receipt"
mapfile -t complete < <(find results/b0 -path 'results/b0/recovery*/evaluation.json' -printf '%h\n' | sort)
python3 -m scripts.b0.index_recovery_round --runs "${complete[@]}" --output results/b0/recovery_round_20261123
python3 - "$note/outcome.json" "$localrun" <<'PY'
from pathlib import Path
import json,sys,datetime
from zoneinfo import ZoneInfo
d=json.load(open(sys.argv[1]))
now=datetime.datetime.now(ZoneInfo('Asia/Shanghai'))
lines=[f"## {now:%Y-%m-%d %H:%M} 北京时间｜tmux 物理评分回收", ""]
for name in sorted({r['job'].split('/')[0] for r in d['jobs']}|{sys.argv[2]}):
    p=Path('results/b0')/name
    parts=[]
    for side in ('pull','push'):
        cases={f.parent.name:json.load(open(f))['passed'] for f in (p/side/'full').glob('*/result.json')}
        nominal=cases.pop('nominal',None)
        ntext={True:'通过',False:'失败',None:'未测'}[nominal]
        parts.append(side+' 名义'+ntext+'，开发'+(f'{sum(cases.values())}/{len(cases)}' if cases else '未测'))
    lines.append(f"- {name}："+'；'.join(parts))
for r in d['jobs']:
    if r['status']!='completed': lines.append(f"- 需查验 {r['job']}，状态 {r['status']}，日志 {r['log']}。")
lines+=['','逐案物理结果及实际分母见 results/b0/recovery_round_20261123/case_index.csv 和各 run 目录。独立 seed 与 H 保持封存。']
text='\n'.join(lines)+'\n'
for name in ('DAILY_WORK_LOG.md','reports/B0_RECOVERY_RESULTS_20261123.md'):
    with open(name,'a') as f: f.write('\n'+text)
for name in ('prompts/NEXT_RUN.txt','PROJECT_STATE.md'):
    p=Path(name); p.write_text(text+'\n'+p.read_text())
PY
git add -- "$note/outcome.json" results/b0/recovery_round_20261123 DAILY_WORK_LOG.md PROJECT_STATE.md prompts/NEXT_RUN.txt reports/B0_RECOVERY_RESULTS_20261123.md
for name in "${names[@]}" "$localrun"; do git add -- "results/b0/$name"; done
git -c user.name=Codex -c user.email=codex@users.noreply.github.com commit -m 'Collect the detached B0 regressions and record the final case counts'
tip=$(git rev-parse HEAD)
ref="refs/heads/codex/b0-tmux-delivery-${handoff:0:10}"
git push "autodl-dog-arm:$cloud" "HEAD:$ref"
"${net[@]}" autodl-dog-arm "cd $cloud && git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push origin $tip:refs/heads/main && gh api repos/kaiwen123-yang/dog-and-arm/commits/main --jq .sha" > "$base/$raw/published.txt"
cat "$base/$raw/published.txt"
