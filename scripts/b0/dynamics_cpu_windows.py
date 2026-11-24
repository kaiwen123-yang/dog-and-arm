"""Cross-check two decisive archived-command windows on CPU MuJoCo, separately from Warp."""
import json
from pathlib import Path

import mujoco as mj
import numpy as np

from learning.b0.physics import ActionMap, ContactMeter, make_model

OUT=Path("results/b0/standard_dynamics_20261124/warp_windows")
RAW=Path("results/raw_large/b0/dynamics_20261124/warp_windows")
OLD=Path("results/raw_large/b0/temporal_entries_v1")


def main():
    reg=json.loads((OUT/"registration.json").read_text())
    ids=("pull_5_train_grasp/t7/b23","push_0_validation_grip_hold/t0/b0")
    rows=[]
    for item in reg["items"]:
        if item["trace_id"] not in ids:
            continue
        t,b=item["transition"],item["lane"]
        folder=OLD/item["start"]
        with np.load(folder/"start.npz") as f:
            s=dict(f)
        with np.load(folder/"substeps.npz") as f:
            q=f["qpos_post"][:t+1,b].reshape(-1,32)
            v=f["qvel_post"][:t+1,b].reshape(-1,31)
            u=f["ctrl"][:t+1,b].reshape(-1,23)
        for r in (1,2,4,8,16):
            m=make_model()
            a=ActionMap(m)
            d=mj.MjData(m)
            meter=ContactMeter(m,"preview_floor","back" if item["side"]=="push" else "front")
            d.qpos[:],d.qvel[:]=s["qpos"],s["qvel"]
            mj.mj_forward(m,d)
            d.qacc_warmstart[:]=s["qacc_warmstart"]
            for i in range(t*10):
                d.ctrl[:]=u[i]
                mj.mj_step(m,d)
                d.qpos[:],d.qvel[:]=q[i],v[i]
            m.opt.timestep=.002/r
            records={k:[] for k in ("qpos","qvel","tcp_start","door_force_n","finger_n","eq_residual_m")}
            for target in u[t*10:]:
                d.ctrl[:]=target
                for z in range(r):
                    mj.mj_step(m,d)
                    contact=meter.measure(d)
                    for k,x in (("qpos",d.qpos),("qvel",d.qvel),("tcp_start",d.site_xpos[m.site("p4_grasp").id]),
                                ("door_force_n",np.linalg.norm(contact.door_force)),("finger_n",contact.finger_normal),
                                ("eq_residual_m",d.efc_pos[0])):
                        records[k].append(np.array(x))
            rawfile=RAW/f"{item['trace_id'].replace('/','__')}__cpu_{mj.__version__}__r{r}.npz"
            np.savez_compressed(rawfile,**records)
            w=np.array(records["qvel"])[:,a.dof[[19,21]]]
            rows.append(dict(id=item["trace_id"],h_s=m.opt.timestep,raw=str(rawfile),
                             wrist_peak_rad_s=abs(w).max(0).tolist(),wrist_endpoint_rad_s=w[-1].tolist(),
                             peak_force_n=float(max(records["door_force_n"])),
                             both_duration_s=float((np.array(records["finger_n"])>.01).all(1).sum()*m.opt.timestep)))
    record=dict(engine="cpu-mujoco-"+mj.__version__,windows=rows,command="complete registered 23d Warp ctrl every 2ms",
                state="Registered q/v; initial Warp warmstart plus CPU preceding 2ms solves with measured states. Other internal backend caches cannot be transferred. No formal case or training labels.",
                clocks="F/TCP on interval start, q/v on interval end")
    (OUT/f"cpu_{mj.__version__}.json").write_text(json.dumps(record,indent=2,allow_nan=False)+"\n")


if __name__=="__main__":
    main()
