"""Compare current reference joint positions with physical setpoints and test four Warp segments."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from learning.b0.physics import ActionMap, FINGERS, make_model
from scripts.b0.calibrate_contact_actor import REFS
from scripts.b0.eval_contact_segments import WarpSingleWorld, dump, evaluate_segment

REFERENCES = Path("results/raw_large/b0/contact_held_r1")
MANIFEST = Path("config/b0/contact_dev_v1.json")
CHECKPOINT = Path("results/b0/contact_s0_bc_effort32_r1/actor_003000.pt")
SOURCE = "frozen BC first 16 raw channels; current given reference six arm positions and two-finger opening for last seven; no learned residual"


def reference_targets(path, model, mapping):
    # DoorMotions.joint_pos is qpos[7:31] in float32. The first 24 values of
    # motion_goal_window expose that exact current frame to the Actor.
    q = np.load(path/"qpos.npy", mmap_mode="r")
    fingers = [model.joint(joint).qposadr.item() for joint in FINGERS]
    arm = q[:, mapping.q[16:22]].astype(np.float32)
    width = q[:, fingers[0]].astype(np.float32) - q[:, fingers[1]].astype(np.float32)
    return np.column_stack([arm, width])


def error_metrics(values):
    return dict(rmse=float(np.sqrt(np.mean(values**2))),
                p95_absolute=float(np.quantile(np.abs(values), .95)),
                mean_signed=float(np.mean(values)))


def measure(output):
    model = make_model()
    mapping = ActionMap(model)
    rows = []
    for split in ("train","validation"):
        errors, phases, sides = [], [], []
        for name in REFS:
            train = REFERENCES/name
            path = REFERENCES/name.replace("train",split)
            reference = reference_targets(train,model,mapping)
            valid = np.load(path/"valid_full_interval.npy")
            n = min(int(valid.sum()), int(np.load(train/"valid_full_interval.npy").sum()))
            # Use the calibration's identical complete-history and reference clocks.
            nominal_action = (reference[9:n]-mapping.offset[16:])/mapping.scale[16:]
            actual = np.load(path/"physical_target.npy")[9:n,16:]
            observed = np.load(path/"action_clipped.npy")[9:n,16:]
            np.testing.assert_allclose(mapping.offset[16:]+mapping.scale[16:]*observed,actual,atol=1e-12)
            # Include the same safety clamp used at a real policy boundary.
            decoded = mapping.offset[16:]+mapping.scale[16:]*np.clip(nominal_action,-1,1)
            errors.append(decoded-actual)
            meta = json.loads((path/"metadata.json").read_text())
            phases.extend(np.array(meta['phases'])[np.load(path/"phase.npy")[9:n]])
            sides.extend([meta["task"]]*(n-9))
        residual = np.concatenate(errors)
        phases, sides = np.asarray(phases), np.asarray(sides)
        for side in ("all","pull","push"):
            side_mask = np.ones(len(sides),bool) if side=="all" else sides==side
            for phase in ("all",*np.unique(phases[side_mask])):
                select = side_mask if phase=="all" else side_mask & (phases==phase)
                r = residual[select]
                row = dict(split=split,side=side,phase=phase,frames=len(r))
                for block, values in (("arm_rad",r[:,:6]),("jaw_mm",r[:,6]*1000)):
                    row.update({f"{block}_{k}":v for k,v in error_metrics(values).items()})
                rows.append(row)
    with (output/"errors.csv").open("x") as handle:
        writer = csv.DictWriter(handle, rows[0].keys(),lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    dump(output/"method.json",dict(method="current frame of the given training motion's six arm positions and two-finger width as held servo setpoints",source=str(REFERENCES),given_references=REFS,
         signed_error="clipped current training reference joint position or width minus issued 20 ms physical setpoint",
         phases="actual measured phase at interval start",frames="9..min(N_nominal,N_measured)-1, matching BC u3000",
         validation="held-target perturbed validation labels at same absolute frame; given reference always the training nominal",
         pooled_arm="six component errors per included frame; p95 absolute error; jaw reported in mm"))


def physical(output):
    from learning.b0.contact_policy import load_policy
    manifest = json.loads(MANIFEST.read_text())["cases"]
    policy = load_policy(CHECKPOINT,[REFERENCES/n for n in REFS],"cuda:0")
    raw_root = Path("results/raw_large/b0")/output.name
    rows = []
    for side in ("pull","push"):
        model = make_model("mobile" if side=="pull" else "push")
        mapping = ActionMap(model)
        plant = WarpSingleWorld(model,"cuda:0")
        for segment in ("stable_grip","open_5"):
            registered = manifest[f"{side}/{segment}"]
            path = REFERENCES/registered["episode"]
            poses = reference_targets(path,model,mapping)

            def hybrid(episode, frame, q, v, prev):
                action = policy(episode,frame,q,v,prev).astype(np.float64, copy=True)
                action[16:] = (poses[frame]-mapping.offset[16:])/mapping.scale[16:]
                return action

            case = Path(side)/segment/"nominal"
            result = evaluate_segment(hybrid,path,segment,registered["nominal"]["perturbation"],"warp",
                                      output/case,model=model,integrator=plant,raw_dir=raw_root/case,
                                      video=True,action_source=SOURCE)
            original = Path("results/b0/contact_s0_bc_u3000_warp_r1")/case/"result.json"
            baseline = json.loads(original.read_text())
            rows.append(dict(side=side,segment=segment,paired_original=str(original),
                       original_passed=baseline["passed"],original_physics_steps=baseline["physics_steps"],
                       original_failure=baseline["first_failure"],diagnostic_passed=result["passed"],
                       diagnostic_physics_steps=result["physics_steps"],diagnostic_failure=result["first_failure"],
                       diagnostic_final_door_deg=result["final_door_deg"]))
            print(side,segment,result["passed"],result["physics_steps"],flush=True)
    dump(output/"comparison.json",dict(method=SOURCE,checkpoint=str(CHECKPOINT),manifest=str(MANIFEST),
                                      case_type="paired nominal physical control diagnostic",cases=rows))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("measure","warp"))
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    (measure if args.mode=="measure" else physical)(args.output)
