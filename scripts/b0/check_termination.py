"""Compare the O1 imagined termination rule to observed physical endpoints."""
import argparse
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evaluation', type=Path)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    meta = json.loads((args.evaluation/'evaluation.json').read_text())
    raw = Path(meta['raw_path'])/'physical'
    rows = []
    for f in sorted((args.evaluation/'physical').glob('*_F*.json')):
        case = json.loads(f.read_text())
        observed = np.load(raw/f.stem/'qpos.npy')[-1]
        ref = np.load(args.references/case['reference_id']/'qpos.npy')
        index = min(max(0, (case['physics_steps'] - 1)//10), len(ref)-1)
        target = ref[index]
        height = abs(observed[2]-target[2])
        gravity_z_diff = abs(2*(np.sum(observed[4:6]**2)-np.sum(target[4:6]**2)))
        normalized = max(height/.10, gravity_z_diff/.12)
        p = 1/(1 + np.exp(-(normalized-1)/.05))
        rows.append(dict(reference=case['reference_id'], case=case['case'], physics_steps=case['physics_steps'],
                         first_failure=next(iter(case['failures']), None),
                         height_error_m=height, gravity_z_error=gravity_z_diff,
                         o1_soft_termination_on_measured_state=p))
    failures = [r for r in rows if r['first_failure']=='wheel_unloaded']
    result = dict(source=str(args.evaluation), inputs='Actual endpoint and reference, independent of WM predictions',
                  thresholds=dict(anchor_pos=.10,anchor_ori=.12,softness=.05), unload_failures=len(failures),
                  max_probability_on_unload=max((r['o1_soft_termination_on_measured_state'] for r in failures), default=None),
                  cases=rows)
    with args.output.open('x') as out:
        out.write(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    main()
