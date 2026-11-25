"""Recompute frozen event predicates and separate same-clock TCP tracking from reference progress."""
import argparse
import csv
import gzip
import json
from pathlib import Path

import numpy as np

OLD = Path('results/b0/standard_official_flow_continuation_20261125')
REF = Path('results/raw_large/b0/full_warp_hold_park_r1')
OUT = Path('results/b0/standard_pregrasp_compatibility_20261125')
RAW = Path('results/raw_large/b0/pregrasp_compatibility_20261125')
DT = .002


def read(path):
    return json.loads(path.read_text())


def write(name, value):
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT/name).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def case_at(u, backend, side):
    folder = 'diagnostic_replay' if u == 4991 else 'physics'
    path = OLD/folder/f'u{u:06}_{backend}_full'/side/'full/nominal/result.json'
    case = read(path)
    raw = Path(case['raw_directory'])
    obs = dict(zip(case['readiness_columns'], np.load(raw/'readiness.npy').T))
    return case, raw, obs, REF/case['episode'], path


def register():
    states = []
    for side in ('pull','push'):
        case, raw, obs, ref, path = case_at(10000,'warp',side)
        k = obs['step'].astype(int)-1
        phase = case['phases'].index('pregrasp')
        allowed = ((k%10==0) & (obs['actual_phase']==phase) & (obs['reference_phase']==phase)
                   & (obs['ramp']==1))
        ids = np.flatnonzero(allowed)
        for i in np.unique(ids[[0,-1]]) if len(ids) else []:
            states.append(dict(side=side, frame=int(k[i]//10), step_2ms=int(k[i]),
                               seconds=float(k[i]*DT), source=str(path), raw=str(raw),
                               episode=ref.name, eligible_count=len(ids)))
    document = dict(selection='u10000 formal Warp, absolute interval-start k divisible by 10, original ramp and actual/reference pregrasp. First and last eligible, deduplicated.',
                    states=states,missing_sides=[s for s in ('pull','push') if not any(a['side']==s for a in states)])
    if (OUT/'states.json').exists():
        assert read(OUT/'states.json') == document
    else:
        write('states.json', document)
    return document


def longest(mask):
    spans=np.diff(np.flatnonzero(np.diff(np.r_[False,mask,False].astype(int))).reshape(-1,2),axis=1)
    return int(spans.max()) if len(spans) else 0


def fk(model, data, qpos):
    import mujoco as mj
    tcp=model.site('p4_grasp').id
    xyz=np.empty((len(qpos),3))
    orient=np.empty((len(qpos),3,3))
    roots=np.empty_like(orient)
    for i,q in enumerate(qpos):
        data.qpos[:]=q
        mj.mj_kinematics(model,data)
        xyz[i]=data.site_xpos[tcp]
        orient[i]=data.site_xmat[tcp].reshape(3,3)
        mj.mju_quat2Mat(roots[i].ravel(),q[3:7])
    return xyz,orient,roots


def rotate(rot,v):
    return np.einsum('nij,nj->ni',rot,v)


def norms(x):
    return np.linalg.norm(x,axis=-1)


def filled_min(k,mask,dist,rot):
    indices=np.flatnonzero(mask)
    if not len(indices):
        return None
    ix=indices[np.argmin(dist[indices])]
    j=indices[np.argmin(rot[indices])]
    return dict(n=len(indices),min_distance_m=float(dist[ix]),k_at_min_distance=int(k[ix]),
                orientation_at_min_distance_rad=float(rot[ix]),min_orientation_rad=float(rot[j]),
                k_at_min_orientation=int(k[j]))


def region(k,mask,dist,rot,ramp,components):
    d_ok=dist<=.003
    r_ok=rot<=.02
    m=filled_min(k,mask,dist,rot)
    if m is None:
        return None
    m['max_consecutive_2ms']={name:longest(mask&x) for name,x in (
        ('position',d_ok),('orientation',r_ok),('position_and_orientation',d_ok&r_ok),
        ('ready',d_ok&r_ok&ramp))}
    m['predicate_counts']={name:int((mask&x).sum()) for name,x in (
        ('ramp',ramp),('position',d_ok),('orientation',r_ok),('position_and_orientation',d_ok&r_ok),
        ('ready',d_ok&r_ok&ramp))}
    m['signed_projection_mean_m']={key:float(v[mask].mean()) for key,v in components.items()}
    return m


def analyze(u,backend,side):
    import mujoco as mj
    from learning.b0.physics import build
    from learning.b0.contact_events import FrozenDoorReference
    case,raw,obs,ref,path=case_at(u,backend,side)
    model=build(case['actual_config'])
    data=mj.MjData(model)
    frozen=FrozenDoorReference.from_episode(ref,model)
    start,end=frozen.phase_bounds['pregrasp']
    ramp_start=start+int(np.ceil(case['actual_config']['phase_ramp_s']['pregrasp']/DT-1e-9))
    dense=np.load(ref/'substeps/qpos.npy',mmap_mode='r')
    qbank=np.load(ref/'qpos.npy',mmap_mode='r')
    recorded_goal=np.load(ref/'substeps/tcp_goal_world_m.npy',mmap_mode='r')
    phases=np.array(case['phases'])
    trace=np.load(raw/'solved_servo_trace.npz')
    k=trace['step']
    np.testing.assert_array_equal(k+1,obs['step'])
    q=trace['q_pre']
    actual,orient,R=fk(model,data,q)
    post,post_rot,_=fk(model,data,trace['q_post'])
    p_ref,_,Rref=fk(model,data,dense[k])
    bank,_,_=fk(model,data,qbank[k//10])
    target,target_R=frozen.endpoint_pose['pregrasp']
    pos_error=norms(actual-target)
    rot_error=np.arccos(np.clip((np.sum(orient*target_R,axis=(1,2))-1)/2,-1.,1.))
    phase=phases[obs['actual_phase'].astype(int)]
    refphase=phases[np.load(ref/'substeps/phase.npy',mmap_mode='r')[k]]
    np.testing.assert_array_equal(refphase,phases[obs['reference_phase'].astype(int)])
    np.testing.assert_array_equal(phase,trace['phase'])
    active=phase=='pregrasp'
    rmask=k>=ramp_start
    np.testing.assert_array_equal(rmask[active],obs['ramp'][active].astype(bool))
    # Original solved geometry is checked against saved values on both candidate state clocks.
    def residual(x,original):
        return float(np.max(np.abs(x[active]-original[active]))) if active.any() else None
    alignment=dict(pre_distance_max_abs_m=residual(pos_error,obs['endpoint_m']),
                   post_distance_max_abs_m=residual(norms(post-target),obs['endpoint_m']),
                   pre_orientation_max_abs_rad=residual(rot_error,obs['endpoint_rad']),
                   post_orientation_max_abs_rad=residual(np.arccos(np.clip((np.sum(post_rot*target_R,axis=(1,2))-1)/2,-1,1)),obs['endpoint_rad']))
    # The judge uses the backend's cached orientation matrix, particularly near arccos(1).
    # Original predicate recomputation below uses original saved solved values.
    saved_d,saved_r=obs['endpoint_m'],obs['endpoint_rad']
    ready=active&rmask&(saved_d<=.003)&(saved_r<=.02)
    np.testing.assert_array_equal(ready[active],obs['ready'][active].astype(bool))
    n=0
    for i in np.flatnonzero(active):
        n=n+1 if ready[i] else 0
        assert n==obs['current'][i] and obs['required'][i]==75
    tracking=actual-p_ref
    progress=p_ref-target
    translation=q[:,:3]-dense[k,:3]
    # Evaluate local TCP FK with the free root at the identity for both joint states.
    # This is independent of both previously obtained world-frame TCPs.
    def local_fk(configurations):
        local=configurations.copy()
        local[:,:7]=[0,0,0,1,0,0,0]
        return fk(model,data,local)[0]
    f_ref=local_fk(dense[k])
    f=local_fk(q)
    rotation=rotate(R-Rref,f_ref)
    arm=rotate(R,f-f_ref)
    parts=dict(total=actual-target,tracking=tracking,reference_progress=progress,
               root_translation=translation,root_rotation=rotation,arm_fk=arm)
    scores={key:np.einsum('ij,ij->i',v,parts['total'])/np.maximum(norms(parts['total']),1e-15)
            for key,v in parts.items()}
    closure=norms(tracking-translation-rotation-arm)
    closure_ep=norms(parts['total']-tracking-progress)
    # Warp qpos are originally float32. Its quaternions may be slightly non-unit.
    recorded_ready_mismatch=int(np.sum(active&(ready!=(rmask&(pos_error<=.003)&(rot_error<=.02)))))
    alignment.update(closure_max_m=float(closure.max()),endpoint_identity_max_m=float(closure_ep.max()),
                     fk_vs_original_ready_predicate_mismatches=recorded_ready_mismatch)
    name=f'u{u:06}_{backend}_{side}'
    xyzcols=dict(actual=actual,reference_dense=p_ref,reference_bank_held=bank,
                 cartesian_goal=recorded_goal[k],endpoint=np.broadcast_to(target,actual.shape),**parts)
    RAW.mkdir(parents=True,exist_ok=True)
    table=RAW/(name+'_endpoint_decomposition.csv.gz')
    with gzip.open(table,'wt',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['k_2ms','time_s','policy_frame','actual_event_phase','reference_phase','original_ramp',
                         'pregrasp_endpoint_m','pregrasp_endpoint_rad','judge_endpoint_m','judge_endpoint_rad',
                         'original_ready','original_continuous_ready']+
            [f'{col}_{axis}_m' for col in xyzcols for axis in 'xyz']+
            [f'{col}_signed_projection_m' for col in parts]+['tracking_closure_m','endpoint_closure_m'])
        for i in range(len(k)):
            writer.writerow([k[i],k[i]*DT,k[i]//10,phase[i],refphase[i],int(obs['ramp'][i]),
                             pos_error[i],rot_error[i],saved_d[i] if active[i] else '',
                             saved_r[i] if active[i] else '',int(obs['ready'][i]),int(obs['current'][i])]+
                            [v[i,j] for v in xyzcols.values() for j in range(3)]+
                            [v[i] for v in scores.values()]+[closure[i],closure_ep[i]])
    first=lambda m:int(k[np.flatnonzero(m)[0]]) if m.any() else None
    windows={
        'actual_pregrasp':active,
        'actual_before_ramp':active&~rmask,
        'actual_after_ramp_including_later_reference':active&rmask,
        'original_pregrasp_plateau':active&rmask&(refphase=='pregrasp'),
    }
    row=dict(update=u,backend=backend,side=side,source=str(path),arrays=str(raw),reference=str(ref),
             step_count=len(k),actual_pregrasp_start_k=first(active),first_ramp_k=first(active&rmask),
             reference_pregrasp_start_k=int(start),reference_ramp_complete_k=ramp_start,
             reference_pregrasp_stop_k_exclusive=int(end),vector_table=str(table),archive_failure=case['first_failure']['reason'],
             regions={key:region(k,m,saved_d,saved_r,rmask,scores) for key,m in windows.items()},
             alignment=alignment)
    return row,obs,case,raw


def run():
    register()
    results=[]
    rechecks=[]
    tracking=read(OLD/'tracking_windows.json')['windows']
    readiness=read(OLD/'readiness_windows.json')['windows']
    for u in (4991,7500,10000):
        for backend in ('warp','native'):
            for side in ('pull','push'):
                row,obs,case,raw=analyze(u,backend,side)
                results.append(row)
                for w in readiness:
                    if (w['backend'],w['side'])!=(backend,side): continue
                    ok=(obs['step']>=w['start'])&(obs['step']<=w['end'])
                    match=ok & (obs['actual_phase']==case['phases'].index(w['actual_phase']))
                    rechecks.append(dict(update=u,backend=backend,side=side,kind='actual_event',phase=w['actual_phase'],
                        start=w['start'],end=w['end'],expected=w['n'],available=int(ok.sum()),matched=int(match.sum()),
                        complete=bool(match.sum()==w['n'])))
                # Use the original full formal trajectory at u4991 for the reference tracking registration.
                p=OLD if u!=4991 else Path('results/b0/standard_official_flow_continuation_20261124')
                old_case=read(p/'physics'/f'u{u:06}_{backend}_full'/side/'full/nominal/result.json')
                raw_formal=Path(old_case['raw_directory'])
                tick=np.load(raw_formal/'physics_step.npy')
                for w in tracking:
                    if (w['backend'],w['side'])!=(backend,side): continue
                    ks=np.arange(w['start'],w['end']+1,10) if w['count'] else []
                    n=int(np.isin(ks,tick).sum())
                    rechecks.append(dict(update=u,backend=backend,side=side,kind='reference_clock',phase=w['phase'],
                        start=w['start'],end=w['end'],expected=w['count'],available=n,complete=bool(n and n==w['count'])))
    write('readiness_predicates.json',results)
    write('registered_windows_recheck.json',rechecks)
    write('clock_alignment.json',dict(k='start interval k; readiness.step=k+1; cached solved site geometry compared with both q_pre and q_post; reference dense q[k], Cartesian goal[k].',
        actor='Absolute 20ms frame k//10 held; bank qpos[k//10]; training goal at frame t and reward successor t+1.',
        projection='Signed on total endpoint-error unit vector. Tracking decomposition includes all three root translation and rotation axes.',
        rows=[{key:r[key] for key in ('update','backend','side','alignment')} for r in results]))
    with (OUT/'endpoint_decomposition.csv').open('w',newline='') as f:
        out=csv.writer(f)
        cols=['update','backend','side','region','ticks','min_distance_m','min_k','longest_ready_ticks',
              'endpoint_mean_m','tracking_mean_projection_m','reference_progress_mean_projection_m',
              'translation_mean_projection_m','rotation_mean_projection_m','arm_mean_projection_m','vector_table']
        out.writerow(cols)
        for r in results:
            for region_name,v in r['regions'].items():
                a=v['signed_projection_mean_m'] if v else {}
                out.writerow([r['update'],r['backend'],r['side'],region_name,v['n'] if v else 0,
                    v['min_distance_m'] if v else None,v['k_at_min_distance'] if v else None,
                    v['max_consecutive_2ms']['ready'] if v else None]+[a.get(j) for j in ('total','tracking','reference_progress','root_translation','root_rotation','arm_fk')]+[r['vector_table']])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--register',action='store_true')
    if p.parse_args().register:
        print(register())
    else:
        run()
