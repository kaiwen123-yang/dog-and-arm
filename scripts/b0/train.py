"""Run real O1 supervised WM + H32 actor/critic updates on the B0 free-motion scene."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True, help='New experiment directory name')
    p.add_argument('--config', type=Path, default=ROOT/'config/b0/baseline.yaml')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--updates', type=int, required=True, help='Absolute actor-update endpoint')
    p.add_argument('--from-checkpoint', type=Path, help='Restore networks + optimizers; start new physical episodes/replay')
    p.add_argument('--eval-only', action='store_true', help='Evaluate --from-checkpoint in a new output directory')
    p.add_argument('--integration', action='store_true',
                   help='Pre-formal diagnostic: evaluate three nominal conditions at start/end')
    return p.parse_args()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def main():
    args = arguments()
    if Path(args.run).name != args.run or args.run in ('', '.', '..'):
        raise ValueError('run must be a new directory name')
    if args.updates < 0 or (args.eval_only and not args.from_checkpoint):
        raise ValueError('invalid update count or missing evaluation checkpoint')
    # Integration uses eager PyTorch on the laptop. Graph construction still runs autograd.
    os.environ.setdefault('TORCH_COMPILE_DISABLE', '1')
    import torch
    import yaml
    from learning.b0.training import FreeRun
    from learning.b0.diagnostics import checkpoint_eval

    cfg = yaml.safe_load(args.config.read_text())
    if not torch.cuda.is_available():
        raise RuntimeError('O1 Muon/fused Adam learner requires a working CUDA torch runtime')
    torch.set_float32_matmul_precision('high')
    out = ROOT/'results/b0'/args.run
    out.mkdir(exist_ok=False, parents=True)
    previous = torch.load(args.from_checkpoint, map_location='cuda:0', weights_only=False) if args.from_checkpoint else None
    if previous and (previous['cfg'] != cfg or previous['seed'] != args.seed):
        raise ValueError('warm restart requires the same data/model config and training seed')
    run = FreeRun(cfg, args.run, args.seed)
    opts = [*run.wml.optimizers, *run.policy.actor_optimizers, *run.policy.critic_optimizers]
    run.warmstart()
    if previous:
        for name in ('actor', 'critic', 'dyn'):
            getattr(run, name).load_state_dict(previous[name])
        for obj, state in zip(opts, previous['optimizers'], strict=True):
            obj.load_state_dict(state)
        run.updates, run.collected = previous['updates'], previous['collected']
        del previous
    spec = dict(cfg=cfg, run=args.run, initial_actor_update=run.updates, target_actor_update=args.updates,
                hypothesis='O1 initialized from scratch can improve free-base reference tracking via supervised GenCoord and H32 BPTT.',
                seed=args.seed, gpu=torch.cuda.get_device_name(), torch=torch.__version__,
                compile_disable=os.environ['TORCH_COMPILE_DISABLE'],
                revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                checkpoint_restart=str(args.from_checkpoint) if args.from_checkpoint else None,
                reference_root=cfg['reference_root'], teacher_unique_steps=sum(len(d['action_clipped']) for d in run.refs.values()),
                evaluation='three nominal' if args.integration else '3 x 20 frozen',
                backend='mjlab_research.Simulation', update='10 WM minibatches, one H32 actor step, 20 critic minibatches')
    save_json(out/'actual_config.json', spec)
    if args.eval_only:
        checkpoint_eval(run, out/f'eval_{run.updates:06d}', full=not args.integration)
        return

    def checkpoint():
        weights = {n:getattr(run,n).state_dict() for n in ('actor','critic','dyn')}
        weights.update(cfg=cfg, seed=args.seed, updates=run.updates, collected=run.collected,
                       optimizers=[o.state_dict() for o in opts])
        path = out/f'checkpoint_{run.updates:06d}.pt'
        torch.save(weights, path.with_suffix('.pt.tmp'))
        path.with_suffix('.pt.tmp').replace(path)
        return path

    if args.updates <= run.updates:
        raise ValueError('--updates must exceed the previous completed actor-update count')
    run.start_plant()
    checkpoint()
    checkpoint_eval(run, out/f'eval_{run.updates:06d}', full=not args.integration)
    vector_steps = cfg['wm_batches'] * cfg['wm_batch'] * run.wmc.horizon / (cfg['worlds'] * cfg['replay_ratio'])
    if not vector_steps.is_integer():
        raise ValueError('this batch configuration requires a non-integral interaction interval')
    log_path = out/'updates.jsonl'
    while run.updates < args.updates:
        evidence = run.updates in (0,1) or run.updates in cfg['milestones']
        stats = run.collect(int(vector_steps), save=evidence)
        stats.update(run.update(), actor_update=run.updates)
        with log_path.open('a') as f:
            f.write(json.dumps(stats,allow_nan=False)+'\n')
        if run.updates <= 5 or run.updates % 25 == 0:
            print(json.dumps(stats), flush=True)
        if (run.updates in cfg['milestones'] or run.updates % cfg['periodic_updates'] == 0
                or run.updates == args.updates):
            checkpoint()
            checkpoint_eval(run,out/f'eval_{run.updates:06d}',full=not args.integration)
    save_json(out/'outcome.json',dict(actor_updates=run.updates, wm_minibatch_updates=run.updates*run.wmc.num_batches,
                                     policy_transitions=run.collected, checkpoint=f'checkpoint_{run.updates:06d}.pt'))


if __name__ == '__main__':
    main()
