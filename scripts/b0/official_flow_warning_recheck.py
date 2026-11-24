"""Run the registered u1000 warning rechecks in a fresh original 2 ms evaluator."""
import argparse
import runpy
import sys
from pathlib import Path
from scripts.b0.official_flow_trace import capture_warnings, WARNING_CONTEXT

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('parent',type=Path)
    p.add_argument('name')
    p.add_argument('sides',nargs='+',choices=['pull','push'])
    a=p.parse_args()
    root=a.parent.resolve()
    capture_warnings(Path('results/b0/standard_official_flow_continuation_20261124/backend')/f'warnings_{a.name}.jsonl')
    WARNING_CONTEXT.update(case=a.name,side='->'.join(a.sides))
    sys.path.insert(0,str(root))
    script=root/'scripts/b0/eval_contact_segments.py'
    sys.argv=[str(script),'--checkpoint','results/raw_large/b0/official_flow_20261124/checkpoint_001000.pt',
        '--backend','warp','--run',a.name,'--round','standard_official_flow_continuation_20261124/backend',
        'official_flow_continuation_20261124/backend','--paper-score','--full-task','--side',*a.sides,
        '--references','results/raw_large/b0/full_warp_hold_park_r1']
    import os
    os.chdir(root)
    runpy.run_path(str(script),run_name='__main__')
