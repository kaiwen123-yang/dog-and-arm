"""Matched frozen-Actor check at equal total Warp physics ticks, without optimizer updates."""
import json
from pathlib import Path

import numpy as np
import torch
from learning.b0.contact_training import ContactRun
from learning.b0.contact_warp import PHASES


def compare(source, out):
    weight = torch.load(source,map_location='cpu',weights_only=False)
    reports = {}
    for mode in ('cohort','lane_reset'):
        torch.manual_seed(85200)
        np.random.seed(85200)
        cfg = dict(weight['cfg'],collector=mode,freeze_actor_statistics=True)
        refs = [Path(cfg['reference_directory'])/p for p in cfg['references']]
        run = ContactRun(cfg,refs,refs,weight,weight,'cuda:0')
        torch.manual_seed(85201)
        np.random.seed(85201)
        raw = Path('results/raw_large/b0')/out.name/mode
        raw.mkdir(parents=True,exist_ok=False)
        run.compact_directory = raw
        counts = []
        dual = {}
        for i, steps in enumerate([40,40] if mode=='cohort' else [40,40,20]):
            run.steps = steps
            folder = raw/str(i)
            counts.append(run.collect(folder))
            arr = lambda k: np.load(folder/(k+'.npy'),mmap_mode='r')
            valid, frame = arr('valid'), arr('frame')
            side = run.sides[torch.as_tensor(frame.copy(),device=run.device)].cpu().numpy()
            both = (arr('sub_finger_load_N')>run.plant.cfg['contact_threshold_n']).all(axis=(-1,-2))
            for s, label in enumerate(['pull','push']):
                dual[label] = dual.get(label,0) + int((valid & both & (side==s)).sum())
            if mode=='lane_reset':
                ep=arr('episode')
                same=ep[:-1]==ep[1:]
                assert np.array_equal(arr('next_qpos')[:-1][same],arr('qpos')[1:][same])
                assert np.array_equal(arr('clipped')[:-1][same],arr('prev_action')[1:][same])
                assert (np.diff(frame,axis=0)[same]==1).all()
        bins = {}
        for h in (1,7):
            hist = torch.zeros((2,len(PHASES)),device=run.device,dtype=torch.long)
            for data, indices in run.replay.chunks:
                i,t = indices[h].T
                f = data['motion_time'][i,t]
                hist += torch.bincount(run.sides[f]*len(PHASES)+run.phases[f,0],minlength=hist.numel()).reshape_as(hist)
                if h==7 and mode=='lane_reset':
                    for j in range(1,h):
                        assert (data['episode'][i,t]==data['episode'][i,t+j]).all()
                        assert (data['motion_time'][i,t+j]==f+j).all()
                        assert torch.equal(data['next_state'][i,t+j-1],data['state'][i,t+j])
            bins[h] = {s:dict(zip(PHASES,row)) for s,row in zip(('pull','push'),hist.tolist())}
        prefixes=sum(r.get('prefix_intervals',10*run.n) for r in counts)
        physics=run.simulated + (prefixes if mode=='cohort' else 0)
        reports[mode]=dict(physics_substeps=10*physics,prefix_intervals=prefixes,valid=run.total,
                valid_per_physical_interval=run.total/physics,
                waiting_or_invalid=physics-prefixes-run.total,
                episodes=sum(sum(r['starts_per_motion']) for r in counts),continuous_dual_intervals=dual,
                starts_by_side_and_phase=bins,blocks=counts)
        del run
    assert reports['cohort']['physics_substeps']==reports['lane_reset']['physics_substeps']
    return reports


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    measured=compare(a.checkpoint,a.out)
    (a.out/'comparison.json').write_text(json.dumps(dict(source=str(a.checkpoint),
        seeds=[85200,85201],actor_updates=0,results=measured),indent=2)+'\n')
