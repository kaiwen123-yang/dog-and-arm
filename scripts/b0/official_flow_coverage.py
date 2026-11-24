"""Count real, eligible policy rows and reference support from the saved online ring."""
import argparse
from collections import Counter
from pathlib import Path
import numpy as np
import torch
from scripts.b0.official_flow import OUT, RAW, CONTINUATION, io


def save_counting_fields(run,u):
    # Retain just the fields required to count visits and measure arm/jaw support
    # in the part of a long continuation that will roll out of the final ring.
    ring=run.replay
    dest = RAW/(f'countclock_{ring.clock:08}.pt' if CONTINUATION else f'counting_{u:06}.pt')
    if dest.exists() and CONTINUATION:
        return
    pages={}
    for page,arrays in ring.pages.items():
        part={k:arrays[k].cpu() for k in ('valid','terminated','truncated','episode','motion_time')}
        part['state']=arrays['state'][...,23:31].contiguous().cpu()
        part['action']=arrays['action'][...,16:].contiguous().cpu()
        pages[page]=part
    small=dict(clock=ring.clock,capacity=ring.capacity,page_size=ring.page_size,lanes=ring.lanes,
               arm_only=True,pages=pages)
    io.atomic_torch(dict(replay=small),dest)


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
    files={int(p.name.split('_')[1]):p/'state.pt' for p in RAW.glob('resume_*')}
    files.update({int(p.stem.split('_')[1]):p for p in RAW.glob('counting_*.pt')})
    parent=io.read(OUT/'parent.json') if CONTINUATION else None
    first_tick=parent['clock'] if parent else 0
    if parent:
        files={int(p.stem.split('_')[1]):p for p in RAW.glob('countclock_*.pt')}
        files={k:p for k,p in files.items() if first_tick<=k<=clock}
    for node,state_file in sorted(files.items(),reverse=True):
        if (not parent and node>u) or right==first_tick:
            continue
        if not state_file.is_file():
            continue
        candidate=torch.load(state_file,map_location='cpu',weights_only=False,mmap=True)['replay']
        begin=max(first_tick,candidate['clock']-candidate['capacity'])
        if begin<right<=candidate['clock']:
            ranges.append((begin,right,state_file))
            right=begin
    left=right
    ranges.reverse()
    counts=Counter()
    starts=Counter()
    if parent:
        assert left==first_tick, ('missing counting ticks',left,first_tick)
        inherited=torch.load(RAW/f'countclock_{first_tick:08}.pt',map_location='cpu',weights_only=False,mmap=True)['replay']
        page,off=divmod((first_tick-1)%inherited['capacity'],inherited['page_size'])
        previous=inherited['pages'][page]['episode'][off].numpy()
        # Recover exact capped episode age from the inherited suffix.
        age=np.zeros(previous.shape,dtype=np.int32)
        for lag in range(1,11):
            p,j=divmod((first_tick-1-lag)%inherited['capacity'],inherited['page_size'])
            age+=(previous==inherited['pages'][p]['episode'][j].numpy())
    else:
        previous=None
    amin=np.full(7,np.inf)
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
        pos=states if ring.get('arm_only') else states[:,23:31]
        armjaw=np.column_stack((pos[:,:6],pos[:,6]-pos[:,7]))
        qmin=np.minimum(qmin,armjaw.min(0))
        qmax=np.maximum(qmax,armjaw.max(0))
        amin=np.minimum(amin,row['action'][ix,-7:].min(0))
        amax=np.maximum(amax,row['action'][ix,-7:].max(0))
        for m in np.unique(motion[ix]):
            name=cfg['reference_paths'][m].split('/')[-1]
            ph,ns=np.unique(labels[frames[ix & (motion==m)]],return_counts=True)
            counts.update({name+'/'+p:int(n) for p,n in zip(ph,ns)})
    if parent:
        assert valid==dump['total']-parent['valid']
        assert (clock-left)*replay['lanes']==dump['simulated']-parent['simulated']
    if left==0:
        assert valid==dump['total'] and clock*replay['lanes']==dump['simulated']
    sc=np.array([x['scale'] for x in info['actions']])
    offset=np.array([x['offset'] for x in info['actions']])
    lo,hi=offset[-7:]+sc[-7:]*amin,offset[-7:]+sc[-7:]*amax
    ref_lo=np.min([r['physical_min'] for r in info['references']],axis=0)
    ref_hi=np.max([r['physical_max'] for r in info['references']],axis=0)
    bounds=[]
    for i in range(7):
        span=float(ref_hi[i]-ref_lo[i])
        low=max(lo[i]-ref_lo[i],0)
        high=max(ref_hi[i]-hi[i],0)
        bounds.append(dict(channel=16+i,unit='m_full_opening' if i==6 else 'rad',
            reference_min=float(ref_lo[i]),reference_max=float(ref_hi[i]),
            online_min=float(lo[i]),online_max=float(hi[i]),state_min=float(qmin[i]),state_max=float(qmax[i]),
            lower_gap=float(low),upper_gap=float(high),reference_span=span,
            lower_gap_over_span=float(low/span) if span else None,upper_gap_over_span=float(high/span) if span else None))
    io.write(OUT/f'coverage_u{u:06}.json',dict(first_tick_zero_based=left,clock=clock,
        recovery_ranges=[(a,b,str(p)) for a,b,p in ranges],full_chain=left==0,valid=valid,complete_terminal_rows=term,complete_clip_end_rows=trunc,
        parent_tick=first_tick,segment_covered=left==first_tick,prefix_lane_intervals=prefix if left==first_tick else None,simulated_intervals=(clock-left)*replay['lanes'],
        training_by_reference_phase=counts,starts_by_reference=starts,measured_command_support=bounds))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('update',type=int)
    coverage(p.parse_args().update)
