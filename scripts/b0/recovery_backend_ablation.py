"""Run the fixed Warp Actor with declared MuJoCo 3.16 contact-manifold interventions."""
import argparse
import json
from pathlib import Path

import mujoco as mj

from learning.b0.contact_policy import load_policy
from learning.b0.physics import build, settings
from scripts.b0.eval_contact_segments import evaluate_segment
from scripts.b0.recovery_backend_probe import DEFAULT_SOURCE, configure


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--references', type=Path, default=DEFAULT_SOURCE)
    p.add_argument('--run', required=True)
    p.add_argument('--engine', choices=('cpu316','warp316'), default='cpu316')
    p.add_argument('--variant', choices=('wheel_deepest_only', 'multiccd_off',
                                         'wheel_deepest_and_multiccd_off'), default='wheel_deepest_only')
    p.add_argument('--video', action='store_true')
    args = p.parse_args()
    if mj.__version__ != '3.16.0' or Path(args.run).name != args.run:
        p.error('Expected MuJoCo 3.16 and a new run name')
    out = Path('results/b0')/args.run
    out.mkdir(parents=True, exist_ok=False)
    raw = Path('results/raw_large/b0')/args.run
    paths = [args.references/name for name in ('pull_60_train', 'push_25_train')]
    device = 'cuda:0' if args.engine == 'warp316' else 'cpu'
    policy = load_policy(args.checkpoint, paths, device)
    spec = dict(engine=args.engine, variant=args.variant, checkpoint=str(args.checkpoint),
                references=str(args.references), command='Actor on own measured state', results=[])
    for side, episode in zip(('pull','push'), paths):
        model = build(settings('mobile' if side=='pull' else 'push', 1))
        configure(model, spec['variant'])
        folder = Path(side)/'full'/'nominal'
        backend = 'warp' if args.engine == 'warp316' else 'native'
        result = evaluate_segment(policy, episode,'full', {'p6_case':1}, backend, out/folder,
                                  model=model, device=device, raw_dir=raw/folder, video=args.video)
        spec['results'].append({k:result[k] for k in ('side','passed','physics_steps','first_failure','final_door_deg')})
        print(spec['results'][-1],flush=True)
    (out/'evaluation.json').write_text(json.dumps(spec,indent=2)+'\n')


if __name__ == '__main__':
    main()
