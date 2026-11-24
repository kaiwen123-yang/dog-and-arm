"""Read the parent traces and repeat recorded Actor inputs at the first meaningful divergence."""
import json
from pathlib import Path
import numpy as np
from learning.b0.contact_policy import load_policy
from learning.b0.physics import ActionMap,make_model
from scripts.b0.official_flow import OUT,RAW,PARENT_OUT,PARENT_RAW,io


def report():
    align=io.read(OUT/'backend'/'alignment.json')
    refs=Path('results/raw_large/b0/full_warp_hold_park_r1')
    fn=load_policy(PARENT_RAW/'checkpoint_001000.pt',[refs/r['episode'] for r in align['sides']],io.DEVICE)
    mapping=ActionMap(make_model())
    rows=[]
    for side_row in align['sides']:
        j=side_row['first_reference_frame']
        side=side_row['side']
        pair={}
        for backend in ('warp','native'):
            old=io.read(PARENT_OUT/'physics'/f'u001000_{backend}_full'/side/'full/nominal/result.json')
            oldraw=Path(old['raw_directory'])
            q,v,a,prev=(np.load(oldraw/(k+'.npy')) for k in ('qpos','qvel','raw_action','clipped_action'))
            path=refs/old['episode']
            test=fn(path,j,q[j-9:j+1],v[j-9:j+1],prev[j-10:j])
            test2=fn(path,j,q[j-9:j+1],v[j-9:j+1],prev[j-10:j])
            repeat_error=float(np.max(abs(test-test2)))
            full=io.read(OUT/'backend'/f'u1000_{backend}'/side/'full/nominal/result.json')
            with np.load(Path(full['raw_directory'])/'solved_servo_trace.npz') as tr:
                step=10*j
                idx=np.flatnonzero(tr['step']==step).item()
                prev_idx=np.flatnonzero(tr['step']==step-1).item()
                snap={k:tr[k][idx].tolist() for k in ('q_pre','v_pre','ctrl','bias','force','force_prelimit','physical_target','heading_deg','xy_m')}
                wheel=slice(12,16)
                snap.update(wheel_target_rad_s=tr['physical_target'][idx,wheel].tolist(),
                            wheel_speed_rad_s=tr['v_pre'][idx,mapping.dof[wheel]].tolist(),
                            preceding_wheel_speed_rad_s=tr['v_pre'][prev_idx,mapping.dof[wheel]].tolist())
            end=full['last_physical_observation']
            pair[backend]=dict(replayed_action_max_abs_difference=float(np.max(abs(test-a[j]))),
                same_input_repeated_action_exact=bool(np.array_equal(test,test2)),same_input_repeat_max_abs=repeat_error,reference_frame=j,snapshot=snap,
                repeated_phase_events=[v['phase'] for v in full['events']],original_steps=old['physics_steps'],
                repeated_steps=full['physics_steps'],original_failure=old['first_failure'],repeat_failure=full['first_failure'],
                last_xy_m=end['station_error_m'],last_heading_deg=end['heading_error_deg'],
                last_xy_over_20mm=end['station_error_m']/.02,last_heading_over_2deg=end['heading_error_deg']/2,
                capacity=full.get('warp_capacity'))
        fine=io.read(OUT/'backend'/'u1000_fine'/side/'full/nominal/result.json')
        rows.append(dict(side=side,backends=pair,fine=dict(clock=fine['clock'],measured_s=fine['physics_seconds'],
            native_reference_2ms_end=fine['reference_end_2ms'],actual_end_microsteps=fine['physics_steps'],
            reference_end_microsteps=fine['reference_last_substep'],events=fine['events'],failure=fine['first_failure'],
            formal=False)))
    warnings=[]
    for p in sorted((OUT/'backend').glob('warnings_*.jsonl')):
        warnings.extend(json.loads(line) for line in p.read_text().splitlines())
    extra=[io.read(p) for p in (OUT/'backend').glob('warning_*/evaluation.json')]
    fluid={}
    for side in ('mobile','push'):
        m=make_model(side)
        fluid[side]=dict(wind=m.opt.wind.tolist(),density=m.opt.density,viscosity=m.opt.viscosity,
            warp_has_fluid=bool(m.opt.wind.any() or m.opt.density>0 or m.opt.viscosity>0))
    io.write(OUT/'backend'/'comparison.json',dict(sides=rows,original_2ms_repeats=4,fine_cases=2,
        additional_warning_cases=sum(r['evaluated'] for r in extra),fluid_model=fluid,
        warning_occurrences=warnings,old_warning=dict(category='RuntimeWarning',message='overflow encountered in cast',
        file='warp/_src/types.py',line=3728,order='after pull and before push verdict in u1000 Warp full'),
        interpretation=('The instrumented push construction converted efm_fluid during put_data. '
            'Both models have has_fluid=false. In the installed derivative.py the buffer is zeroed before generation (3223), '
            'and fluid qH/multiply kernels are guarded by has_fluid (3379/3478). The historical warning has no field receipt.')))


if __name__=='__main__':
    report()
