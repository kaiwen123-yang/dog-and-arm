"""Warm the inherited door WM with registered train-only physical successors."""
import argparse
import json
import os
from pathlib import Path
import time

os.environ.setdefault("TORCH_COMPILE_DISABLE","1")
import torch
import yaml
from supermimic.models import Dynamics
from supermimic.learners.wm_learner import WorldModelLearner
from learning.b0.contact_sources import RegisteredWM, native_episodes
from learning.b0.contact_model import SCHEMA, ContactRepresentation, ContactWorldModelCfg
from learning.b0.physics import ActionMap, make_model
from learning.b0.model import tensor


def main(args):
    start=time.monotonic()
    cfg=yaml.safe_load(args.recipe.read_text())
    seed=0
    device="cuda:0"
    torch.manual_seed(seed)
    torch.set_float32_matmul_precision("high")
    prior=json.loads(Path("results/b0/lanes_wm_v1/config.json").read_text())
    source=Path("results/b0/lanes_wm_v1/wm_001000.pt")
    init=torch.load(source,weights_only=False,map_location="cpu")
    model=make_model()
    mapping=ActionMap(model)
    rep=ContactRepresentation(model,device)
    dyn=Dynamics(rep,23,5,tensor(mapping.scale,device),tensor(mapping.offset,device),tuple(init["hidden"])).to(device)
    dyn.load_state_dict(init["dyn"])
    teachers=native_episodes([Path(ep["path"]) for ep in prior["sources"] if ep["split"]=="train"],device)
    pool=RegisteredWM(cfg,model,rep,teachers,device)
    learners={h:WorldModelLearner(dyn,rep,ContactWorldModelCfg(batch_size=256,horizon=h+1,num_batches=1),device) for h in (1,7)}
    learners[1].optimizers=learners[7].optimizers
    out=Path("results/b0")/args.run
    out.mkdir(exist_ok=False)
    (out/"config.json").write_text(json.dumps(dict(initializer=str(source),fixed_statistics=True,optimizers="fresh Muon/Adam",
        native=[e.group for e in teachers],inventory=pool.inventory,recipe=cfg["wm_data_recipe"],seed=seed),indent=2))
    def save(k):
        torch.save(dict(seed=seed,schema=SCHEMA,dyn=dyn.state_dict(),hidden=init["hidden"],minibatches=k,
            optimizers=[o.state_dict() for o in learners[7].optimizers],cpu_rng=torch.get_rng_state(),
            cuda_rng=torch.cuda.get_rng_state(),initializer=str(source)),out/f"wm_{k:06d}.pt")
    save(0)
    with (out/"samples.jsonl").open("x",buffering=1) as log:
        for k in range(1000):
            h=1 if k%10<2 else 7
            batch,_=pool.draw(h,k,256)
            stats=learners[h].update([batch])
            log.write(json.dumps(dict(**pool.rows.pop(),loss={key:float(v) for key,v in stats.items()}),allow_nan=False)+"\n")
            if k+1 in (200,1000):
                save(k+1)
                print(k+1,flush=True)
    (out/"outcome.json").write_text(json.dumps(dict(wall_s=time.monotonic()-start,h1=200,h7=800,actor=0,critic=0,
        samples=256000,successor_targets=256*(200+7*800),stored_positions=256*(200*2+800*8))))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",default="response_wm_v1")
    p.add_argument("--recipe",type=Path,default=Path("config/b0/standard_response_v1.yaml"))
    main(p.parse_args())
