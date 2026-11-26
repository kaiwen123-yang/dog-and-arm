"""Measure exact-batch frozen GPU policy latency on retained MM03 training observations."""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np
import torch

from scripts.multimodal import mm03_inference
from scripts.multimodal.mm03_launch import now, write


def load_candidate(path):
    if path is None:
        return mm03_inference
    spec = importlib.util.spec_from_file_location("mm03_timed_inference", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def training_inputs(episode, width, steps):
    names = ("proprio", "previous_action", "image_index", "image_t", "rgb", "depth", "depth_valid", "t")
    data = {k:np.load(episode/(k+".npy"), mmap_mode="r") for k in names}
    trace = []
    for tick in range(steps):
        batch = []
        for lane in range(width):
            i = 300 + lane*37 + tick
            history = np.arange(i-9,i+1)
            frame = data["image_index"][i]
            fresh = tick==0 or frame!=data["image_index"][i-1]
            age = data["t"][i]-data["image_t"][frame]
            header = mm03_inference.HEADER.pack(int(fresh), int((tick+lane)%3!=0), float(age), i*.02)
            fields=[header, data["proprio"][history].astype("<f4").tobytes(),
                    data["previous_action"][history].astype("<f4").tobytes()]
            if fresh:
                fields.extend(data[k][frame].tobytes() for k in ("rgb","depth","depth_valid"))
            batch.append(b"".join(fields))
        trace.append(batch)
    return trace


def replay(module, service, checkpoint, instruction, trace):
    ck = checkpoint.stat()
    key = (str(checkpoint), ck.st_size, ck.st_mtime_ns, "task")
    clients = [module.Stream("task",key,instruction) for _ in trace[0]]
    outputs, durations = [], []
    for batch in trace:
        requests = [module.Request(c,body) for c,body in zip(clients,batch,strict=True)]
        begin = time.perf_counter()
        service.infer(requests)
        outputs.extend(q.done.result() for q in requests)
        durations.append(time.perf_counter()-begin)
    return outputs, durations


def compare(root, dest, candidate):
    torch.set_num_threads(1)
    episode = root/"B/teachers/teacher_26112600_tr_nominal_pull15/episode"
    instruction = json.loads((episode/"metadata.json").read_text())["task_text"]
    module = load_candidate(candidate)
    baseline = module.ModelBatcher(root,"cuda",32,.7,task_graphs=False)
    proposed = module.ModelBatcher(root,"cuda",32,.7,task_graphs=True)
    rows = []
    with torch.inference_mode():
        for method in ("H9","D23"):
            checkpoint = root/"B/warm"/method/"seed1701/deploy.pt"
            for width in (1,3,9):
                trace=training_inputs(episode,width,80)
                expected,_ = replay(module,baseline,checkpoint,instruction,trace[:10])
                observed,_ = replay(module,proposed,checkpoint,instruction,trace[:10])
                if len(expected)!=len(observed):
                    raise AssertionError("Dropped warmup request")
                outputs=None
                timings={"eager":[], "graph":[]}
                mismatches = 0
                maximum = 0.
                for name in ("eager","graph","graph","eager"):
                    server=baseline if name=="eager" else proposed
                    actual, dt=replay(module,server,checkpoint,instruction,trace)
                    timings[name].append(1000*sum(dt)/len(dt))
                    if outputs is None:
                        outputs=actual
                        continue
                    for before,after in zip(outputs,actual,strict=True):
                        if before!=after:
                            mismatches+=1
                            if before[:3]!=after[:3]:
                                raise AssertionError("Changed action response dimensions")
                            a,b=[np.frombuffer(x[3:],dtype="<f4") for x in (before,after)]
                            maximum=max(maximum,float(np.abs(a-b).max()))
                e,g=map(statistics.mean,(timings["eager"],timings["graph"]))
                row=dict(method=method,batch=width,decisions_compared=width*len(trace),
                         eager_ms=e,graph_ms=g,speedup=e/g,batch_mean_ms=timings,
                         differing_responses=mismatches,max_abs_difference=maximum)
                rows.append(row)
                print(json.dumps(row),flush=True)
    result=dict(at_beijing=now(),source=str(episode),order=["eager","graph","graph","eager"],
        width_is_actual=True,scope="ModelBatcher.infer including real 10 Hz RGB-D and returning the requested actions/auxiliary values",
        native_steps=0,optimizer_steps=0,rows=rows,identical=all(r["differing_responses"]==0 for r in rows))
    write(dest,result)
    if not result["identical"]:
        raise RuntimeError("Action parity failed")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--candidate",type=Path)
    args=parser.parse_args()
    compare(args.root,args.output,args.candidate)

