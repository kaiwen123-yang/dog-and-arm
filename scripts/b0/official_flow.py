"""Pinned SuperMimic online seed-zero run with the M1/Piper physical interfaces."""
import argparse
import fcntl
from contextlib import ExitStack, nullcontext
import json
import os
import shutil
from pathlib import Path
import time
from unittest.mock import patch

os.environ.setdefault("TORCH_COMPILE_DISABLE", "1")
import numpy as np
import torch
import yaml
from supermimic.learners import policy_learner, wm_learner

from learning.b0.contact_model import CONTEXT_NAMES, SCHEMA, contact_context, contact_state
from learning.b0.contact_training import ContactRun
from learning.b0.physics import make_model
from scripts.b0 import dynamics_h32_pilot as io
from scripts.b0.dynamics_h32_probe import rng_state, restore_rng

OUT = Path("results/b0/standard_official_flow_20261124")
RAW = Path("results/raw_large/b0/official_flow_20261124")
PARENT_OUT, PARENT_RAW = OUT, RAW
NEW_SEGMENT = os.environ.get("B0_FLOW_SEGMENT") == "continuation_20261125"
CONTINUATION = NEW_SEGMENT or os.environ.get("B0_FLOW_SEGMENT") == "continuation"
if CONTINUATION:
    OUT = Path("results/b0/standard_official_flow_continuation_20261124")
    RAW = Path("results/raw_large/b0/official_flow_continuation_20261124")
PARENT_UPDATE = 4991 if NEW_SEGMENT else 1000
if NEW_SEGMENT:
    PARENT_OUT, PARENT_RAW = OUT, RAW
    OUT = Path("results/b0/standard_official_flow_continuation_20261125")
    RAW = Path("results/raw_large/b0/official_flow_continuation_20261125")
CONFIG = Path("config/b0/official_flow_s0_v1.yaml")
NODES = (0, 1, 10, 50, 100, 200, 500, 1000, 1500, 2000, 3000, 4000, 5000)

if NEW_SEGMENT:
    NODES = (5000, 7500, 10000, 12500, 15000)


def stats(run):
    return {name: int(norm.count.item()) for name, norm in (
        ("wm_state", run.dyn.state_normalizer), ("wm_proc", run.dyn.action_normalizer),
        ("proprio", run.actor.obs_normalizer), ("goal", run.actor.goal_normalizers["motion"]))}


def build(cfg):
    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])
    torch.set_float32_matmul_precision("high")
    refs = list(map(Path, cfg["reference_paths"]))
    payload = torch.load(cfg["wm_checkpoint"], map_location="cpu", weights_only=False)
    run = ContactRun(cfg, refs, [], None, {"dyn":payload["dyn"]}, "cuda:0")
    assert payload["batches"] == 850 and payload["physics_dt"] == run.model.opt.timestep
    assert float(payload["c"]) == run.rep.substep_coeff
    assert all(len(o.state) == 0 for o in run.optimizer_list())
    assert not run.offline and set(run.learners) == {7}
    assert run.schedule.positions == 10 * run.b * 8 and run.steps == 1
    mapping = run.plant.mapping
    np.testing.assert_allclose(run.dyn.action_offset.cpu(), mapping.offset, atol=1e-6)
    np.testing.assert_allclose(run.dyn.action_scale.cpu(), mapping.scale, atol=1e-6)
    for key, value in run.dyn.state_dict().items():
        torch.testing.assert_close(value.cpu(), payload["dyn"][key], rtol=0, atol=0)
    checks = []
    for path in refs:
        meta = run.bank.metas[path.name]
        side = meta["task"]
        own = make_model('push' if side == 'push' else 'mobile')
        torch.testing.assert_close(run.ctx[int(side == 'push')], contact_context(own, side, run.device))
        action = np.load(path/'action_clipped.npy', mmap_mode='r')
        targets = np.load(path/'physical_target.npy', mmap_mode='r')
        np.testing.assert_allclose(action * mapping.scale + mapping.offset, targets, atol=1e-5)
        q = np.load(path/'qpos.npy', mmap_mode='r')
        v = np.load(path/'qvel.npy', mmap_mode='r')
        checks.append(dict(id=path.name, side=side, intervals=len(action), split=meta["wm_split"],
            full=bool(meta.get("full_task")), arm_q_min=q[:,23:29].min(0).tolist(),
            arm_q_max=q[:,23:29].max(0).tolist(), arm_v_min=v[:,22:28].min(0).tolist(),
            arm_v_max=v[:,22:28].max(0).tolist(), jaw_width_range=np.percentile(q[:,29]-q[:,30], [0,100]).tolist(),
            physical_min=targets[:,16:].min(0).tolist(), physical_max=targets[:,16:].max(0).tolist()))
    state = contact_state(run.bank.qpos[:1], run.bank.qvel[:1])
    rep = run.rep.represent(state)
    wm_goal, actor_goal = run.bank.goals(run.rep,run.bank.motion_starts[:1],state[:,:7])
    assert (state.shape[1], rep.shape[1], wm_goal.shape[1], actor_goal.shape[1]) == (63,75,570,542 if cfg.get("feature_mode") in ("zero", "measured") else 540)
    assert run.actor.standard_action.equal(run.rep.reward_unit)
    info = dict(config=cfg, initializer_keys=list(payload), inherited_batches=payload["batches"],
        normalizers=stats(run), context_names=CONTEXT_NAMES, pull_push_context=run.ctx.tolist(),
        clock=run.plant.clock.metadata(), actions=mapping.describe(run.model),
        home_canonical=run.actor.home_action.tolist(), canonical_per_effort=run.actor.standard_action.tolist(),
        physical_per_effort=(run.actor.standard_action.cpu().numpy()*mapping.scale).tolist(),
        references=checks, replay_positions_per_update=run.schedule.positions, lr_groups=[
            [float(g['lr']) for g in opt.param_groups] for opt in run.optimizer_list()],
        optimizers=[type(opt).__name__ for opt in run.optimizer_list()], initial_steps=io.optimizer_steps(run),
        device=torch.cuda.get_device_name(), available_device_bytes=torch.cuda.mem_get_info()[0])
    return run, info


def save(run, u, rolling=False):
    label = "rolling" if rolling else "node"
    if CONTINUATION and (OUT/f'{label}_{u:06}.json').exists():
        raise FileExistsError(f'Committed node u{u} is immutable')
    directory = RAW / f"resume_{u:06}"
    if NEW_SEGMENT and rolling and not directory.exists():
        # The two previous generations stay readable while the next is being written.
        expected=(PARENT_RAW/f'resume_{PARENT_UPDATE:06}'/'state.pt').stat().st_size+1024**3
        if shutil.disk_usage(RAW).free < expected:
            backing=(RAW/'resume_005000').resolve().parent/'rolling'
            backing.mkdir(exist_ok=True)
            if shutil.disk_usage(backing).free >= expected:
                slot=backing/directory.name
                slot.mkdir(exist_ok=False)
                directory.symlink_to(slot,target_is_directory=True)
    directory.mkdir(exist_ok=True)
    package = io.package(run,u)
    io.atomic_torch(package, RAW/f"checkpoint_{u:06}.pt")
    data = dict(optimizer=[o.state_dict() for o in run.optimizer_list()], rng=rng_state(),
        schedule=run.schedule.state_dict(), sampler=run.sampler.state_dict(), total=run.total,
        simulated=run.simulated, last_episode=getattr(run,'last_episode',0), lanes=getattr(run,'lanes',None),
        replay={k:v for k,v in vars(run.replay).items() if k not in ('index','receipt')},
        counters={k:getattr(run.plant,k) for k in (*io.COUNTERS,'servo_bias')})
    io.atomic_torch(data, directory/'state.pt')
    if run.simulated:
        with patch.object(io,'SHARED',directory):
            io.solver_snapshot(run,False)
    receipt = dict(update=u, checkpoint=str(RAW/f"checkpoint_{u:06}.pt"),
        state=str(directory), clock=run.replay.clock, simulated=run.simulated, valid=run.total,
        steps=io.optimizer_steps(run), stats=stats(run), ratio=run.schedule.state_dict())
    if NEW_SEGMENT:
        # Snapshot serialization is synchronous. Read both torch containers and
        # the closed solver archive before advertising or retiring a generation.
        import zipfile
        ck = torch.load(receipt['checkpoint'], map_location='cpu', weights_only=False, mmap=True)
        st = torch.load(directory/'state.pt', map_location='cpu', weights_only=False, mmap=True)
        assert ck['cfg'] == run.cfg and st['total'] == run.total and st['replay']['clock'] == run.replay.clock
        with zipfile.ZipFile(directory/'solver.npz') as z:
            assert z.testzip() is None
    io.write(OUT/f'{label}_{u:06}.json', receipt)
    io.write(OUT/'recovery.json', receipt)
    if rolling and io.read(OUT/'recovery.json') == receipt:
        for obsolete in sorted(OUT.glob('rolling_*.json'))[:-2]:
            old = io.read(obsolete)
            i = old['update']
            directory = RAW/f'resume_{i:06}'
            checkpoint = RAW/f'checkpoint_{i:06}.pt'
            assert i < u and i not in NODES and i > PARENT_UPDATE
            assert old['state'] == str(directory) and old['checkpoint'] == str(checkpoint)
            assert not (OUT/f'node_{i:06}.json').exists()
            io.write(OUT/'retired_rolling'/obsolete.name, old)
            obsolete.unlink()
            for name in ('state.pt', 'solver.npz'):
                (directory/name).unlink()
            if directory.is_symlink():
                slot=directory.resolve()
                assert slot==(RAW/'resume_005000').resolve().parent/'rolling'/directory.name
                directory.unlink()
                slot.rmdir()
            else:
                directory.rmdir()
            checkpoint.unlink()


def restore(run, receipt=None):
    if receipt is None:
        receipt = io.read(OUT/'recovery.json')
    package = torch.load(receipt['checkpoint'],weights_only=False,map_location=run.device)
    if package['cfg'] != run.cfg:
        raise ValueError('The recovery configuration changed')
    for key in ('dyn','actor','critic'):
        getattr(run,key).load_state_dict(package[key])
    directory = Path(receipt['state'])
    data = torch.load(directory/'state.pt',weights_only=False,map_location=run.device)
    for opt, saved in zip(run.optimizer_list(),data['optimizer'],strict=True):
        opt.load_state_dict(saved)
    run.sampler.load_state_dict(data['sampler'])
    run.schedule.load_state_dict(data['schedule'])
    for key in ('total','simulated','last_episode'):
        setattr(run,key,data[key])
    vars(run.replay).update(data['replay'])
    if data['lanes'] is not None:
        run.lanes=data['lanes']
        with patch.object(io,'SHARED',directory):
            io.solver_snapshot(run,True)
        for key,value in data['counters'].items():
            getattr(run.plant,key).copy_(value)
    restore_rng(data['rng'])
    assert io.optimizer_steps(run) == receipt['steps'] and stats(run) == receipt['stats']
    assert run.schedule.state_dict() == receipt['ratio']
    assert (run.total, run.simulated, run.replay.clock) == (receipt['valid'], receipt['simulated'], receipt['clock'])
    return receipt['update']


def observer(original, norms):
    def step(optimizers, loss, params, max_norm, *args):
        norm = original(optimizers, loss, params, max_norm, *args)
        norms.append(torch.stack((loss.detach(), norm.detach())))
        return norm
    return step


def retain_interrupted_rows(update, tick):
    # Keep post-checkpoint work inspectable when restarting from an older saved node.
    archive=OUT/'interrupted'/f'{time.time_ns()}_after_u{update:06}'
    for file in RAW.glob('countclock_*.pt'):
        if int(file.stem.split('_')[1])>tick:
            dest=RAW/'interrupted'/archive.name
            dest.mkdir(parents=True,exist_ok=True)
            file.rename(dest/file.name)
    for filename,field,limit in (('updates.jsonl','update',update),('collection.jsonl','tick',tick),
                                 ('readiness.jsonl','tick',tick),('physical_contact_counts.jsonl','tick',tick)):
        path=OUT/filename
        if not path.exists():
            continue
        kept,extra=[],[]
        for line in path.read_text().splitlines(keepends=True):
            try:
                durable=json.loads(line)[field]<=limit
            except json.JSONDecodeError:
                durable=False
            (kept if durable else extra).append(line)
        if extra:
            archive.mkdir(parents=True,exist_ok=True)
            (archive/filename).write_text(''.join(extra))
            temp=path.with_suffix('.tmp')
            temp.write_text(''.join(kept))
            temp.replace(path)


def map_observation_history(run, scratch):
    # Relocate the physical storage of already populated history pages. The
    # current episode, ring indices and all CUDA random draws stay on device.
    scratch.mkdir(parents=True, exist_ok=True)
    size=0
    for page, fields in sorted(run.replay.pages.items()):
        src=fields['history']
        file=scratch/f'history_{page:03}.bin'
        host=torch.from_file(str(file),shared=True,size=src.numel(),dtype=src.dtype).reshape(src.shape)
        host.copy_(src)
        if not torch.equal(host.to(src.device),src):
            raise RuntimeError(f'Observation history copy mismatch on page {page}')
        fields['history']=host
        size+=host.nbytes
    torch.cuda.empty_cache()
    return dict(pages=len(run.replay.pages),bytes=size,dtype=str(src.dtype),each_page_exact=True,
                scope="storage only; all sampled observations transferred losslessly to original CUDA device")


def host_saved_activations(limit, buffers):
    # Byte-preserving transport for autograd's saved inputs on a shared device.
    # RNG, forward/backward kernels, parameters, losses and optimizer calls stay on CUDA.
    moved=slot=0
    def pack(tensor):
        nonlocal moved,slot
        if (tensor.device.type=='cuda' and tensor.ndim>=2 and tensor.shape[0]==4096
                and tensor.nbytes>=4*1024**2 and moved<limit):
            moved+=tensor.nbytes
            if slot==len(buffers):
                buffers.append(torch.empty_like(tensor,device='cpu',pin_memory=True))
            host=buffers[slot]
            if host.shape!=tensor.shape or host.dtype!=tensor.dtype:
                raise RuntimeError('Fixed graph activation layout changed')
            slot+=1
            host.copy_(tensor.detach(),non_blocking=True)
            return tensor.device,host
        return tensor.detach()
    def unpack(saved):
        return saved[1].to(saved[0],non_blocking=True) if isinstance(saved,tuple) else saved
    return torch.autograd.graph.saved_tensors_hooks(pack,unpack)


def validate_parent(path, receipt):
    expected = PARENT_OUT/'recovery.json'
    if path.resolve()!=expected.resolve() or receipt!=io.read(expected) or receipt['update']!=PARENT_UPDATE:
        raise ValueError(f'Expected the registered u{PARENT_UPDATE} parent')
    if NEW_SEGMENT:
        spec=io.read(Path('results/b0/official_flow_review_20261125/next_registration.json'))['parent_recovery']
        for key in ('state','checkpoint','steps','clock','valid'):
            assert receipt[key]==spec[key], key
        assert receipt['stats']==spec['statistics']
        assert all(receipt['ratio'][k]==spec['ratio'][k] for k in ('pending','previous_clock'))


def train(stop, resume, parent=None, host_history=None, host_activation_gib=0):
    from scripts.b0.official_flow_coverage import save_counting_fields
    if parent is not None and (not CONTINUATION or resume or (OUT/'recovery.json').exists()):
        raise ValueError('A parent receipt is only valid on entry to a new continuation')
    if CONTINUATION and not (resume or parent):
        raise ValueError('An exact recovery is required for this segment')
    interval = 100
    if NEW_SEGMENT:
        if stop not in NODES or host_history or host_activation_gib:
            raise ValueError("Use registered stops and the original GPU path")
        if stop > 10000 and not io.read(OUT/'decision_u010000.json')['extend']:
            raise ValueError("The u10000 physics decision is required for extension")
        remaining = dict(actor=100, wm=1000, critic=2000)
        for failure in OUT.glob('failure_at_*.json'):
            if failure.name.endswith('.rollback.json'):
                continue
            spent = io.read(failure)['steps']
            retained = io.read(failure.with_suffix('.rollback.json'))['steps']
            for key in remaining:
                delta = spent[key] - retained[key]
                assert delta >= 0
                remaining[key] -= delta
        interval = min(remaining['actor'], remaining['wm']//10, remaining['critic']//20)
        if interval < 1:
            raise ValueError(f"Rollback allowance exhausted: {remaining}")
    cfg = yaml.safe_load(CONFIG.read_text())
    run, info = build(cfg)
    run.log_physical_dual = NEW_SEGMENT
    OUT.mkdir(parents=True,exist_ok=True)
    RAW.mkdir(parents=True,exist_ok=True)
    if resume or parent:
        if resume and CONTINUATION:
            # node_N is the publication point for all three files. A process
            # can stop after publishing it but before refreshing the latest pointer.
            nodes=sorted([*OUT.glob('node_*.json'), *OUT.glob('rolling_*.json')], key=lambda p: int(p.stem.split('_')[-1]))
            receipt=io.read(nodes[-1] if nodes else OUT/'recovery.json')
            io.write(OUT/'recovery.json',receipt)
        else:
            receipt = io.read(parent or OUT/'recovery.json')
        if parent:
            validate_parent(parent,receipt)
        u=restore(run, receipt)
        if host_history is not None:
            io.write(OUT/f'history_storage_from_u{u:06}.json',map_observation_history(run,host_history))
        if parent:
            from scripts.b0.official_flow_restore_check import verify_loaded
            verify_loaded(run, receipt)
            io.write(OUT/'parent.json', receipt)
            io.write(OUT/'interface.json', io.read(PARENT_OUT/'interface.json'))
        if CONTINUATION:
            save_counting_fields(run, u)
        retain_interrupted_rows(u,run.replay.clock)
    else:
        if (OUT/'recovery.json').exists():
            raise FileExistsError('Use the recorded recovery boundary')
        io.write(OUT/'interface.json',info)
        u=0
        save(run,u)
    # The captured CUDA graph reuses these pinned addresses on every replay.
    activation_buffers=[]
    started=time.monotonic()
    start_wall=time.time()
    start_update=u
    last_save=u
    if CONTINUATION:
        io.append(OUT/'sessions.jsonl',dict(started_unix=start_wall,from_update=u,from_clock=run.replay.clock,
            stop=stop,host_history=bool(host_history),host_activation_gib=host_activation_gib,
            start_steps=io.optimizer_steps(run),cfg_matches_checkpoint=bool(resume or parent)))
    while u < stop:
        try:
            cohort = run.collect()
            if NEW_SEGMENT:
                counts = cohort.pop('physical_contact_counts')
                io.append(OUT/'physical_contact_counts.jsonl',dict(tick=run.replay.clock, **counts))
            if CONTINUATION and run.replay.clock % 500 == 0:
                save_counting_fields(run, u)
            if run.replay.clock <= 20 or run.replay.clock % 10 == 0 or run.schedule.pending:
                io.append(OUT/'collection.jsonl',dict(tick=run.replay.clock, **cohort,
                    ratio=run.schedule.state_dict(), statistics=stats(run), wall_s=time.monotonic()-started))
            due=run.schedule.pending
            while due and u < stop:
                due -= 1
                run.schedule.pending -= 1
                if not len(run.replay.positions(7)[1]):
                    io.append(OUT/'readiness.jsonl',dict(tick=run.replay.clock,valid=run.total,skipped=1))
                    continue
                first=(u==0)
                norms, policy_norms = [], []
                if first:
                    run.replay.receipt=[]
                with ExitStack() as scope:
                    if first:
                        for module, seq in ((wm_learner,norms),(policy_learner,policy_norms)):
                            scope.enter_context(patch.object(module,'_optimize_step',observer(module._optimize_step,seq)))
                    wm=run.learners[7].update(run.replay.windows(7,run.b) for _ in range(10))
                    if not torch.stack(list(wm.values())).isfinite().all():
                        raise FloatingPointError('nonfinite WM optimizer result')
                    with (host_saved_activations(host_activation_gib*1024**3,activation_buffers)
                          if host_activation_gib else nullcontext()):
                        policy=run.policy.update()
                metrics={k:float(v) for k,v in (wm|policy).items()}
                if not all(np.isfinite(list(metrics.values()))):
                    raise FloatingPointError(str(metrics))
                u+=1
                steps=io.optimizer_steps(run)
                assert steps==dict(wm=10*u,actor=u,critic=20*u), steps
                row=dict(update=u,tick=run.replay.clock,valid=run.total,simulated=run.simulated,
                    steps=steps,metrics=metrics,ratio=run.schedule.state_dict(),statistics=stats(run),
                    gpu_peak_bytes=torch.cuda.max_memory_allocated(),wall_s=time.monotonic()-started)
                if CONTINUATION:
                    row.update(segment_from_update=start_update,segment_started_unix=start_wall)
                if first:
                    assert len(norms)==10 and len(policy_norms)==21 and len(run.replay.receipt)==11
                    arrays=torch.stack(norms+policy_norms).tolist()
                    assert np.isfinite(arrays).all()
                    np.savez_compressed(OUT/'first_draws.npz',**{f'h7_{i+1}' if i<10 else 'actor':
                        group for i,group in enumerate(run.replay.receipt)})
                    run.replay.receipt=None
                    io.write(OUT/'first_update.json',row|dict(wm_loss_preclip_norm=arrays[:10],
                        actor_loss_preclip_norm=arrays[10],critic_loss_preclip_norm=arrays[11:],
                        draw_columns=['lane','absolute_first_tick_zero_based'], online_only=True))
                io.append(OUT/'updates.jsonl',row)
                print(f"u{u} valid={run.total} actual_steps={steps}",flush=True)
                if CONTINUATION and u==PARENT_UPDATE+1:
                    io.write(OUT/'first_resumed_update.json', row)
                if u==750:
                    save_counting_fields(run,u)
                if host_activation_gib:
                    # Warp's captured forward/reset graphs allocate outside the PyTorch cache.
                    torch.cuda.empty_cache()
                if u in NODES or u==stop or (host_activation_gib and u==1001):
                    if CONTINUATION:
                        save_counting_fields(run, u)
                    save(run,u)
                    last_save=u
                elif NEW_SEGMENT and u-last_save >= interval:
                    save(run,u,rolling=True)
                    last_save=u
        except BaseException as exc:
            failure=OUT/f'failure_at_{run.replay.clock:06}_u{u:06}.json'
            if failure.exists():
                failure=failure.with_stem(failure.stem+f'_{time.time_ns()}')
            io.write(failure,
                dict(error=repr(exc), completed=u,steps=io.optimizer_steps(run),tick=run.replay.clock,
                     valid=run.total,gpu_free_total=torch.cuda.mem_get_info(), peak=torch.cuda.max_memory_allocated()))
            if CONTINUATION:
                save_counting_fields(run, u)
            raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop',type=int,default=200)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--parent-recovery',type=Path)
    parser.add_argument('--host-history',type=Path)
    parser.add_argument('--host-activation-gib',type=int,default=0)
    args=parser.parse_args()
    RAW.mkdir(parents=True,exist_ok=True)
    with (RAW/'.training.lock').open('a') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX | fcntl.LOCK_NB)
        train(args.stop,args.resume,args.parent_recovery,args.host_history,args.host_activation_gib)
