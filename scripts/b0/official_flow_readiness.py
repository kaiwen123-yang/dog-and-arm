"""Register parent failure windows and score the original microstep readiness observations."""
import argparse
import numpy as np
from scripts.b0.official_flow import OUT, PARENT_OUT, PARENT_UPDATE, io
from scripts.b0.official_flow_tracking import trial
from pathlib import Path


def register():
    target = OUT/'readiness_windows.json'
    if target.exists():
        raise FileExistsError(target)
    rows = []
    for backend in ('warp', 'native'):
        for side in ('pull', 'push'):
            case, raw, _ = trial(PARENT_UPDATE, backend, side)
            events = np.load(raw/'physical_events_2ms.npy')
            original = dict(zip(case['physical_event_columns'], events.T))
            phase = case['last_physical_observation']['phase']
            active = original['phase_id'] == case['phases'].index(phase)
            steps = original['step'][active].astype(int)
            assert len(steps) and np.all(np.diff(steps)==1)
            with np.load(raw/'solved_servo_trace.npz') as z:
                columns = z.files
                assert len(z['step']) == case['physics_steps']
            rows.append(dict(backend=backend, side=side, actual_phase=phase, start=int(steps[0]),
                end=int(steps[-1]), n=len(steps), source=str(raw), original_verdict=case['first_failure'],
                old_event_columns=case['physical_event_columns'], old_servo_columns=columns,
                original_ready_best=int(original['continuous_ready_steps'][active].max()),
                missing_for_replay=['four per-step wheel normal loads','original per-phase last_not_ready'],
                metrics=['median endpoint distance / 3 mm','median endpoint rotation / .02 rad',
                         'best continuous ready / required'] if phase=='pregrasp' else
                        ['median planar speed / settle threshold','median absolute yaw rate / threshold',
                         'best continuous ready / required']))
    io.write(target,dict(parent=PARENT_UPDATE,units='inclusive absolute 2 ms steps, anchored to the original parent failure phase',
        window_rule='Every step must exist and have the registered event phase. Short or different-phase windows are unscored. Compare physical milestones separately.',
        tracking_only='Both sides must improve failure-related metrics on complete windows without earlier physical violation. Inspect load/contact failures independently; magnitude of joint tracking alone is insufficient.',
        windows=rows))


def score(u):
    windows=io.read(OUT/'readiness_windows.json')['windows']
    rows=[]
    for window in windows:
        backend,side=window['backend'],window['side']
        folder='diagnostic_replay' if u==PARENT_UPDATE else 'physics'
        case=io.read(OUT/folder/f'u{u:06}_{backend}_full'/side/'full/nominal/result.json')
        raw=Path(case['raw_directory'])
        d=dict(zip(case['readiness_columns'], np.load(raw/'readiness.npy').T))
        reproduction=None
        if u==PARENT_UPDATE:
            original=io.read(PARENT_OUT/'physics'/f'u{u:06}_{backend}_full'/side/'full/nominal/result.json')
            difference={}
            for name in ('qpos','qvel','raw_action','physics_step'):
                old=np.load(Path(original['raw_directory'])/(name+'.npy'))
                new=np.load(raw/(name+'.npy'))
                difference[name]=dict(same_shape=old.shape==new.shape,exact=np.array_equal(old,new),
                    max_abs=float(np.max(np.abs(old-new))) if old.shape==new.shape else None)
            reproduction=dict(trajectory_comparison=difference,
                original_reason=(original['first_failure'] or {}).get('reason'),
                same_reason=(original['first_failure'] or {}).get('reason')==(case['first_failure'] or {}).get('reason'),
                same_steps=original['physics_steps']==case['physics_steps'],same_events=original['events']==case['events'],
                same_event_phase_and_step=[(e['phase'],e['end_step']) for e in original['events']]==
                                          [(e['phase'],e['end_step']) for e in case['events']])
        target=(d['step']>=window['start']) & (d['step']<=window['end'])
        phase_id=case['phases'].index(window['actual_phase'])
        complete=int(target.sum())==window['n'] and bool(np.all(d['actual_phase'][target]==phase_id))
        observed=[]
        for phase in dict.fromkeys(d['actual_phase'].astype(int)):
            ix=np.flatnonzero(d['actual_phase']==phase)
            breaks=ix[1:][(d['current'][ix[:-1]]>0)&(d['current'][ix[1:]]==0)]
            bad=ix[d['ready'][ix]==0]
            j=int(breaks[0]) if len(breaks) else (int(bad[0]) if len(bad) else None)
            detail=None if j is None else {k:float(v[j]) if np.isfinite(v[j]) else None for k,v in d.items()}
            observed.append(dict(phase=case['phases'][phase],interruptions=len(breaks),first_ready_break_or_first_nonready=detail))
        result=dict(backend=backend,side=side,node=u,window_complete=complete,required_n=window['n'],
            actual_n=int(target.sum()),window_phase_match_n=int(np.sum(target & (d['actual_phase']==phase_id))),
            parent_replay_check=reproduction,failure=case['first_failure'],terminal=case['readiness'],phase_breaks=observed)
        loads=np.stack([d[f'wheel_{i}_N'] for i in range(4)],axis=1)
        low=(loads < case['actual_config']['wheel_threshold_n']).any(axis=1)
        changes=np.flatnonzero(np.diff(np.r_[False,low,False].astype(int))).reshape(-1,2)
        result['wheel_support_summary']=dict(threshold_N=case['actual_config']['wheel_threshold_n'],
            longest_unloaded_steps=int(max((b-a for a,b in changes),default=0)),
            terminal_unloaded_start_step=int(changes[-1,0]+1) if len(changes) and low[-1] else None,
            terminal_unloaded_steps=int(changes[-1,1]-changes[-1,0]) if len(changes) and low[-1] else 0)
        if complete:
            for key in ('endpoint_m','endpoint_rad','xy_m','heading_deg','speed_m_s','yaw_rate_deg_s'):
                a=np.abs(d[key][target])
                result[key+'_median_abs']=float(np.median(a)) if np.isfinite(a).all() else None
            result['best_ready_ratio']=float((d['current'][target]/d['required'][target]).max())
            result['four_wheel_min_N']=np.stack([d[f'wheel_{i}_N'][target] for i in range(4)]).min(axis=1).tolist()
        rows.append(result)
    io.write(OUT/f'readiness_u{u:06}.json', rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--register',action='store_true')
    parser.add_argument('nodes',nargs='*',type=int)
    args=parser.parse_args()
    if args.register:
        register()
    for node in args.nodes:
        score(node)
