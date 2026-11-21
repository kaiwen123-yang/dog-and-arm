"""Evaluate a frozen B0 Actor in the unchanged native 3.3.0 P6 environment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def native_worker(args):
    from learning.b0.evaluate import PROTOCOL, evaluate_cases
    from learning.b0.physics import make_model
    from learning.b0.reference import load_episode
    import mujoco as mj
    import numpy as np
    if mj.__version__ != '3.3.0':
        raise RuntimeError(f'The historical physics benchmark requires native MuJoCo 3.3.0, got {mj.__version__}')

    def policy_factory(name, episode):
        print(json.dumps({'begin': name}), flush=True)
        previous_applied = None

        def actor(qpos, qvel, frame):
            msg = dict(frame=frame, qpos=qpos.tolist(), qvel=qvel.tolist())
            if previous_applied is not None:
                msg['previous_applied'] = previous_applied
            print(json.dumps(msg, allow_nan=False), flush=True)
            return np.asarray(json.loads(input()))
        def applied(cmd):
            nonlocal previous_applied
            previous_applied = cmd.tolist()
        actor.applied = applied
        return actor

    setup = json.loads(input())
    refs = {name: load_episode(Path(setup['reference_root']) / name) for name in PROTOCOL['references']}
    cases = None if args.full else [dict(id='nominal', dx_m=0., dy_m=0., dyaw_deg=0.)]
    output_dir = ROOT / 'results/b0' / args.run
    raw = ROOT / 'results/raw_large/b0' / args.run / 'physical'
    if args.action_blocks:
        from learning.b0.action_diagnostics import diagnose_initial_actions, record_action_coverage
        path = Path(setup['reference_root']) / 'support' / 'substeps/qpos.npy'
        diagnose_initial_actions(make_model(), refs['support'], np.load(path, mmap_mode='r'),
                                 policy_factory, output_dir / 'action_blocks', raw)
        record_action_coverage(refs, output_dir / 'action_blocks',
                               ROOT / 'results/raw_large/b0' / args.checkpoint.parent.name)
    else:
        evaluate_cases(make_model(), refs, policy_factory, output_dir / 'physical', seed=setup['seed'],
                       cases=cases, checkpoint=str(args.checkpoint), trace_directory=raw)
    (output_dir / 'evaluation.json').write_text(json.dumps(dict(
        physics='native CPU MuJoCo 3.3.0', actor_interpreter='isolated B0 environment',
        raw=str(raw.relative_to(ROOT)),
        action_source=('diagnostic action-group interventions on frozen actor' if args.action_blocks
                       else 'frozen actor inference every 20 ms'),
        **setup), indent=2) + '\n')


def evaluate(args):
    if Path(args.run).name != args.run or args.run in ('', '.', '..'):
        raise ValueError('run must be a new directory name')
    os.environ.setdefault('TORCH_COMPILE_DISABLE', '1')
    import numpy as np
    import torch
    from learning.b0.training import FreeRun
    device = 'cuda:0'
    torch.set_float32_matmul_precision('high')
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=True)
    output_dir = ROOT / 'results/b0' / args.run
    output_dir.mkdir(exist_ok=False, parents=True)
    run = FreeRun(ckpt['cfg'], args.run, ckpt['seed'], device=device)
    run.warmstart()
    run.actor.load_state_dict(ckpt['actor'])
    setup = dict(seed=ckpt['seed'], actor_updates=ckpt['updates'], checkpoint=str(args.checkpoint),
                 reference_root=ckpt['cfg']['reference_root'], full_manifest=args.full)
    del ckpt
    worker = ['bash', str(ROOT / 'scripts/project_env.sh'), 'python', '-u', __file__,
              '--native-worker', '--run', args.run, '--checkpoint', str(args.checkpoint)]
    if args.full:
        worker.append('--full')
    if args.action_blocks:
        worker.append('--action-blocks')
    with subprocess.Popen(worker, cwd=ROOT, text=True, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, bufsize=1) as proc:
        try:
            proc.stdin.write(json.dumps(setup) + '\n')
            proc.stdin.flush()
            for message in proc.stdout:
                request = json.loads(message)
                if 'begin' in request:
                    name = request['begin']
                    actor = run.policy_factory(name, run.refs[name])
                    continue
                kwargs = {}
                if 'previous_applied' in request:
                    kwargs['previous_applied'] = request['previous_applied']
                command = actor(np.asarray(request['qpos']), np.asarray(request['qvel']), request['frame'], **kwargs)
                proc.stdin.write(json.dumps(command.tolist(), allow_nan=False) + '\n')
                proc.stdin.flush()
        finally:
            proc.stdin.close()
        if proc.wait():
            raise RuntimeError('Native physics evaluation failed; see the child traceback')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--checkpoint', required=True, type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--action-blocks', action='store_true', help='Short diagnostic interventions on four action groups')
    modes.add_argument('--full', action='store_true', help='Use all 3 × 20 frozen initial configurations')
    parser.add_argument('--native-worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.native_worker:
        native_worker(args)
    else:
        evaluate(args)
