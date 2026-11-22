"""Apply each frozen 50 Hz contact target sequence in the segment evaluation plant."""
import argparse
import csv
import json
from pathlib import Path
import sys

import mujoco as mj
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.b0.eval_contact_segments import evaluate_segment, WarpSingleWorld, dump, ZERO
from learning.b0.physics import build, settings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend', choices=('native','warp'), required=True)
    p.add_argument('--references', type=Path, default=Path('results/raw_large/b0/contact_held_r1'))
    p.add_argument('--manifest', type=Path, default=Path('config/b0/contact_dev_v1.json'))
    p.add_argument('--segment', nargs='+', help='Evaluate only these registered segment names')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--reuse-native', type=Path, help='Earlier documented RSI positives from exactly this protocol')
    args = p.parse_args()
    if mj.__version__ != ('3.3.0' if args.backend=='native' else '3.16.0'):
        p.error('Run with matching native33 or Warp316 interpreter')
    cases = json.loads(args.manifest.read_text())['cases']
    if args.segment:
        cases = {name: case for name, case in cases.items() if name.split('/')[1] in args.segment}
        if not cases:
            p.error('No matching registered segments')
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    last_side = None
    for name, registered in cases.items():
        side, segment = name.split('/')
        path = args.references / registered['episode']
        reused = None
        if args.backend == 'native' and args.reuse_native:
            prior = args.reuse_native / (side+'_'+segment+'_rsi_reference') / 'result.json'
            if prior.is_file():
                result = json.loads(prior.read_text())
                if (result['side']!=side or result['segment']!=segment or result['episode']!=path.name
                        or result['backend']!=args.backend or result['perturbation']!=ZERO
                        or 'teacher' not in result['action_source'] or result['prefix_physics_steps']!=100):
                    raise ValueError(f'Mismatched positive control {prior}')
                reused = str(prior)
        if not reused:
            if side != last_side:
                model = build(settings('push' if side=='push' else 'mobile',1))
                plant = WarpSingleWorld(model,'cuda:0') if args.backend=='warp' else None
                last_side=side
            actions = np.load(path/'action_clipped.npy',mmap_mode='r')
            def reference_command(_episode, frame, _q, _v, _previous):
                return actions[frame]
            result = evaluate_segment(reference_command,path,segment,ZERO,args.backend,
                        args.output/side/segment, model=model,integrator=plant,
                        action_source='recorded 20 ms teacher targets, replayed from reconstructed RSI')
        failure = result['first_failure'] or {}
        ready = failure.get('readiness',{})
        row = dict(side=side,segment=segment,backend=args.backend,passed=result['passed'],
                   reference=path.name,source='executed' if not reused else 'archived positive control',
                   evidence=str(args.output/side/segment/'result.json') if not reused else reused,
                   physics_steps=result['physics_steps'],maximum_steps=result['reference_phase_end_substep']-result['start_substep'],
                   final_door_deg=result['final_door_deg'],reason=failure.get('reason'),phase=failure.get('phase'),
                   best_ticks=ready.get('best'),required_ticks=ready.get('required'))
        rows.append(row)
        print(json.dumps(row),flush=True)
    with (args.output/'cases.csv').open('x') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0],lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    dump(args.output/'summary.json',dict(backend=args.backend,mujoco=mj.__version__,cases=len(rows),
         newly_executed=sum(x['source']=='executed' for x in rows),passed=sum(x['passed'] for x in rows),
         source='fixed previously measured 20 ms targets, identical prefix and event gates as Actor; no learned policy'))


if __name__=='__main__':
    main()
