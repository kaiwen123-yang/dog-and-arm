"""Index the actual response cases and their same-function finite differences without new simulation."""
import csv
from pathlib import Path

import numpy as np
from learning.b0.physics import make_model
from scripts.b0.pregrasp_response import OUT, RAW, read, write
from scripts.b0.pregrasp_response_objective import HORIZONS, AMPS, INDEX, TERMS, NAMES


def table(path,rows):
    with path.open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(dict.fromkeys(k for r in rows for k in r)))
        writer.writeheader()
        for row in rows:
            writer.writerow({k:('NA' if v is None else v) for k,v in row.items()})


def scalar(v):
    return float(v) if np.isfinite(v) else None


def mean_abs(x):
    return scalar(np.mean(np.abs(x)))


def stack_values(a,name):
    values=np.full((len(HORIZONS), len(NAMES)),np.nan)
    data=a[name]
    values[:len(data)]=data
    values[:2,INDEX['bootstrapped_return']]=np.nan
    values[:2,INDEX['critic_contribution']]=np.nan
    return values


def masks(a,cfg,model):
    force=a['actuator_force']
    ctrl=a['ctrl']
    limits=model.actuator_ctrlrange
    force_lim=model.actuator_forcerange
    return dict(wm_canonical_clamp=np.sign(a['wm_raw'])*(abs(a['wm_raw'])>=1),
                real_canonical_clamp=np.sign(a['real_raw'])*(abs(a['real_raw'])>=1),
                finger_contact=a['finger_load_N']>cfg['contact_threshold_n'],
                wheel_support=a['wheel_load_N']>=cfg['wheel_threshold_n'],
                unexpected_contact=a['unexpected_contact_N']>cfg['contact_threshold_n'],
                robot_door_contact=a['door_force_norm_sum_N']>cfg['contact_threshold_n'],
                slip_threshold=a['wheel_slip_m_s']>cfg['park_slip_limit_m_s'],
                ctrl_limit=((ctrl<limits[:,0]).astype(int)-(ctrl>limits[:,1]).astype(int))*model.actuator_ctrllimited,
                force_limit=(force<=force_lim[:,0]+1e-5).astype(int)-(force>=force_lim[:,1]-1e-5).astype(int),
                monitored_servo_saturation=abs(force)>=cfg['sat_fraction']*force_lim[:,1])


def changes(a,b,h):
    out={}
    for key in a:
        n=min(len(a[key]),len(b[key]),h if 'canonical' in key else 80*h)
        out[key]=bool(np.any(a[key][:n]!=b[key][:n]))
    return out


def compare(scene,case_rows,branch_table,comparisons):
    side,k=scene['side'],scene['frame']
    common=dict(side=side,frame=k)
    group=read(OUT/f'response_cases_{side}_{k}.json')
    cfg=read(scene['source'])['actual_config']
    model=make_model('push' if side=='push' else 'mobile')
    metrics={}
    all_masks={}
    cases={}
    root=Path(group['raw'])
    closure=[]
    for row in group['rows']:
        n,a,sign=row['direction'],row['amplitude'],row['sign']
        key=(n,a,sign)
        cases[key]=row
        with np.load(row['raw']) as raw:
            metrics[key]={name:stack_values(raw,name) for name in ('wm','real')}
            all_masks[key]=masks(raw,cfg,model)
        base={**common,'direction':n,'amplitude_effort':a,'sign':sign,'real_microsteps':row['microsteps'],
              'first_failure':str(row['physical_first_failure']) if row['physical_first_failure'] else None,'trace':row['raw']}
        for name,m in metrics[key].items():
            for i,h in enumerate(HORIZONS):
                closure.append(abs(m[i,INDEX['prefix_return']]-sum(m[i,INDEX['weighted_'+t]] for t in TERMS)))
                for item in ('prefix_return','bootstrapped_return','critic_contribution','survival','last_soft_termination',
                             'endpoint_m','synchronous_m','auxiliary_loss',*['weighted_'+t for t in TERMS]):
                    base[f'{name}_H{h}_{item}']=scalar(m[i,INDEX[item]])
        branch_table.append(base)
        case_rows.append(row)
    base=('baseline',0.,0)
    detail=[]
    with np.load(root/'wm_directional_derivatives.npz') as grads:
        for n in group['directions']:
            for a in AMPS:
                minus,plus=(n,a,-1),(n,a,1)
                delta={}
                for name in ('wm','real'):
                    empty=np.full_like(metrics[base][name],np.nan)
                    m0=metrics[base][name]
                    lo,hi=(metrics[key][name] for key in (minus,plus))
                    # Each one-sided comparison needs its own endpoint and the common baseline.
                    forward=(hi-m0)/a
                    backward=(m0-lo)/a
                    central=np.where(np.isfinite(m0),(hi-lo)/(2*a),empty)
                    delta[name]=(forward,backward,central)
                ad=grads[n].astype(float).copy()
                ad[:2,INDEX['bootstrapped_return']]=np.nan
                ad[:2,INDEX['critic_contribution']]=np.nan
                path=root/f'{n}_{int(a*100):02}_derivatives.npz'
                np.savez_compressed(path,fields=np.array(NAMES),horizons=HORIZONS,wm_ad=ad,
                                    **{f'{name}_{which}':val for name,vals in delta.items()
                                       for which,val in zip(('Dplus','Dminus','central'),vals)})
                for i,h in enumerate(HORIZONS):
                    ix=INDEX['bootstrapped_return' if h==32 else 'prefix_return']
                    sides=[changes(all_masks[base],all_masks[key],h) for key in (minus,plus)]
                    switch={f'{key}_switch':any(m[key] for m in sides) for key in sides[0]}
                    if h==32:
                        for identity in ('wm','real'):
                            flags=[cases[key][f'{identity}_critic_clipped'] for key in (base,minus,plus)]
                            switch[f'{identity}_critic_clip_switch']=None if None in flags else len(set(flags))>1
                    drow=dict(**common,direction=n,amplitude=a,horizon=h,
                              full_3branch_real_horizon=all(h in cases[key]['real_horizons'] for key in (base,plus,minus)),
                              wm_AD_J=scalar(ad[i,ix]),file=str(path))
                    for name,(forward,backward,central) in delta.items():
                        drow.update({f'{name}_Dplus_J':scalar(forward[i,ix]),f'{name}_Dminus_J':scalar(backward[i,ix]),
                                     f'{name}_central_J':scalar(central[i,ix])})
                        for x in ('endpoint_m','synchronous_m'):
                            col=INDEX[x]
                            drow[f'{name}_Dplus_{x}']=scalar(forward[i,col])
                            drow[f'{name}_Dminus_{x}']=scalar(backward[i,col])
                            drow[f'{name}_central_{x}']=scalar(central[i,col])
                            drow[f'wm_AD_{x}']=scalar(ad[i,col])
                    drow.update(switch)
                    detail.append(drow)
    comparisons.extend(detail)
    closure=np.array(closure)
    return dict(**common,objective_gradient_defined='objective' in group['directions'],
                reward_component_closure_max=float(np.nanmax(closure)),rows=len(group['rows']),
                actual_optimizer_steps=0,raw=str(root))


def sign_grade(a,b,magnitude,amp):
    if a is None or b is None:
        return 'missing'
    # Display-only roundoff floor on the central secant: one ulp of the outputs / amplitude.
    floor=np.spacing(np.float32(max(abs(magnitude),np.finfo('f').tiny)))/amp
    if abs(a)<=floor or abs(b)<=floor:
        return 'under_resolution'
    return 'same' if np.sign(a)==np.sign(b) else 'opposite'


def main():
    comp,branches,rows,starts=[],[],[],[]
    all_anchors=read(OUT/'states.json')['states']
    for s in all_anchors:
        recon=read(OUT/f"response_reconstruction_{s['side']}.json")
        if s['frame'] in recon['reached']:
            starts.append(compare(s,rows,branches,comp))
    bases={(r['side'],r['frame']):r for r in branches if r['direction']=='baseline'}
    for r in comp:
        h=r['horizon']
        base=bases[r['side'],r['frame']]
        m='bootstrapped_return' if h==32 else 'prefix_return'
        mag=base[f'wm_H{h}_{m}']
        r['wm_AD_FD_J_sign']=sign_grade(r['wm_AD_J'],r['wm_central_J'],mag,r['amplitude'])
        r['wm_physics_FD_J_sign']=sign_grade(r['wm_central_J'],r['real_central_J'],
                                               max(abs(mag),abs(base[f'real_H{h}_{m}'] or 0.)),r['amplitude'])
    scores=[]
    for h in HORIZONS:
        subset=[r for r in comp if r['horizon']==h]
        summary=dict(horizon=h,registered_triplets=len(subset),complete=sum(r['full_3branch_real_horizon'] for r in subset))
        for label in ('wm_AD_FD_J_sign','wm_physics_FD_J_sign'):
            summary[label]={v:sum(r[label]==v for r in subset) for v in ('same','opposite','under_resolution','missing')}
        eligible=[r for r in subset if r['direction']=='objective' and r['full_3branch_real_horizon']]
        summary.update(objective_direction_instances=len(eligible),
                       original_positive_effort_reduces_real_endpoint=sum(r['real_Dplus_endpoint_m']<0 for r in eligible),
                       original_positive_effort_reduces_real_same_clock=sum(r['real_Dplus_synchronous_m']<0 for r in eligible),
                       original_positive_effort_increases_real_return=sum(r['real_Dplus_J']>0 for r in eligible),
                       both_errors_reduced=sum(r['real_Dplus_endpoint_m']<0 and r['real_Dplus_synchronous_m']<0 for r in eligible))
        scores.append(summary)
    table(OUT/'response_branches.csv',branches)
    table(OUT/'response_differences.csv',comp)
    checks=[read(OUT/f"response_reload_{s['side']}_{s['frame']}.json") for s in all_anchors
            if (OUT/f"response_reload_{s['side']}_{s['frame']}.json").exists()]
    prefix=[read(OUT/f'response_reconstruction_{side}.json') for side in ('pull','push')]
    write(OUT/'gradient_physics_comparison.json',dict(
        definition='Dplus=(plus-baseline)/a; Dminus=(baseline-minus)/a; central=(plus-minus)/(2a). H1/H7 use original survival discounted prefixes. J32 adds the unchanged terminal Critic.',
        source='pregrasp_response_objective.Fold calls pinned WorldModelEnv._compute_term_prob and ActorCriticPolicyLearner._bootstrap, and ContactRepresentation.compute_wm_reward_from_reference with successor reference t+1.',
        original_actor_first_variable='RobotActor.raw independent decoder output z0 times original standard_action plus home_action through canonical clamp; all later policy queries see their own successors and retain full input AD.',
        comparison='AD versus finite difference of the same WM function; measured finite difference includes subsequent actor feedback. Counts are descriptive across registered amplitudes at overlapping starts.',
        reported_sign_resolution='One float32 ulp on baseline return / amplitude for both compared slopes. Raw slopes and one-sided values are preserved. Physical/contact mode switches counted by comparing each sign to the baseline on shared measured microsteps.',
        scope='Fine-step development starts. Neither absorbing full-task scores nor V0. Hyperscale or backend causation is not identified.',
        starts=starts,results_by_horizon=scores,physical_branches=len(rows),physical_microsteps=sum(r['microsteps'] for r in rows),
        actor_calls_in_response_physics=sum(r['policy_queries'] for r in rows),physical_first_failure_count=sum(r['physical_first_failure'] is not None for r in rows),
        prefix_microsteps=sum(r['physics_steps'] for r in prefix),reload_microsteps=sum(r['microsteps'] for r in checks),
        full_solver_reload_checks=len(checks),bitwise_successors=sum(r['exact'] for r in checks),dense_derivatives='Each differences row links all 101 scalar/state outputs, AD, +/- and central derivatives in NPZ.',
        light_branch_table='response_branches.csv',finite_difference_table='response_differences.csv',formal_return=None,
        optimizer_steps=dict(actor=0,wm=0,critic=0)))


if __name__=='__main__':
    main()
