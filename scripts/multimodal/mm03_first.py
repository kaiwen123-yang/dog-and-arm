"""Retain and independently reload the first full, frame-zero MM03 student success."""
import json
from pathlib import Path

import numpy as np

from scripts.multimodal.mm03_launch import read, write
from scripts.multimodal.mm03_videos import render


def first_claim(root):
    marker = root/"videos/mm03/first_case.json"
    if marker.is_file():
        return read(marker)
    candidates = [p for lane in ("B","C") for p in (root/lane/"success").glob("*.json")]
    if not candidates:
        return None
    for path in sorted(candidates, key=lambda p:(p.stat().st_mtime_ns,str(p))):
        claim = read(path)
        r = read(Path(claim["case"]))
        episode = Path(claim["episode"])
        modes = np.load(episode/"execution_source.npy", mmap_mode="r")
        times = np.load(episode/"t.npy",mmap_mode="r")
        if not (r["success"] and r["mode"]=="pure" and r["teacher_steps"]==0 and
                len(r["events"])==12 and r.get("parent_tick",0)==0 and times[0]==0 and not modes.any()):
            raise ValueError(f"Invalid first-success identity: {path}")
        claim.update(claim=str(path),lane=path.parent.parent.name,
                     events=r["events"],physics_steps=r["physics_steps"])
        write(marker,claim)
        return claim


def deliver(root, *, video_only=False):
    claim = first_claim(root)
    if not claim:
        return False
    dst=root/"videos/mm03"
    case=Path(claim["case"])
    row=read(case)
    render(case,Path(claim["episode"]),dst/"first_student_full_1080p.mp4","MM03",False)
    if video_only:
        return True
    if (dst/"independent_reloads.json").exists():
        return True
    records=[]
    for n in (1, 2):
        # Each new path gets its own strict weight load in the batched service. The
        # frozen source inode is shared while solver/camera/history start anew.
        ckpt=dst/f"independent_reload{n}.pt"
        if not ckpt.exists():
            ckpt.hardlink_to(Path(claim["checkpoint"]))
        job={**row,"id":f"first_success_reload{n}", "partition":"first_success_reloads",
             "mode":"pure", "use":"evaluation", "checkpoint":str(ckpt)}
        if claim["lane"]=="B":
            from scripts.multimodal.mm03_b_physics import episode
            new=episode((str(root),job))
        else:
            from scripts.multimodal.mm02_physics import execute
            from scripts.multimodal.mm03_inference import PolicyClient
            job["partition"]="C/first_success_reloads"
            client=PolicyClient(ckpt,kind="mm02")
            try:
                new=execute(root,job,client=client,deliver_success=False)
            finally:
                client.close()
        if new["teacher_steps"] or new["initial_state_sha256"]!=row["initial_state_sha256"]:
            raise ValueError("First-success reload did not match the physical reset or executor")
        records.append(dict(number=n,checkpoint=str(ckpt),success=new["success"],
                            ordered_events=len(new["events"]),physics_steps=new["physics_steps"],
                            case=str(Path(new["raw_episode"]).parent/"result.json"),
                            first_failure=new["first_failure"]))
    write(dst/"independent_reloads.json",records)
    return True
