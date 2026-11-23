"""Index real per-case results in this round, respecting the registered mixed contact protocol."""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--closeout', action='store_true')
    a = parser.parse_args()
    base = Path('results/b0')
    note = base / 'standard_handoff_20261123'
    note.mkdir(exist_ok=True)
    margin = set(load(Path('config/b0/contact_dev_hold_margin_v2.json'))['cases'])
    cases, summary, packages = [], {}, {}
    for p in sorted(base.glob('standard_s0_*/evaluation.json')):
        ev = load(p)
        v2 = 'hold_margin_v2' in ev['manifest']
        key = (ev['checkpoint'], ev['backend'])
        pair = summary.setdefault(key, {})
        for trial in sorted(p.parent.glob('*/*/nominal/result.json')):
            item = load(trial)
            group = item['side'] + '/' + item['segment']
            fail = item['first_failure'] or {}
            row = dict(checkpoint=key[0], backend=key[1], protocol='hold_margin_v2' if v2 else 'v1',
                       group=group, passed=item['passed'], steps=item['physics_steps'],
                       reason=fail.get('reason'), net_force_n=fail.get('door_net_force_n'),
                       case=str(trial), formal=(group in margin) == v2)
            cases.append(row)
            if row['formal']:
                if group in pair:
                    raise ValueError(f'Duplicate formal group {key} {group}')
                pair[group] = row['passed']
    for end in sorted(base.glob('standard_s0_*/outcome.json')):
        packages[end.parent.name] = load(end)
    record = dict(beijing=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
                  training=packages, completed_nominal_cases=len(cases),
                  formal=[dict(checkpoint=c, backend=b, passed=sum(values.values()), scored=len(values))
                          for (c,b),values in summary.items()])
    (note/'snapshot.json').write_text(json.dumps(record, indent=2)+'\n')
    if cases:
        with (note/'case_index.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=cases[0], lineterminator='\n')
            writer.writeheader()
            writer.writerows(cases)
    if a.closeout:
        heading = '### 标准接触 tmux 回收'
        lines = [heading, '', f"北京时间 {record['beijing']}。已回收 {len(cases)} 条 nominal 物理记录，含同包不同参考协议的配对。记录索引见 results/b0/standard_handoff_20261123/case_index.csv。", '']
        for name, m in packages.items():
            lines.append(f"- {name}：累计 H32 {m['actor_updates']} 次、有效在线转移 {m['valid_online_transitions']}。")
        lines += ['', '已完成末节点的十项原登记组合结果如下。', '']
        for row in record['formal']:
            if row['scored'] == 10 and any(s in row['checkpoint'] for s in ('000050.pt','000200.pt')):
                lines.append(f"- {row['checkpoint']}，{row['backend']}，{row['passed']}/10。")
        lines += ['', '首步力和后继 tracking 的同起点双侧实测见 results/b0/standard_handoff_20261123/gain200_entry.json。开发 D、完整 C、独立 seed 与 H 本队列未执行。']
        block='\n'.join(lines)+'\n'
        for f in ('reports/B0_STANDARD_TRANSFER_RESULTS.md','DAILY_WORK_LOG.md'):
            path=Path(f)
            if heading not in path.read_text():
                with path.open('a') as stream:
                    stream.write('\n'+block)
        for f in ('PROJECT_STATE.md','prompts/NEXT_RUN.txt'):
            path=Path(f)
            if heading not in path.read_text():
                contents=path.read_text()
                first,rest=contents.split('\n',1)
                path.write_text(first+'\n\n'+block+'\n'+rest)
    print(json.dumps(record))

if __name__=='__main__':
    main()
