"""Intervene on the actual starting position/hinge with all other measured state held fixed."""
import argparse
import csv
from pathlib import Path

import numpy as np
import torch
from supermimic.tasks.task_spec import build_actor_obs_td
from learning.b0.contact_policy import DoorMotions, actor_goal_schema, build_actor, sensor
from learning.b0.model import RobotRepresentation, full_state
from learning.b0.physics import ActionMap, make_model
from scripts.b0.recovery_bc import REFERENCE, REF


@torch.no_grad()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoints", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    a = parser.parse_args()
    model = make_model()
    rep = RobotRepresentation(model, "cpu")
    mapping = ActionMap(model)
    rows = []
    for path in a.checkpoints:
        saved = torch.load(path, weights_only=False, map_location="cpu")
        cfg = saved["cfg"]
        actor, _ = build_actor(rep, cfg, model, "cpu")
        actor.load_state_dict(saved["actor"])
        actor.eval()
        bank = DoorMotions([REFERENCE / x for x in REF.values()], rep, "cpu", actor_schema=actor_goal_schema(cfg))
        for side, ref in REF.items():
            frame = torch.tensor([bank.starts[ref]])
            q = bank.qpos[frame].clone()
            v = bank.qvel[frame]
            h = sensor(rep, full_state(q,v), torch.zeros((1,23)))[:,None].expand(-1,10,-1)
            def physical(pose):
                _, g = bank.goals(rep, frame, pose[:,:7], pose[:,31])
                return actor(build_actor_obs_td({"motion":g},h))[0].numpy()*mapping.scale
            nominal = physical(q)
            for name, col, delta in [("world_x",0,.05),("world_y",1,.05),("hinge",31,np.deg2rad(2))]:
                for sign in (-1,1):
                    shifted = q.clone()
                    shifted[:, col] += sign*delta
                    change = physical(shifted)-nominal
                    rows.append(dict(checkpoint=str(path), side=side, input=name, change=sign*delta,
                        leg_rad_max=np.abs(change[:12]).max(),wheel_rad_s_max=np.abs(change[12:16]).max(),
                        arm_rad_max=np.abs(change[16:22]).max(),jaw_m_abs=abs(change[22])))
    with a.output.open("x") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


if __name__=="__main__":
    main()
