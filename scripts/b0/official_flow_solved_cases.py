"""Summarize final solved physical intervals using the original model, clock and force units."""
from pathlib import Path
import numpy as np
from learning.b0.physics import ActionMap, make_model
from scripts.b0.official_flow import OUT, io


def summaries(rows):
    cases,joints=[],[]
    for row in rows:
        path=OUT/row['record']
        case=io.read(path)
        raw=Path(case['raw_directory'])
        trace=raw/'solved_servo_trace.npz'
        if not trace.exists():
            if case['physics_steps']!=0:
                raise FileNotFoundError(trace)
            cases.append(dict(update=row['update'],backend=row['backend'],side=row['side'],
                protocol=row['protocol'],task=row['task'],record=row['record'],intervals=0))
            continue
        directory=path.parents[3]
        spec=io.read(directory/'evaluation.json')
        ref=Path(spec['source'])/case['episode']
        names=io.read(ref/'metadata.json')['phases']
        ref_phases=np.load(ref/'substeps/phase.npy',mmap_mode='r')
        model=make_model('mobile' if row['side']=='pull' else 'push')
        mapping=ActionMap(model)
        limits=model.actuator_forcerange[mapping.actuator_ids,1]
        with np.load(trace) as a:
            steps=a['step']
            np.testing.assert_array_equal(steps,np.arange(case['physics_steps']))
            k=int(steps[-1])
            actual=a['q_pre'][-1]
            vel=a['v_pre'][-1]
            command=a['physical_target'][-1]
            both=(a['finger_n']>.01).all(1)
            spans=np.diff(np.flatnonzero(np.diff(np.r_[False,both,False].astype(int))).reshape(-1,2),axis=1)
            applicable=np.isin(a['phase'],('open','hold'))
            applicable_force=a['resultant_n'][applicable]
            before=a['force_prelimit'][-1]
            force=a['force'][-1]
            clipped=np.clip(a['force_prelimit'],-limits,limits)
            np.testing.assert_allclose(clipped,a['force'],atol=.001,rtol=1e-5)
            common=dict(update=row['update'],backend=row['backend'],side=row['side'],protocol=row['protocol'],
                task=row['task'],record=row['record'],intervals=len(steps))
            cases.append(common|dict(reference_step_2ms=case['start_substep']+k,
                reference_phase=names[int(ref_phases[case['start_substep']+k])],actual_phase=str(a['phase'][-1]),
                xy_m=float(a['xy_m'][-1]),xy_limit_m=.02,xy_over_limit=float(a['xy_m'][-1]/.02),
                heading_deg=float(a['heading_deg'][-1]),heading_limit_deg=2,heading_over_limit=float(a['heading_deg'][-1]/2),
                longest_both_seconds=float(spans.max()*.002) if len(spans) else 0.,
                both_seconds=float(both.sum()*.002),contact_cutoff_each_N=.01,
                left_finger_N=float(a['finger_n'][-1,0]),right_finger_N=float(a['finger_n'][-1,1]),
                resultant_N=float(a['resultant_n'][-1]),applicable_6N_intervals=int(applicable.sum()),
                peak_applicable_N=float(applicable_force.max()) if len(applicable_force) else None,
                peak_applicable_over_6N=float(applicable_force.max()/6) if len(applicable_force) else None,
                applicable_failure_over_6N=row['failure_force_over_6N'],
                first_failure=row['failure'],trace=str(trace)))
            for i in range(12,23):
                wheel=i<16
                jaw=i==22
                unit='rad/s' if wheel else ('m_full_opening' if jaw else 'rad')
                measured=vel[mapping.dof[i]] if wheel else (actual[29]-actual[30] if jaw else actual[mapping.q[i]])
                joints.append(common|dict(channel=i,joint=mapping.names[i],target=command[i],measured=measured,
                    coord_units=unit,force_units='N' if jaw else 'Nm',servo_ctrl=a['ctrl'][-1,i],
                    bias_generalized=a['bias'][-1,i],prelimit_force=before[i],actual_force=force[i],
                    limit=limits[i],abs_force_over_limit=abs(force[i])/limits[i],
                    abs_prelimit_over_limit=abs(before[i])/limits[i]))
    return cases,joints
