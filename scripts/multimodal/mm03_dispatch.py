"""Dispatch already registered training episodes using lengths from the preceding round."""
from collections import defaultdict
import json
from pathlib import Path
from statistics import median


def condition(job):
    if job["mode"] == "prefix":
        return ("prefix", job["side"], int(job["switch_phase"])//2)
    return ("pure", job["scene"], job["side"], int(job["goal"]))


def physical_queue(root, pending):
    if not pending or not pending[0]["partition"].endswith("/collect") or pending[0]["round"]<2:
        return pending, 0
    # Preserve policy-package locality for central batched inference. The original
    # registration, BC membership and returned result order are independent of this queue.
    by_model=defaultdict(list)
    for job in pending:
        by_model[job["method"],job["seed"]].append(job)
    output=[]
    predicted=0
    for (method,seed),jobs in by_model.items():
        prior=Path(root)/"B"/"rounds"/f"r{jobs[0]['round']-1:02d}"
        plan=prior/"collection_plan"/f"{method}_seed{seed}.json"
        lengths=defaultdict(list)
        if plan.is_file():
            for old in json.loads(plan.read_text())["cases"]:
                path=prior/"collect"/old["id"]/"result.json"
                if path.is_file():
                    result=json.loads(path.read_text())
                    lengths[condition(old)].append(int(result["physics_steps"]))
        if all(condition(j) in lengths for j in jobs):
            jobs=sorted(jobs,key=lambda j:-median(lengths[condition(j)]))
            predicted+=len(jobs)
        output.extend(jobs)
    return output,predicted

