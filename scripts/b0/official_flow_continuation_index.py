"""Independent continuation accounting, anchored to durable snapshots and individual verdicts."""
import csv
import json
from pathlib import Path
import numpy as np
from scripts.b0.official_flow import NEW_SEGMENT,OUT,RAW,PARENT_OUT,io
from scripts.b0.official_flow_index import physics,full_clock,csv_file
from scripts.b0.official_flow_tracking import compare


def index(stop):
    parent=io.read(OUT/'parent.json')
    latest=io.read(OUT/f'node_{stop:06}.json')
    inherited=io.read(PARENT_OUT/'baseline_manifest.json')
    updates=[json.loads(l) for l in (OUT/'updates.jsonl').read_text().splitlines()
             if json.loads(l)['update']<=stop]
    assert [r['update'] for r in updates]==list(range(parent['update']+1,stop+1))
    for r in updates:
        u=r['update']
        assert r['steps']==dict(wm=u*10,actor=u,critic=u*20)
        assert r['statistics']['proprio']==r['valid'] and r['statistics']['wm_state']==r['valid']+50479
    assert updates[-1]['valid']==latest['valid']
    nodes=[u for u in (1500,2000,3000,4000,5000) if u<=stop]
    if NEW_SEGMENT:
        nodes=[u for u in (7500,10000,12500,15000) if u<=stop]
        if not nodes or nodes[-1]!=stop:
            raise ValueError('Index a scored major physics node')
    if (OUT/'coverage_u004991.json').exists() and 4991<=stop and 4991 not in nodes:
        nodes.append(4991)
    if stop not in nodes:
        nodes.append(stop)
    nodes.sort()
    cases,clocks,servo,free,summary,videos=[],[],[],[],[],[]
    for u in nodes:
        tag=f'u{u:06}'
        r=io.read(OUT/f'node_{u:06}.json')
        coverage=io.read(OUT/f'coverage_{tag}.json')
        assert coverage['segment_covered'] and coverage['valid']==r['valid']-parent['valid']
        assert coverage['simulated_intervals']==r['simulated']-parent['simulated']
        compare(u)
        for backend in ('warp','native'):
            protocols= ('v1','hold_margin_v2') if backend=='warp' or u in (3000,5000,10000,15000) or (
                OUT/'physics'/f'{tag}_{backend}_hold_margin_v2/evaluation.json').exists() else ()
            contacts=[c for protocol in protocols for c in physics(u,backend,protocol)]
            full=physics(u,backend,'full')
            for row in contacts+full:
                case=io.read(OUT/row['record'])
                last=case['last_physical_observation'] or {}
                row['heading_at_failure_or_end_deg']=last.get('heading_error_deg')
                row['xy_over_20mm']=last['station_error_m']/.02 if last else None
                row['heading_over_2deg']=last['heading_error_deg']/2 if last else None
                if row['task']=='full':
                    clocks.append(full_clock(row)|dict(heading_deg=last['heading_error_deg']))
                    if case['passed']:
                        location=(OUT/row['record']).parent
                        video=io.read(location/'video_manifest.json')
                        assert (location/video['video']).stat().st_size>0
                        videos.append(dict(manifest=str(location.relative_to(OUT)/'video_manifest.json'),**video))
            cases+=contacts+full
            summary.append(dict(node=u,backend=backend,contact_cases=len(contacts),
                contact_pass=sum(x['passed'] for x in contacts),contact_events=sum(x['events'] for x in contacts),
                full_cases=len(full),full_success=sum(x['passed'] for x in full),
                full=[dict(side=c['side'],completed=c['completed'],phase=c['failed_phase'],failure=c['failure'],
                    xy_m=c['station_error_m'],heading_deg=c['heading_at_failure_or_end_deg']) for c in full]))
        table=io.read(OUT/'servo'/f'closedloop_{tag}_formal_2ms_r0.json')['rows']
        assert len(table)==6
        for case in table:
            servo.append(dict(node=u,**{k:case[k] for k in ('start','phase','actor_queries','scored_ticks',
                'both_ticks','longest_dual_ticks')},dual_seconds=case['longest_dual_ticks']*.002))
        for task,block in io.read(OUT/'free'/tag/'summary.json').items():
            assert block['attempted']==20
            free.append(dict(node=u,task=task,**block))
    from scripts.b0.official_flow_solved_cases import summaries
    last,joints=summaries(cases)
    keys=dict.fromkeys(k for r in last for k in r)
    csv_file('last_physical_intervals.csv',[keys|r for r in last])
    csv_file('wheel_arm_jaw.csv',joints)
    csv_file('physical_cases.csv',cases)
    csv_file('full_clocks.csv',clocks)
    csv_file('pure_actor_entries.csv',servo)
    csv_file('free_summary.csv',free)
    io.write(OUT/'video_manifest.json',dict(eligible_protocol='B0_FULL_TASK_VIDEO_PROTOCOL',
        full_attempts=sum(x['full_cases'] for x in summary),successes=len(videos),videos=videos))
    delta={k:latest['steps'][k]-parent['steps'][k] for k in parent['steps']}
    val=latest['valid']-parent['valid']
    physical=latest['simulated']-parent['simulated']
    discarded=[]
    for file in sorted(OUT.glob('failure_at_*.json')):
        if file.name.endswith('.rollback.json'):
            continue
        fail=io.read(file)
        # A failure may contain later retained frozen nodes. Charge only work
        # after the last durable node in that particular attempt.
        receipt=file.with_suffix('.rollback.json')
        if not receipt.exists(): raise ValueError(f'Missing checked recovery boundary for {file}')
        start=io.read(receipt)
        discarded.append(dict(failure=file.name,recovery_update=start['update'],
            steps={k:fail['steps'][k]-start['steps'][k] for k in delta},
            valid=fail['valid']-start['valid'],lane_intervals=(fail['tick']-start['clock'])*4096,
            interrupted_partial_tick_excluded=True))
    charged={k:delta[k]+sum(x['steps'][k] for x in discarded) for k in delta}
    # The first durable u1001 was saved before per-process IDs were introduced.
    wall={}
    for row in updates:
        segment=str(row.get('segment_started_unix','durable_u1001'))
        wall[segment]=max(wall.get(segment,0.),row['wall_s'])
    result=dict(method=inherited['method'],execution_recipe=inherited['execution_recipe'],
        source_main='bdb72d8f7019688b6e51ba0cd2d083a5bef90532',parent_run_commit='51a0133802983b65602949000099e7d18fa8e835',
        supermimic=inherited['supermimic'],mjlab=inherited['mjlab'],seed=0,parent=parent,
        parent_manifest=str(PARENT_OUT/'baseline_manifest.json'),direct_wm_lineage=inherited['direct_wm_lineage' if NEW_SEGMENT else 'direct_weight_lineage'],
        retained_cfg='config/b0/official_flow_s0_v1.yaml',cfg_equality_checked_at_load=True,
        parent_restore_checks='restored_u001000.json',durable_u1001_reload='restored_u001001.json',
        first_new_update='first_resumed_update.json',training_processes='sessions.jsonl',
        u1001_implementation_commit='88448d10566eef38f96df9be4433875454ec2739',
        optimizer_core=inherited['optimizer_core' if NEW_SEGMENT else 'environment'],
        settings=dict(worlds=4096,wm_batch=2048,actor_batch=4096,actor_horizon=32,wm_stored_frames=8,
            wm_scored_transitions=7,wm_batches_per_actor=10,critic_batches_per_actor=20,ratio=16,
            online_statistics=True,actor_input='proprio/history10/goal540',training_dt=.00025,servo_dt=.002,
            policy_dt=.02,formal_dt=.002,coefficient=.50625),
        diagnostics=dict(factorial='wm_factorial/factorial.json',backend='backend/comparison.json',
            fixed_tracking_windows='tracking_windows.json',current_policy=[
                str(p.relative_to(OUT)) for p in sorted((OUT/'current_policy').glob('*/scores.json'))]),
        inherited_wm_ancestor_minibatches=14850,parent_steps=parent['steps'],cumulative_steps=latest['steps'],
        retained_new_steps=delta,charged_new_steps=charged,discarded_attempts=discarded,
        new_valid=val,cumulative_valid=latest['valid'],new_lane_intervals=physical,new_microsteps=physical*80,
        new_prefix_lane_intervals=coverage['prefix_lane_intervals'],new_valid_terminal=coverage['complete_terminal_rows'],
        retained_training_wall_s=sum(wall.values()),wall_by_process_through_retained_update_s=wall,
        wall_scope='monotonic time after restore to last retained update in each process, includes internal checkpoints except its own final write; evaluation and discarded attempts excluded',
        aggregate_new_simulated_seconds=physical*.02,
        new_ratio_stored_positions_per_valid=delta['wm']*2048*8/val,
        new_wm_windows=delta['wm']*2048,new_wm_scored_successors=delta['wm']*2048*7,
        new_imagined_steps=delta['actor']*4096*32,
        nodes=nodes,physics=summary,free=free,pure_actor=servo,video_manifests=videos,
        recovery=dict(host='autodl-d57',cwd=str(Path.cwd()),**latest),
        V0=len(videos),stage='B0-04',candidate=None,qualified_bilateral_return=None,
        paper=dict(sonic_reference=.90,registered_near_band=.88),D=None,C=None,seeds_1_2=None,H=None,
        scope='Individual failed full attempts retain their measured-prefix diagnostics; qualified scores require success.')
    if NEW_SEGMENT:
        manifest=io.read(OUT/'run_manifest.json')
        result.update(source_main=manifest['source_main'],parent_run_commit='0124ad75b61f35224033cdfc9f445228afb89f2e',
            registration='run_manifest.json',parent_restore_checks='restored_u004991.json',
            first_named_reload='restored_u005000.json',previous_round_charged_steps=inherited['charged_new_steps'],
            nodes=[5000,*nodes],u5000_formal_physics='not rescored',diagnostics=dict(
                parent_ready='readiness_u004991.json', windows='readiness_windows.json',
                node_readiness=[f'readiness_u{u:06}.json' for u in nodes],
                tracking='tracking_windows.json',current_policy=result['diagnostics']['current_policy']))
        for stale in ('durable_u1001_reload','u1001_implementation_commit'):
            del result[stale]
    if any(row['contact_pass']==10 for row in summary) or videos:
        result['qualification_followthrough_required']=True
    decision=OUT/'budget_decision.json'
    if decision.is_file() and io.read(decision)['actual_last_node']==stop:
        result.update(close=io.read(decision),coverage_archive='coverage_archive.json',
            milestones='milestones.json',terminal_restore=f'restored_u{stop:06}.json',
            confirmed_sustained_contact='repeat_u004000.json',case_rows='physical_cases.csv',
            physical_ratios='last_physical_intervals.csv',actuator_ratios='wheel_arm_jaw.csv',
            complete_video_register='video_manifest.json')
    if NEW_SEGMENT:
        result.pop('confirmed_sustained_contact',None)
    io.write(OUT/'baseline_manifest.json',result)
