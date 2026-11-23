"""Index engine pairs on common physical ticks and their compiled scene differences."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

PAIRS = (
    ('native33_default','cpu316_default'), ('cpu316_default','warp316_default'),
    ('native33_default','native33_ccd_iterations_35'), ('native33_default','native33_multiccd_on'),
    ('cpu316_default','cpu316_multiccd_off'), ('native33_default','cpu316_wheel_deepest_only'),
    ('native33_default','cpu316_wheel_deepest_and_multiccd_off'),
    ('warp316_default','cpu316_multiccd_off'), ('native33_default','warp316_wheel_deepest_only'),
)


def first_tick(ticks, mask):
    indices = np.flatnonzero(mask)
    return int(ticks[indices[0]]) if len(indices) else None


def columns(rows, names):
    return np.column_stack([rows[name] for name in names])


def trace_comparison(root, pair, side, phase):
    a, b = [np.genfromtxt(root/run/side/(phase+'.csv'), names=True, delimiter=',') for run in pair]
    source = [json.loads((root/run/side/'model_and_windows.json').read_text()) for run in pair]
    left, right = [s['windows'][phase] for s in source]
    if (not np.array_equal(a['source_tick'], b['source_tick']) or source[0]['source'] != source[1]['source']
            or any(left[k] != right[k] for k in ('initial_q','initial_v','prefix_intervals','scored_source_interval'))):
        raise ValueError('Input alignment mismatch')
    ticks = a['source_tick']
    root_pos = ['root_post_'+axis+'_m' for axis in 'xyz']
    tcp = ['tcp_start_'+axis+'_m' for axis in 'xyz']
    wheels = ['wheel_'+label+'_N' for label in ('FAR','FBL','RAR','RBL')]
    def diff(names):
        return columns(a,names)-columns(b,names)
    tcp_mm = np.linalg.norm(diff(tcp),axis=1)*1000
    root_mm = np.linalg.norm(diff(root_pos),axis=1)*1000
    wheel_n = np.max(abs(diff(wheels)),axis=1)
    return dict(engine_a=pair[0], engine_b=pair[1], side=side, window=phase,
                first_source_tick=int(ticks[0]), prefix_intervals=left['prefix_intervals'],
                compared_intervals=len(ticks), scored_intervals=int((ticks>=left['scored_source_interval']).sum()),
                first_count_difference=first_tick(ticks,a['ncon'] != b['ncon']),
                first_wheel_difference_over_0p1_N=first_tick(ticks,wheel_n>.1),
                first_root_difference_over_0p1_mm=first_tick(ticks,root_mm>.1),
                first_tcp_difference_over_0p1_mm=first_tick(ticks,tcp_mm>.1),
                count_mismatch_intervals=int((a['ncon'] != b['ncon']).sum()),
                max_wheel_diff_N=float(wheel_n.max()),
                max_finger_diff_N=float(abs(diff(['finger1_N','finger2_N'])).max()),
                max_net_diff_N=float(abs(a['net_N']-b['net_N']).max()), max_tcp_diff_mm=float(tcp_mm.max()),
                max_root_diff_mm=float(root_mm.max()), max_hinge_diff_deg=float(abs(a['door_post_deg']-b['door_post_deg']).max()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    args = p.parse_args()
    rows = [trace_comparison(args.root, pair, side, phase) for pair in PAIRS for side in ('pull','push')
            for phase in ('start','pregrasp','stable_open')]
    with (args.root/'pair_windows.csv').open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    output = {}
    for side in ('pull','push'):
        source = [json.loads((args.root/engine/side/'model_and_windows.json').read_text())
                  for engine in ('native33_default','cpu316_default','warp316_default')]
        for a, b in zip(source[:-1],source[1:]):
            pair = a['engine']+'_'+b['engine']+'/'+side
            diff = {key:float(np.max(abs(np.asarray(x,dtype=float)-np.asarray(b['fields'][key],dtype=float)),initial=0))
                    for key,x in a['fields'].items()}
            output[pair] = dict(max_absolute_field_difference=diff,
                                changed_options={k:[x,b['options'][k]] for k,x in a['options'].items()
                                                 if x!=b['options'][k]})
    with (args.root/'compiled_fields.json').open('x') as stream:
        json.dump(output,stream,indent=2,allow_nan=False)
        stream.write('\n')


if __name__ == '__main__':
    main()
