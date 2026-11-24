"""Inspect the actual first solved servo response at the six frozen contact entries."""
import argparse
from types import SimpleNamespace
import numpy as np
from learning.b0.physics import ActionMap, make_model
from scripts.b0 import joint_physics_closedloop as entries
from scripts.b0.official_flow import OUT, RAW
from scripts.b0.dynamics_h32_pilot import read
from scripts.b0.score_temporal_wm import csv_file


def evaluate(u):
    tag=f'u{u:06}'
    out,raw=OUT/'servo',RAW/'servo'
    out.mkdir(exist_ok=True,parents=True)
    args=SimpleNamespace(identity='formal_2ms', repeat=0,node=tag,checkpoint=RAW/f'checkpoint_{u:06}.pt')
    entries.run(args,out,raw)
    model=make_model()
    mapping=ActionMap(model)
    interface=read(OUT/'interface.json')
    unit=np.array(interface['physical_per_effort'])
    rows=[]
    for summary in read(out/f'closedloop_{tag}_formal_2ms_r0.json')['rows']:
        with np.load(summary['raw']) as a:
            command=a['query_clipped'][0]
            target=mapping.offset+mapping.scale*command
            ids=mapping.actuator_ids[16:]
            q=a['query_q0'][0].reshape(-1)[mapping.q[16:]]
            v=a['query_v0'][0].reshape(-1)[mapping.dof[16:]]
            kp=model.actuator_gainprm[ids,0]
            kv=-model.actuator_biasprm[ids,2]
            limit=model.actuator_forcerange[ids,1]
            actual=a['actuator_force'][0].reshape(-1)[ids]
            ctrl=a['ctrl'][0].reshape(-1)[ids]
            fac=mapping.finger_factor[16:]
            cache=(ctrl-target[16:]*fac)*kp
            unclipped=kp*(np.where(model.actuator_ctrllimited[ids],np.clip(ctrl,*model.actuator_ctrlrange[ids].T),ctrl)-q)-kv*v
            np.testing.assert_allclose(unclipped.clip(-limit,limit),actual,atol=0.0002)
            dist=np.maximum(abs(unclipped)-limit,0)/kp/fac
            for j,k in enumerate(range(16,23)):
                rows.append(dict(node=tag,entry=summary['start'],phase=summary['phase'],channel=k,
                    joint=mapping.names[k],target=float(target[k]),position=float(q[j]),
                    joint_unit='m_active_finger' if k==22 else 'rad',target_unit='m_full_opening' if k==22 else 'rad',
                    effort_unit='N' if k==22 else 'Nm',limit=float(limit[j]),actual=float(actual[j]),
                    raw=float(unclipped[j]),abs_actual_over_limit=float(abs(actual[j])/limit[j]),
                    abs_raw_over_limit=float(abs(unclipped[j])/limit[j]),
                    kp_error_over_limit=float(abs(kp[j]*(target[k]*fac[j]-q[j]))/limit[j]),
                    kv_speed_over_limit=float(abs(kv[j]*v[j])/limit[j]),bias_over_limit=float(abs(cache[j])/limit[j]),
                    desaturation_distance=float(dist[j]),distance_over_effort_unit=float(dist[j]/unit[k]),
                    distance_over_collection_sigma=float(dist[j]/(.1*unit[k]))))
    csv_file(out/f'{tag}_first_solve.csv',rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('update',type=int)
    evaluate(parser.parse_args().update)
