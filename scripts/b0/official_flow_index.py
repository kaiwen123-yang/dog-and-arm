"""Assemble the independent round manifest from recorded physical cases and optimizer counters."""
import argparse
import csv
import json
import sys
from importlib.metadata import version
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import torch
from scripts.b0.official_flow import OUT, RAW, NODES, io

SOURCE='695f3d7b41a1b1774e8955c31ae02d98733e28eb'
NOMINAL = dict(root_position_rmse_m=.01,root_orientation_rmse_deg=np.rad2deg(.02),
               arm_position_rmse_rad=.1,finite_joint_velocity_rmse_rad_s=3.14,
               door_angle_rmse_deg=2.,door_rate_rmse_rad_s=.1)


def csv_file(name,rows):
    with (OUT/name).open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def physics(u,backend,protocol):
    folder=OUT/'physics'/f'u{u:06}_{backend}_{protocol}'
    summary=io.read(folder/'evaluation.json')
    rows=[]
    for path in sorted(folder.glob('*/*/nominal/result.json')):
        r=io.read(path)
        score=io.read(path.with_name('return.json'))
        assert str(RAW/f'checkpoint_{u:06}.pt')==summary['checkpoint']
        assert r['backend']==backend and r['mujoco']==('3.3.0' if backend=='native' else '3.16.0')
        assert r['passed']==score['physical_passed'] and r['physics_steps']==score['executed_substeps']
        fail=r['first_failure'] or {}
        measured=r['last_physical_observation'] or {}
        errors=score['tracking_errors'] or {}
        goal=r['actual_config']['target_angle_deg'] if protocol=='full' else None
        reason=fail.get('reason')
        force=fail.get('door_net_force_n') if reason=='door_force_limit' else None
        rows.append(dict(update=u,backend=backend,protocol=protocol,side=r['side'],task=r['segment'],
            passed=r['passed'],events=len(r['events']),completed=','.join(e['phase'] for e in r['events']),
            failure=reason,failed_phase=fail.get('phase'),measured_s=score['measured_duration_s'],
            planned_s=score['planned_duration_s'],survival_fraction=score['measured_duration_s']/score['planned_duration_s'],
            physics_steps=r['physics_steps'],prefix_steps=r['prefix_physics_steps'],actor_calls=r['policy_calls'],
            final_door_deg=r['final_door_deg'],target_deg=goal,angle_over_target=r['final_door_deg']/goal if goal else None,
            station_error_m=measured.get('station_error_m'),applicable_failure_force_N=force,
            failure_force_over_6N=force/6 if force is not None else None,
            force_peak_N=r['measured_peak_net_force_n'],physical_score_with_absorbing_failure=score['normalized_fixed_effort'],
            record=str(path.relative_to(OUT)),**{k:errors.get(k) for k in NOMINAL},
            **{k+'_over_nominal':errors[k]/den if k in errors else None for k,den in NOMINAL.items()}))
    assert len(rows)==summary['evaluated']==(2 if protocol=='full' else 5)
    return rows


def full_clock(row):
    case=io.read(OUT/row['record'])
    cfg=case['actual_config']
    ref=Path('results/raw_large/b0/full_warp_hold_park_r1')/case['episode']
    phase_names=io.read(ref/'metadata.json')['phases']
    phases=np.array(phase_names)[np.load(ref/'substeps/phase.npy',mmap_mode='r')]
    q=np.load(ref/'substeps/qpos.npy',mmap_mode='r')
    v=np.load(ref/'substeps/qvel.npy',mmap_mode='r')
    ref_stop=np.flatnonzero(phases=='settle')[-1]
    recorded_station=q[ref_stop,:2]
    last=case['last_physical_observation']
    k=case['physics_steps']-1
    if last['phase'] in ('approach_base','settle'):
        station=np.array(cfg['base_xyz_m'][:2])
    elif last['phase'] in ('retreat_base','final'):
        station=np.array(case['initial_geometry']['parking_xy_m'])
    else:
        station=recorded_station
    return dict(update=row['update'],backend=row['backend'],side=row['side'],last_solve_start_s=.002*k,
        phase_actual=last['phase'],phase_reference_at_same_time=phases[k],tolerance_m=cfg['position_tol_m'],
        actual_station_error_m=last['station_error_m'],actual_over_tol=last['station_error_m']/cfg['position_tol_m'],
        heading_tolerance_deg=cfg['heading_tol_deg'],confirmed_zone_violation=(
            ('XY exceeds tolerance; heading independent' if last['station_error_m']>cfg['position_tol_m'] else 'heading exceeds tolerance with XY inside')
            if row['failure']=='operation_station_drift' else None),
        reference_station_error_m=float(np.linalg.norm(q[k,:2]-station)),
        reference_horizontal_speed_m_s=float(np.linalg.norm(v[k,:2])),actual_speed_m_s=last['speed_m_s'],
        final_tcp_handle_m=last['tcp_handle_error_m'],door_deg=last['door_deg'],failure=row['failure'])


def index(stop):
    nodes=[n for n in NODES if n<=stop]
    updates=[json.loads(line) for line in (OUT/'updates.jsonl').read_text().splitlines()]
    assert [r['update'] for r in updates]==list(range(1,stop+1))
    for r in updates:
        u=r['update']
        assert r['steps']==dict(actor=u,wm=10*u,critic=20*u)
        assert r['statistics']['wm_state']==r['valid']+50479 and r['statistics']['proprio']==r['valid']
    observed=io.read(OUT/'recovery.json')
    assert observed['update']==stop
    nodesummary=[]
    cases=[]
    wm=[]
    for u in nodes:
        for backend in ('warp','native'):
            if backend=='native' and u not in (0,200,500,1000):
                continue
            contact=[] if backend=='native' and u==0 else [r for protocol in ('v1','hold_margin_v2')
                for r in physics(u,backend,protocol)]
            full=physics(u,backend,'full')
            cases.extend(contact+full)
            nodesummary.append(dict(update=u,backend=backend,contact_cases=len(contact),
                contact_pass=sum(r['passed'] for r in contact),contact_events=sum(r['events'] for r in contact),
                first_2ms_over6=sum(r['physics_steps']==1 and r['failure']=='door_force_limit' for r in contact),
                full_cases=len(full),full_pass=sum(r['passed'] for r in full),sides=[{k:r[k] for k in (
                    'side','passed','completed','failed_phase','failure','measured_s','planned_s','final_door_deg',
                    'physical_score_with_absorbing_failure','station_error_m')} for r in full]))
        scores=io.read(OUT/'validation'/f'u{u:06}'/'scores.json')
        line=dict(update=u,**scores['values'])
        wm.append(line)
    for line in wm:
        for k in ('pull_grip','push_grip','pull_multimode','push_multimode'):
            line[k+'_over_warm_start']=line[k]/wm[0][k]
    interface=io.read(OUT/'interface.json')
    axes=[]
    for row,unit,home,canonical in zip(interface['actions'],interface['physical_per_effort'],
            interface['home_canonical'],interface['canonical_per_effort'],strict=True):
        axes.append(dict(**row,physical_home=row['offset']+row['scale']*home,
            physical_lower=row['offset']-row['scale'],physical_upper=row['offset']+row['scale'],
            physical_per_base_effort=unit,physical_exploration_sigma=.1*unit,
            canonical_per_base_effort=canonical,exploration_sigma_over_canonical_half_span=.1*canonical))
    csv_file('action_units.csv',axes)
    csv_file('physical_cases.csv',cases)
    csv_file('full_clocks.csv',[full_clock(row) for row in cases if row['task']=='full'])
    csv_file('wm_nodes.csv',wm)
    free={str(u):io.read(OUT/'free'/f'u{u:06}'/'summary.json') for u in (0,200,500,1000) if u<=stop}
    valids=observed['valid']
    physical=observed['simulated']*80
    ends=[u for u in (200,500,1000) if u<=stop]
    wall=sum(updates[u-1]['wall_s'] for u in ends)
    tz=timezone(timedelta(hours=8))
    milestones=[]
    for u in nodes:
        weight=RAW/f'checkpoint_{u:06}.pt'
        solver=RAW/f'resume_{u:06}'/('solver.npz' if u else 'state.pt')
        milestones.append(dict(update=u,weights=str(weight),weight_bytes=weight.stat().st_size,
            frozen_file_beijing=datetime.fromtimestamp(weight.stat().st_mtime,tz).isoformat(),
            resume_boundary_written_beijing=datetime.fromtimestamp(solver.stat().st_mtime,tz).isoformat()))
    io.write(OUT/'milestones.json',dict(measure='file completion times on the training host',nodes=milestones))
    videos=sorted(str(p.relative_to(OUT)) for p in OUT.glob('physics/*/*/full/nominal/video_manifest.json'))
    full_records=[row for row in cases if row['task']=='full']
    io.write(OUT/'video_manifest.json',dict(protocol='B0_FULL_TASK_VIDEO_PROTOCOL',scope='full_from_start nominal',
        attempts=len(full_records),successful=sum(row['passed'] for row in full_records),videos=videos,
        attempts_and_verdicts=[{k:row[k] for k in ('update','backend','side','passed','completed','failure',
            'measured_s','planned_s','actor_calls','record')} for row in full_records]))
    manifest=dict(method='SuperMimic-M1Piper-standard-v1',execution_recipe='official_flow_s0_v1',seed=0,
        base=SOURCE,supermimic='abc124c1bd5976341034668af3d12c087f2f1f55',mjlab='dd51a9fcc98791a2f0b018b3c7f71a3eefd5ecdd',
        created_beijing=datetime.now(timezone(timedelta(hours=8))).isoformat(),stage='B0-04',
        initialization='WM only: +850 dyn and bound normalizers. Fresh Actor, Critic, Muon/Adam, replay, sampler and Ratio.',
        direct_weight_lineage=[
            dict(source='free_s0_cloud_servo_r2 u1000 (subset of WM layers)',wm=10000,ancestor_H32=1000,ancestor_physical_transitions=1088000),
            dict(source='contact_s0_wm_held_r1 +200 then held_r2 to cumulative 2000',wm=2000),
            dict(source='lanes_wm_v1 +1000 to response_wm_v1 +0',wm=1000),
            dict(source='fine C20 rebased +1000 with 50479 normalization inputs',wm=1000),
            dict(source='joint_contact actual retained +850 of +990',wm=850)],
        ancestral_wm_minibatches=14850,previous_round_accounting='30 diagnostic + 991 charged adaptation (990 retained, 1 discarded); only 850 retained steps on the selected parent, no new qualified H32 in that round.',
        prior_manifest='results/b0/standard_joint_contact_20261124/baseline_manifest.json',
        counters=observed['steps'],new_cost=dict(valid_transitions=valids,physics_lane_intervals=observed['simulated'],
            microsteps=physical,aggregate_simulated_seconds=physical*.00025,wall_seconds_training_segments=wall,
            wall_scope='sum of live training segment timers through each endpoint; excludes initialization, endpoint checkpoint writes, separate scoring, and time between segments',
            wm_samples=stop*10*2048,wm_scored_successors=stop*10*2048*7,imagined_steps=stop*4096*32,
            actual_stored_positions_per_valid_transition=stop*10*8*2048/valids,ratio_charged_positions_per_update=10*8*2048,ratio_target=16,valid_per_steady_update=10240,
            skipped_before_legal_h7=sum(json.loads(line)['skipped'] for line in (OUT/'readiness.jsonl').read_text().splitlines()),final_ratio=observed['ratio']),
        environment=dict(python=sys.version.split()[0],torch=str(torch.__version__),torch_cuda=torch.version.cuda,
            training_mujoco=version('mujoco'),mujoco_warp=version('mujoco-warp'),warp_lang=version('warp-lang'),
            device=interface['device'],native_scoring_mujoco='3.3.0',tensor_math='float32 high',torch_compile_disable=True),
        budget_decisions=[p.name for p in sorted(OUT.glob('budget_*.json'))],
        torch_peak_allocated_bytes=max(r['gpu_peak_bytes'] for r in updates),
        source_implementation_commit='f109bbea6e5abfb1dd0a0e80dacdd76d8d9d8473',
        nodes=nodes,physical=nodesummary,free_warp=free,wm_long_denominators=scores['long_counts'],
        error_denominators=NOMINAL,final_candidate=None,full_bilateral_return=None,
        paper_comparison=dict(SONIC_reference=.90,near_band=.88,full_successes=sum(r['passed'] for r in cases if r['task']=='full'),
            note='Failed full-start trials retain their measured-prefix score with absorbing suffix separately. Qualifying completed bilateral return is NA.'),
        qualifications=dict(D=None,C=None,seed1=None,seed2=None,H=None),video_manifests=videos,
        recovery=dict(host='autodl-d57',cwd=str(Path.cwd()),**observed),
        files=dict(video='video_manifest.json',milestones='milestones.json',first='first_update.json',rechecked_draws='first_draw_recheck.json',config='interface.json',
            full_clocks='full_clocks.csv',action_units='action_units.csv',optimizer_log='updates.jsonl',case_rows='physical_cases.csv',wm_nodes='wm_nodes.csv'))
    assert not any(r['passed'] for r in cases if r['task']=='full') or videos
    if any(n['contact_pass']==10 for n in nodesummary):
        raise ValueError('A complete contact nominal gate requires the registered D/C qualification follow-through')
    io.write(OUT/'baseline_manifest.json',manifest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stop',type=int)
    index(p.parse_args().stop)
