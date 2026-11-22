"""Replay actual held targets from the prescribed full start through the independent door judge."""
import argparse
from pathlib import Path

import numpy as np

from scripts.b0.eval_contact_segments import evaluate_segment


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--episode', type=Path, required=True)
    p.add_argument('--backend', choices=('native','warp'), required=True)
    p.add_argument('--run', required=True)
    options = p.parse_args()
    if options.run in ('','.','..') or Path(options.run).name != options.run:
        p.error('Choose a new run name')
    actions = np.load(options.episode/'action_clipped.npy',mmap_mode='r')
    def reference(_path,frame,_q,_v,_last):
        return actions[frame]
    r = evaluate_segment(reference,options.episode,'full',{'p6_case':1},options.backend,
                         Path('results/b0')/options.run,raw_dir=Path('results/raw_large/b0')/options.run,
                         video=True,action_source='fixed complete measured 20 ms targets, independent event judge')
    print(r['passed'],r['physics_steps'],r['first_failure'])


if __name__ == '__main__':
    main()
