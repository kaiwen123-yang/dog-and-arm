"""Exact read-only wheel/ground meter for MM03 native short branches."""
import argparse
import ctypes as ct
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np


def prepare(root,source):
    import fcntl
    import mujoco as mj
    from scripts.multimodal.mm03_launch import write, now
    if mj.__version__!="3.3.0":
        raise RuntimeError("The registered native interpreter must build the meter")
    folder=root/"resources/native_contacts"
    folder.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    dest=folder/f"wheel_normals_{digest[:16]}.so"
    package=Path(mj.__file__).resolve().parent
    library=package/"libmujoco.so.3.3.0"
    with (folder/"build.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if not dest.exists():
            tmp=dest.with_name(f".{dest.name}.{os.getpid()}.part")
            subprocess.run(["cc","-std=c11","-O2","-fPIC","-shared","-fno-fast-math","-ffp-contract=off",
                "-Wall","-Wextra","-Werror",f"-I{package/'include'}",str(source),str(library),
                f"-Wl,-rpath,{package}","-o",str(tmp)],check=True)
            if ct.CDLL(str(tmp)).mm03_native_abi()!=mj.mj_version():
                raise RuntimeError("Native wheel reader ABI mismatch")
            tmp.replace(dest)
        write(folder/"index.json",dict(at=now(),source_sha256=digest,library=dest.name,
             native=mj.__version__,abi=mj.mj_version(),native_steps=0,optimizer_updates=0))
    return dest


@lru_cache(maxsize=2)
def load_kernel(path, stamp, abi):
    lib=ct.CDLL(str(path))
    if lib.mm03_native_abi()!=abi:return None
    fn=lib.mm03_wheel_normals
    fn.argtypes=[ct.c_void_p,ct.c_void_p,ct.c_int,ct.POINTER(ct.c_int),ct.c_int,ct.POINTER(ct.c_double)]
    fn.restype=ct.c_int
    return fn


class WheelNormals:
    def __init__(self,original,kernel):
        from p6_contacts import ContactSample
        self.base=original
        self.sample=ContactSample
        self.kernel=kernel
        m=original.model
        indices=[original.wheels.get(int(body),-1) if original.robot[i] else -1
                 for i,body in enumerate(m.geom_bodyid)]
        self.indices=(ct.c_int*m.ngeom)(*indices)
        self.model_ptr=m._address
        self.raw=(ct.c_double*4)()
        self.view=np.ctypeslib.as_array(self.raw)
        self.hits=0
        self.fallbacks=0

    def __getattr__(self,name):
        return getattr(self.base,name)

    def measure(self,data,details=False,*,wheel_slip=True):
        if not wheel_slip and not details and self.kernel(
                self.model_ptr,data._address,self.base.floor,self.indices,len(self.indices),self.raw):
            self.hits+=1
            loads=self.view.copy()
            finger=np.zeros(2)
            door,torque,hand=np.zeros((3,3))
            return self.sample(loads,np.full(4,np.nan),np.full(4,np.nan),loads>=self.base.wheel_threshold_n,
                               finger,bool((finger>self.base.contact_threshold_n).all()),{},door,torque,hand,0.,0.,[])
        self.fallbacks+=1
        return self.base.measure(data,details,wheel_slip=wheel_slip)


def wrap(original):
    import mujoco as mj
    socket=os.environ.get("MM03_INFERENCE_SOCKET")
    if not socket or mj.__version__!="3.3.0":return original
    folder=Path(socket).parent.parent/"resources/native_contacts"
    try:
        info=json.loads((folder/"index.json").read_text())
        name=info["library"]
        if Path(name).name!=name or info["native"]!=mj.__version__:return original
        path=folder/name
        fn=load_kernel(path,path.stat().st_mtime_ns,mj.mj_version())
    except (OSError,ValueError,KeyError,AttributeError):
        return original
    return WheelNormals(original,fn) if fn is not None else original


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--source",type=Path,default=Path(__file__).parent/"native/mm03_wheel_normals.c")
    args=p.parse_args()
    print(prepare(args.root.resolve(),args.source.resolve()))
