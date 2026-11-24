"""Frozen u0/u1 weights and online statistics, using the original held-out evaluator."""
from types import SimpleNamespace
import numpy as np
import torch
from scripts.b0.official_flow_eval import (
    ActionMap, ContactRepresentation, ContactWorldModelCfg, Validation, WorldModelLearner,
    io, make_dynamics, make_model)
from scripts.b0.official_flow import OUT, PARENT_OUT, PARENT_RAW


def first_batch():
    state = torch.load(PARENT_RAW/'resume_000001/state.pt', weights_only=False,
                       map_location='cpu', mmap=True)['replay']
    assert state['clock'] == 19
    with np.load(PARENT_OUT/'first_draws.npz') as source:
        lane, tick = source['h7_1'].T
    assert len(lane) == 2048
    frames = tick[:, None] + np.arange(7)
    assert frames.max() < state['page_size']
    page = state['pages'][0]
    def read(key):
        return page[key][frames, lane[:, None]].to(io.DEVICE)
    return read('state'), read('action'), read('sim_ctx'), read('next_state')


def quantiles(t):
    return np.quantile(t.detach().flatten(0,-2).cpu().numpy(), [.01,.5,.95,.99], axis=0)


@torch.no_grad()
def run():
    target = OUT/'wm_factorial'
    target.mkdir(exist_ok=True, parents=True)
    packages = [torch.load(PARENT_RAW/f'checkpoint_{i:06}.pt', weights_only=False,
                           map_location='cpu') for i in (0,1)]
    cfg = packages[0]['cfg']
    assert packages[1]['cfg'] == cfg
    model = make_model()
    model.opt.timestep = cfg['physics_dt']
    rep = ContactRepresentation(model,io.DEVICE)
    dyn = make_dynamics(model,rep,ActionMap(model),cfg['wm_hidden'],'C20',io.DEVICE)
    learner = WorldModelLearner(dyn,rep,ContactWorldModelCfg(),io.DEVICE)
    probe = SimpleNamespace(cfg=io.resolved('config/b0/standard_dynamics_v1.yaml'),
                            model=model, rep=rep, dyn=dyn, learners={1:learner,7:learner})
    validation = Validation(probe)
    x, act, ctx, truth = first_batch()
    real = rep.represent(x)
    torch.set_float32_matmul_precision('highest')
    results = []
    for w,s in ((0,0),(1,1),(0,1),(1,0)):
        cell = target/f'weights{w}_stats{s}'
        cell.mkdir(exist_ok=True)
        weights = packages[w]['dyn']
        selected = {k: (packages[s]['dyn'][k] if k.startswith(('state_normalizer.','action_normalizer.')) else v)
                    for k,v in weights.items()}
        dyn.load_state_dict(selected,strict=True)
        for n in dyn.normalizers():
            assert int(n.count) == (50479,73157)[s]
        scores = validation.score(probe,cell)
        if w == s:
            previous = io.read(PARENT_OUT/'validation'/f'u{w:06}'/'scores.json')
            for k,v in previous['values'].items():
                np.testing.assert_allclose(scores[k],v,rtol=1e-4,atol=1e-6)
        dyn.eval()
        za = dyn.action_normalizer(dyn.proc(act))
        zr = dyn.state_normalizer(real)
        linear = next(m for m in dyn.mlp.modules() if isinstance(m,torch.nn.Linear))
        first = linear(torch.cat((zr,za,ctx),dim=-1))
        aux, r = rep.extract_aux_state(x[:,0]), real[:,0]
        auto, response, endpoint = [], [], {}
        for j in range(7):
            z = dyn.state_normalizer(r)
            auto.append(z)
            response.append(linear(torch.cat((z,za[:,j],ctx[:,j]),dim=-1)))
            aux,r = dyn(r,act[:,j],aux,ctx[:,j])
            pred = rep.reconstruct_full_state(aux,r)
            if j in (0,6):
                endpoint[str(j+1)] = float((pred[:,24]-truth[:,j,24]).square().mean().sqrt())
        np.savez_compressed(cell/'first_batch_quantiles.npz',quantiles=[.01,.5,.95,.99],
            real_state_z=quantiles(zr), real_proc_action_z=quantiles(za), real_first_linear=quantiles(first),
            autoregressive_state_z=quantiles(torch.stack(auto,1)), autoregressive_first_linear=quantiles(torch.stack(response,1)))
        norm = dyn.state_normalizer
        results.append(dict(weights=w,stats=s,count=int(norm.count),eps=getattr(norm,'eps',getattr(norm,'_eps',None)),
            until=getattr(norm,'until',getattr(norm,'_until',None)),state_buffers=list(norm.state_dict()),
            scores=scores,first_H1_H7_j2_rmse_rad=endpoint,first_batch_starts=len(x),
            first_batch_H32_available=0))
        io.write(target/'factorial.json',dict(optimizer_steps=0,matched_first=True,stats1_ticks=19,
            first_draw='h7_1',first_draw_H32='No 32-step window in 19 ticks. Historical validation supplies H32.',
            order='matched originals, then both mixed cells',cells=results))
        print('completed', w,s, scores,flush=True)


if __name__=='__main__':
    run()
