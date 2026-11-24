"""Pinned SuperMimic online seed-zero run with the M1/Piper physical interfaces."""
import argparse
from contextlib import ExitStack
import json
import os
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
CONFIG = Path("config/b0/official_flow_s0_v1.yaml")
NODES = (0, 1, 10, 50, 100, 200, 500, 1000)


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
    assert (state.shape[1], rep.shape[1], wm_goal.shape[1], actor_goal.shape[1]) == (63,75,570,540)
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


def save(run, u):
    directory = RAW / f"resume_{u:06}"
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
    io.write(OUT/'recovery.json',dict(update=u, checkpoint=str(RAW/f"checkpoint_{u:06}.pt"),
        state=str(directory), clock=run.replay.clock, simulated=run.simulated, valid=run.total,
        steps=io.optimizer_steps(run), stats=stats(run), ratio=run.schedule.state_dict()))


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
    return receipt['update']


def observer(original, norms):
    def step(optimizers, loss, params, max_norm, *args):
        norm = original(optimizers, loss, params, max_norm, *args)
        norms.append(torch.stack((loss.detach(), norm.detach())))
        return norm
    return step


def train(stop, resume):
    cfg = yaml.safe_load(CONFIG.read_text())
    run, info = build(cfg)
    OUT.mkdir(parents=True,exist_ok=True)
    RAW.mkdir(parents=True,exist_ok=True)
    if resume:
        u=restore(run)
    else:
        if (OUT/'recovery.json').exists():
            raise FileExistsError('Use the recorded recovery boundary')
        io.write(OUT/'interface.json',info)
        u=0
        save(run,u)
    started=time.monotonic()
    while u < stop:
        try:
            cohort = run.collect()
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
                if u in NODES or u==stop:
                    save(run,u)
        except Exception as exc:
            io.write(OUT/f'failure_at_{run.replay.clock:06}_u{u:06}.json',
                dict(error=repr(exc), completed=u,steps=io.optimizer_steps(run),tick=run.replay.clock,
                     valid=run.total,gpu_free_total=torch.cuda.mem_get_info(), peak=torch.cuda.max_memory_allocated()))
            raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stop',type=int,default=200)
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    train(args.stop,args.resume)
