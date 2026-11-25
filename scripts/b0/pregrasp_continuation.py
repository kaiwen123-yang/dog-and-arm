"""u10000 reference-clock diagnostics using the original, permanently sealed full judge."""
import argparse
from contextlib import contextmanager
import csv
import json
from pathlib import Path
import subprocess
from time import perf_counter

import mujoco as mj
import numpy as np

from learning.b0.contact_events import ContactEvents, FrozenDoorReference
from learning.b0.physics import ActionMap, build, settings
from scripts.b0.eval_contact_segments import FULL_DOOR_PHASES, WarpSingleWorld, continuous_initial

OUT = Path('results/b0/standard_pregrasp_compatibility_20261125')
RAW = Path('results/raw_large/b0/pregrasp_compatibility_20261125')
PARENT = Path('results/b0/standard_official_flow_continuation_20261125/physics')
CKPT = Path('results/raw_large/b0/official_flow_continuation_20261125/checkpoint_010000.pt')
REF = Path('results/raw_large/b0/full_warp_hold_park_r1')
SIDES = {'pull': 'pull_60_train', 'push': 'push_25_train'}
DT = .002
METRICS = ('door_deg', 'door_net_N', 'left_N', 'right_N', 'tcp_handle_m', 'jaw_m',
           'both', 'gripped', 'angle_reached', 'detached', 'loaded', 'lost_ticks',
           'unloaded_ticks', 'slip_ticks', 'sat_ticks_max')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def read(path):
    return json.loads(path.read_text())


class ReferenceMonitor:
    """Scalar contact_warp.ContactPlant.step_contact predicates on this backend's solved fields."""
    def __init__(self, model, judge):
        self.judge = judge
        # The training plant selects the common nominal mobile thresholds for both sides.
        self.cfg = settings('mobile', 1)
        self.threshold = model.actuator_forcerange[:, 1] * self.cfg['sat_fraction']
        self.saturation = np.zeros(model.nu, dtype=int)
        self.lost = self.unloaded = self.sliding = 0
        self.limits = {k: round(self.cfg[k] / DT) for k in
                       ('loss_limit_s', 'unloaded_limit_s', 'sat_limit_s', 'park_slip_limit_s')}
        self.first = None
        self.range = model.jnt_range[[model.joint(f'piper_joint{i}').id for i in range(1, 7)]]

    def observe(self, step, phase, data, q0, c, capacity):
        cfg, judge = self.cfg, self.judge
        grip = phase in ('open', 'hold')
        active = phase in ('grasp', 'open', 'hold', 'release')
        free = phase in ('approach_base', 'settle', 'pregrasp', 'post_release_hold', 'stow', 'retreat_base', 'final')
        supported = bool((c.normal >= cfg['wheel_threshold_n']).all())
        both = bool((c.finger_normal > cfg['contact_threshold_n']).all())
        slip = float(np.hypot(np.nan_to_num(c.slip_long), np.nan_to_num(c.slip_lat)).max())
        self.unloaded = 0 if supported else self.unloaded + 1
        self.lost = self.lost + 1 if grip and not both else 0
        self.sliding = self.sliding + 1 if active and slip > cfg['park_slip_limit_m_s'] else 0
        self.saturation[:] = np.where(np.abs(data.actuator_force) >= self.threshold, self.saturation + 1, 0)
        w, x, y, z = q0[3:7]
        tilt = max(abs(np.arctan2(2*(w*x+y*z), 1-2*(x*x+y*y))),
                   abs(np.arcsin(np.clip(2*(w*y-z*x), -1, 1))))
        arm = data.qpos[judge.arm_q]
        net = float(np.linalg.norm(c.door_force))
        error = float(np.linalg.norm(data.site_xpos[judge.tcp] - data.site_xpos[judge.handle]))
        metrics = np.r_[c.normal, c.finger_normal, c.door_force, c.force_norm_sum, slip]
        finite = all(np.isfinite(v).all() for v in (data.qpos, data.qvel, metrics, data.actuator_force))
        # ContactMeter.unexpected records only unregistered pairs with individual positive
        # normal strictly above threshold, which is the kernel's unexpected-force predicate.
        limits = self.limits
        checks = (
            ('nonfinite', not finite), ('buffer_capacity', capacity != 0),
            ('arm_joint_limit', np.any((arm < self.range[:, 0]) | (arm > self.range[:, 1]))),
            ('unexpected_contact', bool(c.unexpected)),
            ('door_contact_outside_manipulation', free and c.force_norm_sum > cfg['contact_threshold_n']),
            ('wheel_support_or_tilt', self.unloaded >= limits['unloaded_limit_s'] or tilt >= np.deg2rad(cfg['tilt_limit_deg'])),
            ('persistent_saturation', self.saturation.max() >= limits['sat_limit_s']),
            ('lost_grip', self.lost >= limits['loss_limit_s']),
            ('persistent_grip_phase_wheel_slip', self.sliding >= limits['park_slip_limit_s']),
            ('grip_handle_error', grip and error > cfg['grasp_error_m']),
            ('door_force_limit', grip and net > cfg['grip_net_force_limit_n']))
        if self.first is None:
            for reason, fails in checks:
                if fails:
                    self.first = dict(step=step, reference_phase=phase, reason=reason, unloaded=self.unloaded,
                                      lost=self.lost, slip=self.sliding, sat_max=int(self.saturation.max()),
                                      slip_m_s=slip, door_net_N=net, handle_error_m=error,
                                      wheels_N=c.normal.tolist(), fingers_N=c.finger_normal.tolist())
                    break
        jaw = q0[judge.finger_q[0]] - q0[judge.finger_q[1]]
        angle = np.rad2deg(q0[judge.hinge_q])
        gripped = both and cfg['grasp_width_range_m'][0] <= jaw <= cfg['grasp_width_range_m'][1] and error <= cfg['grasp_error_m']
        reached = abs(angle - judge.reference.target_angle_deg) <= cfg['angle_tolerance_deg']
        return (angle, net, *c.finger_normal, error, jaw, both, gripped, reached,
                c.force_norm_sum <= cfg['contact_threshold_n'], supported,
                self.lost, self.unloaded, self.sliding, self.saturation.max())


@contextmanager
def policy_for(backend):
    paths = [REF / n for n in SIDES.values()]
    if backend == 'warp':
        from learning.b0.contact_policy import load_policy
        yield load_policy(CKPT, paths, 'cuda:0')
        return
    assert mj.__version__ == '3.3.0'
    cmd = ['bash', 'scripts/b0/env.sh', 'python', '-u', 'scripts/b0/eval_contact_segments.py',
           '--actor-worker', '--checkpoint', str(CKPT), '--device', 'cuda:0']
    with subprocess.Popen(cmd, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=1) as child:
        child.stdin.write(json.dumps(dict(paths=list(map(str, paths)))) + '\n')
        child.stdin.flush()

        def policy(path, frame, hq, hv, ha):
            request = dict(path=str(path), frame=frame, q=hq.tolist(), v=hv.tolist(), a=ha.tolist())
            child.stdin.write(json.dumps(request, allow_nan=False) + '\n')
            child.stdin.flush()
            return np.asarray(json.loads(child.stdout.readline()))

        try:
            yield policy
        finally:
            child.stdin.close()
            if child.wait():
                raise RuntimeError('Frozen Actor worker exited with an error')


def seal(backend, side, archive, output, raw, judge, d, q, v, queries, actions, peak, initial, elapsed):
    step = judge.step
    ticks = np.r_[queries, step].astype(int)
    raw.mkdir(parents=True, exist_ok=False)
    saved = dict(physics_step=ticks, qpos=np.asarray(q)[ticks], qvel=np.asarray(v)[ticks],
                 raw_action=np.asarray(actions), clipped_action=np.clip(actions, -1, 1))
    for key, arr in saved.items():
        np.save(raw / (key+'.npy'), arr, allow_pickle=False)
    fail = judge.failure
    if not judge.passed and fail is None:
        fail = dict(reason='reference_exhausted', phase=judge.phase, physics_steps=step)
    result = dict(episode=SIDES[side], segment='full', side=side, backend=backend, mujoco=mj.__version__,
                  start_substep=0, prefix_physics_steps=0, physics_steps=step, policy_calls=len(queries),
                  reference_phase_end_substep=judge.score_until_step, initial_geometry=initial,
                  final_partial_substeps=step % 10, passed=judge.terminal_event_step is not None,
                  physical_gate_pass_step=judge.terminal_event_step,
                  first_failure=fail, score_first_failure=fail, events=judge.events, actual_config=judge.cfg,
                  last_physical_observation=judge.latest, longest_ready_steps=judge.peak_ready_steps,
                  last_not_ready=judge.last_not_ready, physical_wall_seconds=elapsed, measured_peak_net_force_n=peak,
                  final_door_deg=float(np.rad2deg(d.qpos[judge.hinge_q])), score_initial_previous_action=[0.]*23,
                  score_initial_previous_action_valid=False, raw_directory=str(raw.resolve()), action_source=archive['action_source'])
    write(output/'result.json', result)
    # Score this sealed prefix with the original scorer before consulting the post-timeout trajectory.
    subprocess.run(['bash', 'scripts/b0/env.sh', 'python', '-m', 'scripts.b0.pregrasp_continuation',
                    'score', '--backend', backend, '--side', side], check=True)
    old = Path(archive['raw_directory'])
    diff = {}
    for key, arr in saved.items():
        prior = np.load(old/(key+'.npy'), mmap_mode='r')
        common = min(len(prior), len(arr))
        diff[key] = dict(same_shape=prior.shape == arr.shape, exact=np.array_equal(arr, prior),
                         shared_rows=common, max_abs_over_shared_rows=float(np.max(np.abs(prior[:common]-arr[:common]))))
    old_score = read(PARENT / f'u010000_{backend}_full' / side / 'full/nominal/return.json')
    score = read(output/'return.json')
    compare = dict(archived_result=str(PARENT / f'u010000_{backend}_full' / side / 'full/nominal/result.json'),
                   archived_reason=archive['first_failure'], same_reason=(fail or {}).get('reason')==(archive['first_failure'] or {}).get('reason'),
                   same_steps=step==archive['physics_steps'], same_event_phase_steps=
                   [(x['phase'],x['end_step']) for x in archive['events']] == [(x['phase'],x['end_step']) for x in judge.events],
                   arrays=diff, archived_fixed_effort=old_score['normalized_fixed_effort'],
                   measured_fixed_effort=score['normalized_fixed_effort'], absorbed_steps=score['absorbed_substeps'])
    write(output/'archive_comparison.json', compare)
    if result['passed']:
        from scripts.b0.eval_contact_segments import save_video
        save_video(judge.meter.model, saved['qpos'], ticks, output/'V0.mp4')
    return result


def trial(backend, side):
    cid = f'{backend}_{side}'
    output, raw = OUT/'continuation'/cid, RAW/'continuation'/cid
    # Reservation persists through interruptions and precludes inadvertent duplicate integrations.
    if (raw/'reservation.json').is_file():
        raise FileExistsError(raw)
    archive = read(PARENT / f'u010000_{backend}_full' / side / 'full/nominal/result.json')
    path = REF / SIDES[side]
    cfg = settings('mobile' if side == 'pull' else 'push', 1)
    model = build(cfg)
    assert model.opt.timestep == DT and mj.__version__ == archive['mujoco']
    meta = read(path/'metadata.json')
    assert tuple(meta['phases']) == FULL_DOOR_PHASES and meta['success'] and meta['wm_split']=='train'
    ref = FrozenDoorReference.from_episode(path, model)
    phases = np.load(path/'substeps/phase.npy', mmap_mode='r')
    stop = ref.phase_bounds['final'][1]
    assert stop == len(phases) and ref.phase_bounds['approach_base'][0] == 0
    mapping = ActionMap(model)
    world = WarpSingleWorld(model,'cuda:0') if backend=='warp' else None
    judge = ContactEvents(model, cfg, side, ref, phases=FULL_DOOR_PHASES, hold_seconds=.5, start_step=0, score_until_step=stop)
    judge.log_readiness = True
    monitor = ReferenceMonitor(model, judge)
    with policy_for(backend) as policy:
        d, (hq,hv,ha,previous), initial = continuous_initial(model,cfg,world)
        q, v = [d.qpos.copy()], [d.qvel.copy()]
        metrics, actual, actions, queries = [], [], [], []
        sealed = None
        peak = 0.
        t0 = perf_counter()
        for start in range(stop):
            if start % 10 == 0:
                hq=np.concatenate((hq[1:],d.qpos[None]))
                hv=np.concatenate((hv[1:],d.qvel[None]))
                ha=np.concatenate((ha[1:],previous[None]))
                action=np.asarray(policy(path,start//10,hq,hv,ha), dtype=np.float64)
                assert action.shape==(23,) and np.isfinite(action).all()
                if start==0:
                    write(raw/'reservation.json', dict(backend=backend,side=side,checkpoint=str(CKPT),
                                                       physics_dt=DT,initial=initial))
                previous=np.clip(action,-1.,1.)
                servo=(mapping.offset+mapping.scale*previous)*mapping.finger_factor
                actions.append(action)
                queries.append(start)
            q0, v0 = q[-1], v[-1]
            if world is None:
                d.ctrl[mapping.actuator_ids]=servo+d.qfrc_bias[mapping.dof]*mapping.bias_gain
                mj.mj_step(model,d)
            else:
                world.step(d,servo)
            step=start+1
            q.append(d.qpos.copy())
            v.append(d.qvel.copy())
            c=judge.meter.measure(d)
            rp=FULL_DOOR_PHASES[int(phases[start])]
            actual.append(FULL_DOOR_PHASES.index(judge.phase) if sealed is None else -1)
            values=monitor.observe(step,rp,d,q0,c,0 if world is None else world.overflow_bits & world.plant.contact_audit.buffer_mask)
            metrics.append(values)
            if sealed is None:
                judge.observe(d,c,q0,v0)
                peak=max(peak,judge.latest['net_door_force_n'])
                if judge.failure or judge.passed or step==stop:
                    sealed=seal(backend,side,archive,output,raw/'formal',judge,d,q,v,queries,actions,peak,initial,perf_counter()-t0)
                    if not (sealed['first_failure'] or {}).get('reason','').startswith('timeout:'):
                        break
            if sealed is not None and monitor.first:
                break
    arr=np.asarray(metrics)
    k=sealed['physics_steps']
    np.savez_compressed(raw/'continuous.npz',qpos=q,qvel=v,query_start_step=queries,raw_action=actions,
                        clipped_action=np.clip(actions,-1.,1.),reference_phase=np.asarray(phases[:step]),
                        formal_phase=np.asarray(actual),interval_metrics=arr,metric_names=np.array(METRICS))
    tail=arr[k:]
    def longest(mask):
        ix=np.flatnonzero(np.diff(np.r_[False,mask,False].astype(int))).reshape(-1,2)
        return int(max((b-a for a,b in ix),default=0))
    observed=dict(elapsed_steps=len(tail),phase_steps={name:int((phases[k:step]==i).sum()) for i,name in enumerate(FULL_DOOR_PHASES)
                                                       if (phases[k:step]==i).any()})
    if len(tail):
        col=lambda name: tail[:,METRICS.index(name)]
        observed.update(peak_door_deg=float(col('door_deg').max()),min_door_deg=float(col('door_deg').min()),
                        max_net_N=float(col('door_net_N').max()),dual_ticks=int(col('both').sum()),
                        longest_gripped_ticks=longest(col('gripped')>0),target_angle_ticks=int(col('angle_reached').sum()),
                        gripped_at_target_ticks=int(((col('gripped')>0)&(col('angle_reached')>0)).sum()),
                        observed_release_after_gripped=False)
        if np.any(col('gripped')):
            first=int(np.flatnonzero(col('gripped'))[0])
            release=(phases[k:step]==FULL_DOOR_PHASES.index('release'))&(col('detached')>0)&(col('jaw_m')>=.9*cfg['open_width_m'])
            observed['observed_release_after_gripped']=bool(release[first+1:].any())
    receipt=dict(case=cid,backend=backend,side=side,mujoco=mj.__version__,reference_last_step=stop,
                 sealed_step=k,sealed_phase=(sealed['first_failure'] or {}).get('phase'),
                 sealed_failure=(sealed['first_failure'] or {}).get('reason'),passed=sealed['passed'],
                 protocol='fixed_effort_successor_2ms_v1',physical_step=step,
                 reference_physical_first_failure=monitor.first,
                 next_query_after_seal=next((x for x in queries if x>=k),None),
                 query_start_grid_exact=bool(np.array_equal(queries,np.arange(0,step,10))),
                 diagnostic=observed,post_timeout_can_qualify=False,trajectory=str(raw/'continuous.npz'),
                 terminal='reference_monitor_failure' if monitor.first else ('reference_end' if step==stop else 'formal_stop'))
    write(output/'continuation.json',receipt)
    print(json.dumps(receipt,allow_nan=False),flush=True)


def score(backend,side):
    from scripts.b0.score_contact_return import score_case
    from learning.b0.physics import make_model
    dst=OUT/'continuation'/f'{backend}_{side}'
    result=read(dst/'result.json')
    scores=score_case(result, REF/SIDES[side],make_model('mobile' if side=='pull' else 'push'))
    write(dst/'return.json',scores)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('trial','score'))
    p.add_argument('--backend',choices=('native','warp'),required=True)
    p.add_argument('--side',choices=SIDES,required=True)
    a=p.parse_args()
    (trial if a.mode=='trial' else score)(a.backend,a.side)
