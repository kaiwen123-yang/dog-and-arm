"""Read a published RefXY2 recovery boundary and compare the physical ring, solver and RNG."""
import argparse
from pathlib import Path
from unittest.mock import patch
import numpy as np
import torch
from scripts.b0 import refxy2_state as state
from scripts.b0 import official_flow_restore_check as checks


def verify(mode, u):
    run, _ = state.flow.build(state.config(mode))
    receipt = state.restore(run,mode,u)
    light=state.LIGHT/mode/"verification"
    with patch.object(checks,"OUT",light):
        checks.verify_loaded(run,receipt)
    package=state.read_pt(state.checkpoint(mode,u))
    for name in ("actor","critic","dyn"):
        for key,value in getattr(run,name).state_dict().items():
            assert torch.equal(value.cpu(),package[name][key]),(name,key)
    saved=state.read_pt(state.state_dir(mode,u)/"state.pt")
    for k,value in saved["lanes"].items():
        assert torch.equal(run.lanes[k].cpu(),value),k
    for k,value in saved["counters"].items():
        assert torch.equal(getattr(run.plant,k).cpu(),value),k
    parent=state.io.read(state.PARENT)
    base=state.read_pt(Path(parent["state"])/"state.pt")["replay"]["pages"]
    # Start with each parent's original page and overlay only archived slots.
    # This also verifies untouched rows when the latest update is mid-page.
    by_page={}
    for i in receipt["delta_nodes"]:
        step=state.io.read(state.node(mode,i))
        for tick in range(step["previous_clock"],step["clock"]):
            p,o=divmod(tick%run.replay.capacity,run.replay.page_size)
            by_page.setdefault(p,{})[o]=(i,tick)
    fields_checked=0
    for page,fields in run.replay.pages.items():
        expected={k:v.clone() for k,v in base[page].items()} if page in by_page else base[page]
        nodes={i for i,_ in by_page.get(page,{}).values()}
        for i in nodes:
            with np.load(state.state_dir(mode,i)/"replay_delta.npz") as archive:
                for offset,(node,tick) in by_page[page].items():
                    if node==i:
                        for key,value in expected.items():
                            value[offset].copy_(torch.from_numpy(archive[f"{tick}/{key}"]))
        for k,val in fields.items():
            assert torch.equal(val.cpu().contiguous().view(torch.uint8),expected[k].contiguous().view(torch.uint8)),(page,k)
            fields_checked+=1
    details=state.io.read(light/f"restored_u{u:06}.json")
    state.io.write(light/f"complete_{u:06}.json",details|dict(mode=mode,local_update=u,replay_pages=len(base),
        replay_field_tensors_exact=fields_checked,live_lane_fields=list(saved["lanes"]),counters=list(saved["counters"]),
        checkpoint=receipt["checkpoint"],delta_nodes=receipt["delta_nodes"],new_physical_cases=0))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=state.METHOD)
    p.add_argument("node",type=int)
    a=p.parse_args()
    verify(a.mode,a.node)
