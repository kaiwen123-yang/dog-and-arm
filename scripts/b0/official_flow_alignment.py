"""Align existing same-checkpoint native/Warp episodes at their exact 20 ms Actor clock."""
from pathlib import Path
import numpy as np
from scripts.b0.official_flow import OUT, PARENT_OUT, PARENT_RAW, io


def compare():
    target = OUT/'backend'
    info = io.read(PARENT_OUT/'interface.json')
    effort = np.array(info['canonical_per_effort'])
    rows = []
    for side in ('pull','push'):
        pairs = []
        for backend in ('warp','native'):
            case = io.read(PARENT_OUT/'physics'/f'u001000_{backend}_full'/side/'full/nominal/result.json')
            directory = Path(case['raw_directory'])
            arrays = {k:np.load(directory/(k+'.npy'),mmap_mode='r')
                      for k in ('physics_step','qpos','qvel','raw_action','clipped_action')}
            pairs.append((case, arrays))
        (a,x),(b,y) = pairs
        assert a['episode']==b['episode'] and a['actual_config']==b['actual_config']
        assert a['initial_geometry']==b['initial_geometry']
        n = min(len(x['raw_action']),len(y['raw_action']))
        np.testing.assert_array_equal(x['physics_step'][:n],y['physics_step'][:n])
        delta = abs(x['raw_action'][:n]-y['raw_action'][:n])/effort
        ix = np.flatnonzero(delta.max(1) >= .1)
        first = int(ix[0]) if len(ix) else None
        index = int(delta[first].argmax()) if first is not None else None
        def describe(j):
            data = {}
            for (case,v),backend in zip(pairs,('warp','native')):
                prev = np.zeros(23) if not j else v['clipped_action'][j-1]
                data[backend] = dict(q=v['qpos'][j].tolist(),v=v['qvel'][j].tolist(),
                                      previous=prev.tolist(),raw_action=v['raw_action'][j].tolist())
            return data
        row = dict(side=side,episode=a['episode'],aligned_calls=n,frame0_input_and_zero_previous_exact=True,
                   frame0_max_action_difference=float(delta[0].max()),same_initial_history=bool(a['initial_geometry']==b['initial_geometry']),
                   first_difference_definition='raw action difference of at least one collection-noise sigma (0.1 effort) on any channel',
                   first_reference_frame=first,first_step=(10*first if first is not None else None),channel=index,
                   first_sigma_units=(float(delta[first,index]/.1) if index is not None else None),
                   first_call=(describe(first) if first is not None else None))
        windows = [[0,10]]
        if first is not None:
            windows.append([max(0,10*first-10),10*first+10])
        for case,_ in pairs:
            for tick in [e['end_step'] for e in case['events']]+[case['physics_steps']]:
                windows.append([max(0,tick-20),tick+2])
        row['targeted_2ms_windows']=windows
        rows.append(row)
    io.write(target/'alignment.json',dict(checkpoint=str(PARENT_RAW/'checkpoint_001000.pt'),sides=rows))


if __name__=='__main__':
    compare()
