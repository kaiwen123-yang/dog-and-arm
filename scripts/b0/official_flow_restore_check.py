"""Reload the actual optimizer, replay, sampler, RNG and live physical boundary."""
import argparse
import json
import numpy as np
import torch
import yaml
from learning.b0.contact_model import contact_state
from scripts.b0.official_flow import CONFIG, OUT, RAW, build, io, restore, stats


def check(u):
    cfg=yaml.safe_load(CONFIG.read_text())
    run,_=build(cfg)
    row=next(r for r in (json.loads(line) for line in (OUT/'updates.jsonl').read_text().splitlines())
             if r['update']==u)
    directory=RAW/f'resume_{u:06}'
    receipt=dict(checkpoint=str(RAW/f'checkpoint_{u:06}.pt'),state=str(directory),
                 steps=row['steps'],stats=row['statistics'],update=u)
    assert restore(run,receipt)==u
    assert run.total==row['valid'] and run.schedule.state_dict()==row['ratio']
    lanes=torch.arange(run.n,device=run.device)
    last=run.replay.get(lanes,torch.full_like(lanes,run.replay.clock-1),('next_state','action','episode'))
    physical=contact_state(run.plant.data.qpos[:],run.plant.data.qvel[:])
    expected=last['next_state']
    direct=list(range(34))+list(range(37,63))
    torch.testing.assert_close(physical[:,direct],expected[:,direct],rtol=0,atol=0)
    # Three angular velocities are recomputed by a float32 quaternion rotation.
    angular_max=float((physical[:,34:37]-expected[:,34:37]).abs().max())
    scale=float(expected[:,34:37].abs().max())
    assert angular_max <= 8 * torch.finfo(physical.dtype).eps * max(1,scale)
    torch.testing.assert_close(run.lanes['previous'],last['action'],rtol=0,atol=0)
    torch.testing.assert_close(run.lanes['episode'],last['episode'],rtol=0,atol=0)
    with np.load(directory/'solver.npz') as z:
        fields=list(io.records(run.plant.sim.wp_data))
        for name,buf in fields:
            np.testing.assert_array_equal(z[name],buf.numpy())
    io.write(OUT/f'restored_u{u:06}.json',dict(update=u,steps=io.optimizer_steps(run),
        valid=run.total,stats=stats(run),ratio=run.schedule.state_dict(),solver_arrays_exact=len(fields),
        all_lanes=run.n,direct_state_and_action_exact=True,world_angular_recompute_max_rad_s=angular_max,additional_optimizer_steps=0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('update',type=int)
    check(p.parse_args().update)
