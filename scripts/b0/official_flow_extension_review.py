"""Compare scored nodes for unattended handoff. Leave mixed physical evidence for review."""
import csv
import json
from pathlib import Path

OUT = Path('results/b0/standard_official_flow_continuation_20261125')
PARENT = Path('results/b0/standard_official_flow_continuation_20261124')


def read(path):
    return json.loads(path.read_text())


def cases(root, node, backend, side):
    with (root/'physical_cases.csv').open() as stream:
        rows=[r for r in csv.DictReader(stream)
              if int(r['update'])==node and r['backend']==backend and r['side']==side]
    contacts=[r for r in rows if r['task']!='full']
    full,=[r for r in rows if r['task']=='full']
    assert len(contacts)==(0 if node==7500 and backend=='native' else 5)
    ready=read(OUT/f'readiness_u{node:06}.json')
    observation,=[r for r in ready if r['side']==side and r['backend']==backend]
    entries=read(root/'servo'/f'closedloop_u{node:06}_formal_2ms_r0.json')['rows']
    return dict(passed_contacts=sorted(r['task'] for r in contacts if r['passed']=='True'),
        attempted_contacts=len(contacts),full_events=full['completed'].split(',') if full['completed'] else [],
        full_success=full['passed']=='True',full_steps=int(full['physics_steps']),first_failure=full['failure'],
        failed_phase=full['failed_phase'],ready=observation['terminal'],window=observation['window_complete'],
        window_metrics={k:observation.get(k) for k in ('endpoint_m_median_abs','endpoint_rad_median_abs',
            'speed_m_s_median_abs','yaw_rate_deg_s_median_abs','best_ready_ratio','four_wheel_min_N')},
        wheel_support=observation['wheel_support_summary'],
        pure_actor={r['start']:r['longest_dual_ticks'] for r in entries if r['side']==side})


def review():
    decision=OUT/'decision_u010000.json'
    if decision.exists():
        raise FileExistsError(decision)
    manifest=read(OUT/'baseline_manifest.json')
    assert manifest['cumulative_steps']=={'actor':10000,'wm':100000,'critic':200000}
    inputs={}
    for node,root in ((4991,PARENT),(7500,OUT),(10000,OUT)):
        inputs[node]={side:{b:cases(root,node,b,side) for b in ('warp','native')} for side in ('pull','push')}
    # These two-backend confirmations can justify extension directly. A single
    # backend milestone, a pure-Actor acquisition or tracking-only progress
    # still needs the original targeted replay / bilateral window review.
    new={}
    retained={}
    repeated_window_losses={}
    for side in ('pull','push'):
        old=inputs[4991][side]
        current=inputs[10000][side]
        passes=[set(current[b]['passed_contacts'])-set(old[b]['passed_contacts']) for b in old]
        parent_events=set(old['warp']['full_events'])|set(old['native']['full_events'])
        phases=set(current['warp']['full_events'])&set(current['native']['full_events'])
        new[side]=dict(confirmed_new_contacts=sorted(set.intersection(*passes)),
                       confirmed_new_full_phases=sorted(phases-parent_events))
        losses=[]
        for b in old:
            history=[inputs[u][side][b] for u in (4991,7500,10000)]
            if all(x['window'] for x in history):
                for metric,value in history[0]['window_metrics'].items():
                    if value is None or metric=='four_wheel_min_N':
                        continue
                    observed=[x['window_metrics'][metric] for x in history[1:]]
                    if all(v is not None and (v<value if metric=='best_ready_ratio' else v>value) for v in observed):
                        losses.append([b,metric,value,*observed])
        repeated_window_losses[side]=losses
        retained[side]=not losses and all(
            set(old[b]['passed_contacts'])<=set(current[b]['passed_contacts']) and
            set(old[b]['full_events'])<=set(current[b]['full_events']) and
            (len(current[b]['full_events'])>len(old[b]['full_events']) or
             (current[b]['full_steps']>=old[b]['full_steps'] and current[b]['first_failure']==old[b]['first_failure'])) and
            all(current[b]['pure_actor'][key]>=v for key,v in old[b]['pure_actor'].items()) and
            current[b]['ready']['best'] is not None and
            (old[b]['ready']['phase']!=current[b]['ready']['phase'] or
             current[b]['ready']['best']>=old[b]['ready']['best'])
            for b in ('warp','native'))
    justified=[s for s,other in (('pull','push'),('push','pull')) if any(new[s].values()) and retained[other]]
    qualify=any((r['contact_pass']==10 or r['full_success']) for r in manifest['physics'])
    detail=dict(node=10000,physical_inputs=inputs,confirmed=new,opposite_side_checks=retained,repeated_window_losses=repeated_window_losses,
        unambiguous_progress_sides=justified,qualification_or_video_followthrough=qualify,
        readiness_windows='readiness_windows.json',u7500_windows='readiness_u007500.json',
        u10000_windows='readiness_u010000.json',scope='An unclassified result is pending review with the full registered criteria.')
    output=OUT/'extension_review_u010000.json'
    if justified and not qualify:
        output=decision
        detail.update(extend=True,status='confirmed_original_physics_extension',target=15000)
    else:
        detail.update(extend=None,status='qualification_review' if qualify else 'physical_review_required')
    tmp=output.with_suffix('.tmp')
    tmp.write_text(json.dumps(detail,indent=2,allow_nan=False)+'\n')
    tmp.replace(output)
    print(detail['status'],output,flush=True)
    return 0 if output==decision else 3


if __name__=='__main__':
    raise SystemExit(review())
