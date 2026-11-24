"""Read a completed recovery, repeat its next WM draw, and leave all updates pending."""
import argparse
import json
from pathlib import Path

import torch
from learning.b0.contact_sources import RegisteredWM,native_episodes
from learning.b0.contact_training import OnlineContactReplay
from learning.b0.contact_model import ContactRepresentation
from learning.b0.physics import make_model
from scripts.b0.training_entry_response import BASE,OUT


def main(run):
    p=BASE/run
    state=torch.load(p/"cohort_state.pt",map_location="cuda:0",weights_only=False)
    cfg=state["cfg"]
    model=make_model()
    rep=ContactRepresentation(model,"cuda:0")
    root=Path(cfg["reference_directory"])
    native=native_episodes([root/n for n in cfg["references"]+cfg["additional_teacher_episodes"]],"cuda:0")
    pool=RegisteredWM(cfg,model,rep,native,"cuda:0")
    replay=OnlineContactReplay(cfg["replay_cohorts"],"cuda:0",cfg["contact_replay_draw"])
    replay.chunks.extend(state["replay"])
    records=[]
    for h,offset in ((7,0),(1,8)):
        def draw():
            torch.cuda.set_rng_state(state["gpu_rng"].cpu())
            result,count=pool.draw(h,state["updates"]*10+offset,256,replay)
            return result,pool.rows.pop(),count
        a,info,count=draw()
        b,again,_=draw()
        equal={k:torch.equal(a[k],b[k]) for k in ("state","action","sim_ctx")}
        assert all(equal.values()) and info==again and count==192
        records.append(dict(h=h,index=info["index"],equal=equal,provenance=info["sources"],shape=list(a.batch_size)))
    empty=OnlineContactReplay(cfg["replay_cohorts"],"cuda:0",cfg["contact_replay_draw"])
    fallback=[]
    for h in (1,7):
        _,count=pool.draw(h,state["updates"]*10,256,empty)
        item=pool.rows.pop()
        counts={k:v["samples"] for k,v in item["sources"].items()}
        assert count==0 and counts["native"]==(192 if h==1 else 128)
        fallback.append(dict(h=h,counts=counts))
    (OUT/"resume_draw_check.json").write_text(json.dumps(dict(run=run,from_update=state["updates"],
        pending=state["ratio_state"],kind="read-only reproducibility check; independent replay of the first H7 and H1 draws from the saved RNG",
        observations=records,empty_replay_fallback=fallback,wm_updates=0,actor_updates=0),indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("run")
    main(p.parse_args().run)
