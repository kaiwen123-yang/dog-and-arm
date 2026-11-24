"""Check continuity of lightweight coverage records and list immutable recovery assets."""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import torch
from scripts.b0.official_flow import OUT,RAW,io


def check(stop):
    parent=io.read(OUT/'parent.json')
    end=io.read(OUT/f'node_{stop:06}.json')
    paths=sorted(p for p in RAW.glob('countclock_*.pt') if parent['clock']<=int(p.stem.split('_')[1])<=end['clock'])
    previous=None
    clocks=[]
    matched=0
    for p in paths:
        ring=torch.load(p,map_location='cpu',weights_only=False,mmap=True)['replay']
        clock=ring['clock']
        clocks.append(clock)
        if previous is not None:
            assert 0<clock-previous['clock']<=500
            assert previous['page_size']==ring['page_size'] and previous['capacity']==ring['capacity']==1000
            left=max(0,clock-ring['capacity'])
            right=previous['clock']
            while left<right:
                pg,off=divmod(left%ring['capacity'],ring['page_size'])
                size=min(right-left,ring['page_size']-off)
                for k in ('episode','valid','terminated','truncated','motion_time'):
                    a=previous['pages'][pg][k][off:off+size]
                    b=ring['pages'][pg][k][off:off+size]
                    if not torch.equal(a,b):
                        raise ValueError(f'Overlapping {k} differs at absolute ticks {left}:{left+size}')
                matched+=size*ring['lanes']
                left+=size
        previous=ring
    assert clocks[0]==parent['clock'] and clocks[-1]==end['clock']
    meta=io.read(OUT/f'coverage_u{stop:06}.json')
    assert meta['segment_covered'] and meta['valid']==end['valid']-parent['valid']
    tz=timezone(timedelta(hours=8))
    milestones=[]
    for receipt in sorted(OUT.glob('node_*.json')):
        r=io.read(receipt)
        if r['update']>stop: continue
        pack=Path(r['checkpoint'])
        parts=[pack,Path(r['state'])/'state.pt',Path(r['state'])/'solver.npz']
        milestones.append(dict(node=r['update'],clock=r['clock'],valid=r['valid'],
            committed_beijing=datetime.fromtimestamp(receipt.stat().st_mtime,tz).isoformat(),
            files=[dict(path=str(f),bytes=f.stat().st_size) for f in parts]))
    io.write(OUT/'coverage_archive.json',dict(parent_tick=clocks[0],end_tick=clocks[-1],clocks=clocks,
        max_tick_gap=max(b-a for a,b in zip(clocks,clocks[1:])),ring_capacity_ticks=1000,
        overlap_lane_rows_checked=matched,overlap_fields=['episode','valid','terminated','truncated','motion_time'],
        segment_valid=meta['valid'],segment_lane_intervals=meta['simulated_intervals'],
        counting='one row for each absolute tick and lane, with episode membership checked across retained overlapping rings'))
    io.write(OUT/'milestones.json',dict(recovery_host='autodl-d57',nodes=milestones))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('stop',type=int)
    check(p.parse_args().stop)
