"""Count real, eligible policy rows and reference support from the saved online ring."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
import torch
from scripts.b0.official_flow import OUT, RAW, io


def coverage(u):
    info=io.read(OUT/'interface.json')
    cfg=info['config']
    path=RAW/f'resume_{u:06}'/'state.pt'
    dump=torch.load(path,map_location='cpu',weights_only=False,mmap=True)
    replay=dump['replay']
    clock=replay['clock']
    phases=[]
    for src in map(Path,cfg['reference_paths']):
        meta=io.read(src/'metadata.json')
        n=int(np.load(src/'valid_full_interval.npy').sum())
        tags=np.load(src/'substeps/phase.npy',mmap_mode='r')[:10*n:10]
        phase_names=np.array(meta['phases'])[tags]
        phases.append(np.concatenate((phase_names,phase_names[-1:])))
    ends=np.cumsum(list(map(len,phases)))
    labels=np.concatenate(phases)
    # Stitch adjacent, immutable recovery rings only where absolute ticks overlap.
    # When extending beyond a ring's capacity, never count the overlap twice.
    ranges=[]
    right=clock
    for directory in sorted(RAW.glob('resume_*'), reverse=True):
        node=int(directory.name.split('_')[1])
        if node>u or right==0:
            continue
        state_file=directory/'state.pt'
        if not state_file.is_file():
            continue
        candidate=torch.load(state_file,map_location='cpu',weights_only=False,mmap=True)['replay']
        begin=max(0,candidate['clock']-candidate['capacity'])
        if begin<right<=candidate['clock']:
            ranges.append((begin,right,state_file))
            right=begin
    left=right
    ranges.reverse()
    counts=Counter()
    starts=Counter()
    previous=None
    amin=np.full(23,np.inf)
    amax=-amin.copy()
    qmin=np.full(7,np.inf)
    qmax=-qmin.copy()
    prefix=valid=term=trunc=0
    ring=None
    for tick in range(left,clock):
        if ring is None or tick==ring_end:
            _,ring_end,ring_file=next(r for r in ranges if r[0]==tick)
            ring=torch.load(ring_file,map_location='cpu',weights_only=False,mmap=True)['replay']
        page,off=divmod(tick%ring['capacity'],ring['page_size'])
        row={k:v[off].numpy() for k,v in ring['pages'][page].items() if k in (
            'valid','terminated','truncated','motion_time','episode','action','state')}
        ix=row['valid']
        frames=row['motion_time']
        ids=row['episode']
        motion=np.searchsorted(ends,frames,side='right')
        if previous is None:
            age=np.full(len(ids),10 if left else 0)
            reset=np.ones(len(ids),bool) if not left else np.zeros(len(ids),bool)
        else:
            reset=ids!=previous
            age=np.where(reset,0,age+1)
        previous=ids
        for m,n in enumerate(np.bincount(motion[reset],minlength=len(ends))):
            starts[cfg['reference_paths'][m].split('/')[-1]]+=int(n)
        prefix+=int((age<10).sum())
        valid+=int(ix.sum())
        term+=int((row['terminated'] & ix).sum())
        trunc+=int((row['truncated'] & ix).sum())
        if not ix.any():
            continue
        states=row['state'][ix]
        armjaw=np.column_stack((states[:,23:29],states[:,29]-states[:,30]))
        qmin=np.minimum(qmin,armjaw.min(0))
        qmax=np.maximum(qmax,armjaw.max(0))
        amin=np.minimum(amin,row['action'][ix].min(0))
        amax=np.maximum(amax,row['action'][ix].max(0))
        for m in np.unique(motion[ix]):
            name=cfg['reference_paths'][m].split('/')[-1]
            ph,ns=np.unique(labels[frames[ix & (motion==m)]],return_counts=True)
            counts.update({name+'/'+p:int(n) for p,n in zip(ph,ns)})
    if left==0:
        assert valid==dump['total'] and clock*replay['lanes']==dump['simulated']
    sc=np.array([x['scale'] for x in info['actions']])
    offset=np.array([x['offset'] for x in info['actions']])
    lo,hi=offset+sc*amin,offset+sc*amax
    ref_lo=np.min([r['physical_min'] for r in info['references']],axis=0)
    ref_hi=np.max([r['physical_max'] for r in info['references']],axis=0)
    bounds=[]
    for i in range(7):
        span=float(ref_hi[i]-ref_lo[i])
        low=max(lo[16+i]-ref_lo[i],0)
        high=max(ref_hi[i]-hi[16+i],0)
        bounds.append(dict(channel=16+i,unit='m_full_opening' if i==6 else 'rad',
            reference_min=float(ref_lo[i]),reference_max=float(ref_hi[i]),
            online_min=float(lo[16+i]),online_max=float(hi[16+i]),state_min=float(qmin[i]),state_max=float(qmax[i]),
            lower_gap=float(low),upper_gap=float(high),reference_span=span,
            lower_gap_over_span=float(low/span) if span else None,upper_gap_over_span=float(high/span) if span else None))
    io.write(OUT/f'coverage_u{u:06}.json',dict(first_tick_zero_based=left,clock=clock,
        recovery_ranges=[(a,b,str(p)) for a,b,p in ranges],full_chain=left==0,valid=valid,complete_terminal_rows=term,complete_clip_end_rows=trunc,
        prefix_lane_intervals=prefix if left==0 else None,simulated_intervals=(clock-left)*replay['lanes'],
        training_by_reference_phase=counts,starts_by_reference=starts,measured_command_support=bounds))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('update',type=int)
    coverage(p.parse_args().update)
