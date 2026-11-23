"""Train O1 contact-segment WM/Actor/Critic from a verified B0-03 lineage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

os.environ.setdefault('TORCH_COMPILE_DISABLE','1')
import numpy as np
import torch
import yaml

from learning.b0.contact_model import SCHEMA
from learning.b0.contact_training import ContactRun


def add_grip_windows(run, directory):
    """H7 dynamics data only, from the preregistered training cohorts."""
    from learning.b0.contact_policy import DoorMotions
    from learning.b0.contact_replay import ContactWindows
    from scripts.b0.h32_fit_recovery_wm import load_cohorts

    registration = json.loads((directory / 'registration.json').read_text())
    original = Path(registration['anchor']).parent / 'actual_config.json'
    source = json.loads(original.read_text())['cfg']
    paths = [Path(registration['reference_directory']) / name for name in source['references']]
    motions = DoorMotions(paths, run.rep, run.device)
    cohorts = json.loads((directory / 'cohorts.json').read_text())
    rows = [row for row in cohorts if row['split'] == 'train']
    expected = [seed for split, seed in registration['allocation'] if split == 'train']
    if not rows or [row['seed'] for row in rows] != expected or len(set(expected)) != len(rows):
        raise ValueError('Expected the complete preregistered training split')
    episodes, _ = load_cohorts(rows, paths, motions, run.model, run.device)
    run.grip_windows = ContactWindows(episodes, 7)
    return dict(seeds=expected, lanes=len(episodes), transitions=sum(len(e.action) for e in episodes),
                h7_windows=len(run.grip_windows.starts), source_behavior=registration['anchor'],
                source=str(directory), use='physical state, clipped action and successor for H7 WM only')


def main():
    process_start = time.monotonic()
    started_unix = time.time()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path('config/b0/contact_servo_cloud.yaml'))
    parser.add_argument('--run',required=True,help='Fresh result directory name')
    parser.add_argument('--updates',type=int,required=True)
    parser.add_argument('--resume',type=Path,help='Complete cohort-boundary state in a different run')
    args=parser.parse_args()
    if args.run in ('','.','..') or Path(args.run).name!=args.run or args.updates<=0:
        parser.error('Specify a new run name and positive absolute update endpoint')
    def resolved(path):
        config=yaml.safe_load(path.read_text())
        return resolved(Path(config['base'])) | config if 'base' in config else config
    cfg=resolved(args.config)
    if cfg['actor_horizon']!=32 or cfg['physics_dt']!=.002 or cfg['policy_dt']!=.02:
        raise ValueError('Contact schema requires H32 and 10 x 2 ms')
    torch.manual_seed(0)
    np.random.seed(0)
    torch.set_float32_matmul_precision('high')
    source=torch.load(cfg['actor_checkpoint'],weights_only=False,map_location='cpu')
    base=yaml.safe_load(Path('config/b0/free_servo_cloud.yaml').read_text())
    if (source['seed'],source['updates'],source['collected'],source['cfg'])!=(0,1000,1088000,base):
        raise ValueError('Unexpected B0-03 lineage/configuration')
    if cfg.get('calibrated_actor'):
        calibrated=torch.load(cfg['calibrated_actor'],weights_only=False,map_location='cpu')
        if (calibrated['source']!=cfg['actor_checkpoint'] or calibrated['seed']!=0
                or calibrated['cfg']!=base or calibrated['supervised_updates']<=0):
            raise ValueError('Unexpected lineage of calibrated contact actor')
        source['actor']=calibrated['actor']
    wm=torch.load(cfg['wm_checkpoint'],weights_only=False,map_location='cpu')
    if wm['schema']!=SCHEMA or wm['seed']!=0:
        raise ValueError('Unexpected contact WM initializer')
    paths=Path(cfg['reference_directory'])
    refs=[paths/n for n in cfg['references']]
    teachers=refs+[paths/n for n in cfg['additional_teacher_episodes']]
    for p in teachers:
        if not (p/'metadata.json').is_file():
            raise FileNotFoundError(p)
    run=ContactRun(cfg,refs,teachers,source,wm,'cuda:0',from_free_anchor=args.resume is None)
    grip_data = add_grip_windows(run, Path(cfg['wm_grip_cohorts'])) if cfg.get('wm_grip_cohorts') else None
    out=Path('results/b0')/args.run
    raw=Path('results/raw_large/b0')/args.run
    out.mkdir(exist_ok=False)
    raw.mkdir(exist_ok=False)
    metadata=dict(cfg=cfg,run=args.run,seed=0,git_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  physics='MuJoCo Warp; exact 10 x 2 ms held targets',device=torch.cuda.get_device_name(),
                  migration='Actor incl. normalizers strict load; critic input layer initialized, shape-compatible hidden and output restored; door WM initialized from explicitly listed pretraining checkpoint. Joint optimizers fresh unless --resume.',
                  initialization=dict(actor=str(cfg.get('calibrated_actor',cfg['actor_checkpoint'])),wm=str(cfg['wm_checkpoint']),resume=str(args.resume) if args.resume else None),
                  max_step_reward=run.policy.wm_env.max_step_reward,max_critic_value=run.policy._v_max,
                  validation_excluded=True,cohort_truncation=cfg['cohort_steps'],requested_endpoint=args.updates)
    metadata['actor_class'] = type(run.actor).__name__
    metadata['started_unix'] = started_unix
    metadata['policy_learner'] = type(run.policy).__name__
    metadata['wm_horizons'] = list(run.learners)
    if run.sampler is not None:
        metadata['return_sampling'] = dict(config=vars(run.sampler.cfg), frames=run.sampler.frame_count,
                  global_bins=run.sampler.bin_count, eligible_by_motion=[len(x) for x in run.eligible],
                  reset_support="fixed mjlab bin->frame distribution conditioned on eligible physical prefixes")
    if run.schedule is not None:
        metadata['ratio_schedule'] = dict(ratio=cfg['replay_ratio'], wm_stored_positions=run.schedule.positions,
                  clock="complete replay-eligible 20ms lane intervals; updates grouped after each physical cohort")
    if grip_data is not None:
        metadata['supplemental_wm_data'] = grip_data
    metadata['execution_source_sha256'] = {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in
        [Path(__file__).resolve().relative_to(Path.cwd()), Path('learning/b0/model.py'),
         *sorted(Path('learning/b0').glob('contact*.py')), args.config]
    }
    if 'peak_force_checkpoint' in cfg:
        metadata['peak_force_checkpoint_sha256'] = hashlib.sha256(Path(cfg['peak_force_checkpoint']).read_bytes()).hexdigest()
    (out/'actual_config.json').write_text(json.dumps(metadata,indent=2)+'\n')
    def save(count):
        state=dict(actor=run.actor.state_dict(),critic=run.critic.state_dict(),dyn=run.dyn.state_dict(),
                   cfg=cfg,updates=count,collected=run.total,seed=0,schema=SCHEMA)
        torch.save(state,out/f'checkpoint_{count:06}.pt')
        state.update(optimizers=[o.state_dict() for o in run.optimizer_list()],
                     replay=list(run.replay.chunks),simulated=run.simulated,
                     cpu_rng=torch.get_rng_state(),gpu_rng=torch.cuda.get_rng_state(),numpy_rng=np.random.get_state())
        if run.schedule is not None:
            state['ratio_state'] = run.schedule.state_dict()
        if run.sampler is not None:
            state['return_sampler_state'] = run.sampler.state_dict()
        tmp=out/'cohort_state.pt.tmp'
        torch.save(state,tmp)
        tmp.replace(out/'cohort_state.pt')
    start=0
    if args.resume:
        state=torch.load(args.resume,map_location='cuda:0',weights_only=False)
        if state['cfg']!=cfg or state['schema']!=SCHEMA:
            raise ValueError('Contact resume requires identical resolved configuration')
        for key in ('actor','critic','dyn'):
            getattr(run,key).load_state_dict(state[key])
        for o,s in zip(run.optimizer_list(),state['optimizers'],strict=True):
            o.load_state_dict(s)
        run.replay.chunks.extend(state['replay'])
        run.total,run.simulated=state['collected'],state['simulated']
        if run.schedule is not None:
            run.schedule.load_state_dict(state['ratio_state'])
        if run.sampler is not None:
            run.sampler.load_state_dict(state['return_sampler_state'])
        torch.set_rng_state(state['cpu_rng'].cpu())
        torch.cuda.set_rng_state(state['gpu_rng'].cpu())
        np.random.set_state(state['numpy_rng'])
        start=state['updates']
        del state
    if args.updates<=start:
        raise ValueError('The requested endpoint must be after the input checkpoint')
    save(start)
    last=start
    try:
        with (out/'updates.jsonl').open('x',buffering=1) as log:
            for count in range(start+1,args.updates+1):
                if run.schedule is None:
                    data=run.collect(raw/f'cohort_{count:06}' if count in (start+1,50,200,1000) else None)
                else:
                    before_valid, before_simulated = run.total, run.simulated
                    while not run.schedule.pending:
                        cohort = run.schedule.cohorts + 1
                        sampled = run.collect(raw/f'cohort_{cohort:06}' if cohort in (1,50,200,1000) else None)
                        with (out/'cohorts.jsonl').open('a') as collected:
                            collected.write(json.dumps(dict(cohort=cohort, due=run.schedule.pending, **sampled))+'\n')
                    data = dict(valid_transitions=run.total-before_valid, cumulative_valid_transitions=run.total,
                                simulated_lane_intervals=run.simulated-before_simulated, cohort=run.schedule.cohorts)
                update=run.update()
                if run.schedule is not None:
                    run.schedule.pending -= 1
                    data['remaining_updates_on_cohort'] = run.schedule.pending
                row=dict(update=count,process_elapsed_s=time.monotonic()-process_start,**data,**update)
                log.write(json.dumps(row,allow_nan=False)+'\n')
                last=count
                if count in cfg['diagnostic_updates'] or count%1000==0 or count==args.updates:
                    save(count)
                if count<=3 or count%25==0:
                    print(json.dumps(row),flush=True)
    except Exception as e:
        (out/'failure.json').write_text(json.dumps(dict(last_complete_update=last,error=repr(e),
                      collected=run.total,simulated=run.simulated),indent=2)+'\n')
        raise
    (out/'outcome.json').write_text(json.dumps(dict(actor_updates=last,wm_minibatches=last*10,
                    critic_minibatches=last*20,valid_online_transitions=run.total,
                    simulated_lane_intervals=run.simulated,elapsed_process_s=time.monotonic()-process_start,
                    started_unix=started_unix,finished_unix=time.time()),indent=2)+'\n')


if __name__=='__main__':
    main()
