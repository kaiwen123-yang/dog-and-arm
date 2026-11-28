from collections import defaultdict
from pathlib import Path
from scripts.multimodal.mm03_launch import now,read,write
import re
root=Path('/root/autodl-tmp/mm03-20261126')
out=Path(__file__).parent
matched={}
cohorts=[]
for p in sorted((root/'B/native_batch_timings').glob('*.json')):
    item=read(p)
    if item['partition'] not in ('rounds/r44/development','rounds/r44/regression'):continue
    parts=item['dispatch_order'][0].split('_')
    matrix=[case.split('_',5)[5] for case in item['dispatch_order']]
    if item['cases']!=len(set(matrix)):continue
    kind=parts[2]
    if item['cases'] != {'development':8,'regression':20}[kind]:continue
    if item['workers'] not in (4,min(12,item['cases'])):continue
    cohort=dict(partition=kind,method=parts[3],seed=int(parts[4]),workers=item['workers'],steps=item['physical_substeps'],seconds=item['elapsed_s'],cases=sorted(matrix),source=p.name)
    cohorts.append(cohort)
for part in ('development','regression'):
    for method in ('D23','H9','H9-WM'):
        rows=[c for c in cohorts if c['partition']==part and c['method']==method]
        base=[c for c in rows if c['workers']==4]
        more=[c for c in rows if c['workers']!=4]
        if not base or not more:continue
        assert all(c['cases']==base[0]['cases'] for c in rows)
        def rate(cs):
            return sum(x['steps'] for x in cs)/sum(x['seconds'] for x in cs)
        a,b=rate(base),rate(more)
        matched[f'{method}/{part}']=dict(old_steps_s=a,new_steps_s=b,ratio=b/a,old_batches=len(base),new_batches=len(more),old_seeds=[x['seed'] for x in base],new_seeds=[x['seed'] for x in more],new_workers=more[0]['workers'],case_matrix=base[0]['cases'])
events=dict(l.split() for l in Path('/sys/fs/cgroup/memory.events').read_text().splitlines())
assert all(k in matched for k in ('D23/development','D23/regression'))
done=all(x['ratio']>=1.05 for x in matched.values()) and int(events['oom'])==0 and int(events['oom_kill'])==0 and read(root/'status/B.json')['state']=='running'
write(out/'decision.json',dict(at=now(),round=44,retained=done,matched=matched,cohorts=cohorts,oom=int(events['oom']),oom_kill=int(events['oom_kill']),added_physics_steps=0,added_optimizer_updates=0,interpretation='Same method and full scene/side/goal matrix; seeds differ. Normalize by actual integrated physical substeps. Release automatically at the third receipt, memory reserve, or candidate freeze.'))
policy=root/'resources/tail_scoring.json'
cfg=read(policy)
if done:
    cfg.pop('through_round',None)
else:
    cfg['enabled']=False
cfg['decision']=str(out/'decision.json')
write(policy,cfg)
print(now(),done,[(k,round(x['old_steps_s']),round(x['new_steps_s'])) for k,x in matched.items()])
