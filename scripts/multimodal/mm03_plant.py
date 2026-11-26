"""MM03 native model files, verified against each registered training geometry before use."""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

import mujoco as mj
import numpy as np

from learning.b0.physics import build
from scripts.multimodal.collect_feasibility import teacher_config
from scripts.multimodal.mm03_launch import read,write,now


def signature(cfg):
    def scalars(v):
        if isinstance(v,np.ndarray):return v.tolist()
        if isinstance(v,np.generic):return v.item()
        raise TypeError(type(v).__name__)
    return hashlib.sha256(json.dumps(cfg,sort_keys=True,default=scalars,
                          allow_nan=False,separators=(",",":")).encode()).hexdigest()


def binary(model):
    target=np.empty(mj.mj_sizeModel(model),dtype=np.uint8)
    mj.mj_saveModel(model,None,target)
    return target


@lru_cache(maxsize=2)
def inventory(path, stamp):
    return read(path)


def verified_file(root, scene, side, goal, cfg):
    if root is None:
        return None
    folder=Path(root)/"resources/native_models"
    index=folder/"index.json"
    try:
        stamp=index.stat().st_mtime_ns
    except FileNotFoundError:
        return None
    info=inventory(index,stamp)
    item=info.get("models",{}).get(f"{scene['id']}/{side}/{int(goal)}")
    if not item or info.get("mujoco")!=mj.__version__ or item["config_signature"]!=signature(cfg):
        return None
    path=folder/item["file"]
    if not path.is_file() or path.stat().st_size!=item["bytes"]:
        return None
    return path


def prepare_pair(args):
    folder,scene,side=args
    records={}
    for goal in (15,25):
        cfg=teacher_config(side,goal,scene)
        start=time.monotonic()
        model=build(cfg)
        elapsed=time.monotonic()-start
        data=binary(model)
        key=hashlib.sha256(memoryview(data)).hexdigest()
        dest=folder/(key+".mjb")
        if not dest.exists():
            tmp=folder/(key+f".{os.getpid()}.part")
            with tmp.open("xb") as f:
                f.write(memoryview(data))
            tmp.replace(dest)
        size=data.nbytes
        del model,data
        start=time.monotonic()
        loaded=mj.MjModel.from_binary_path(str(dest))
        load_s=time.monotonic()-start
        if hashlib.sha256(memoryview(binary(loaded))).hexdigest()!=key:
            raise ValueError(f"Serialized native model differs after load: {dest}")
        records[f"{scene['id']}/{side}/{goal}"]=dict(file=dest.name,bytes=size,sha256=key,
                config_signature=signature(cfg),original_build_s=elapsed,load_s=load_s)
        del loaded
    return records


def prepare(root):
    from scripts.multimodal.mm02_physics import scenes
    import fcntl
    folder=root/"resources/native_models"
    folder.mkdir(parents=True,exist_ok=True)
    with (folder/"prepare.lock").open("a") as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        if (folder/"index.json").is_file():
            return read(folder/"index.json")
        if mj.__version__!="3.3.0":raise ValueError("The registered native binary requires MuJoCo 3.3.0")
        catalog=scenes()
        jobs=[(folder,catalog[s],side) for s in ("tr_nominal","tr_offset","tr_load") for side in ("pull","push")]
        models={}
        with ProcessPoolExecutor(2,mp_context=multiprocessing.get_context("spawn")) as pool:
            for result in pool.map(prepare_pair,jobs):
                models.update(result)
        unique={v["file"]:v["bytes"] for v in models.values()}
        index=dict(prepared_beijing=now(),mujoco=mj.__version__,models=models,
                   unique_native_files=len(unique),total_bytes=sum(unique.values()),
                   additional_native_steps=0,additional_optimizer_updates=0,
                   scope="Three training scenes, two door sides, both goals. Equal serialized native models share a file. All goal-specific scoring configurations stay separate.")
        write(folder/"index.json",index)
        return index


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",required=True,type=Path)
    a=p.parse_args()
    data=prepare(a.root)
    print(json.dumps({k:v for k,v in data.items() if k!="models"}),flush=True)

