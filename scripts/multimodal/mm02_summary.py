"""Summarize recorded MM-02 physics, controller sources and paired commands.

Pre-freeze calls inspect initial, development, collection and recovery partitions.
--final additionally reads completed formal, reload and repeat cases after the
terminal decision exists. No new simulations or checkpoint selection are run.
"""
import argparse
from collections import Counter, defaultdict
from itertools import groupby
import json
from pathlib import Path
import pickle

import numpy as np


PHASES = ("approach_base", "settle", "reach_handle", "grasp", "open", "hold",
          "release", "retreat_arm", "post_release_hold", "stow", "retreat_base", "final")
BRANCHES = ("supervised_aggregate", "model_trajectory")
SCENE_ROLES = {"tr_nominal": "nominal", "tr_offset": "train_offset", "tr_load": "train_load",
               "va_pose": "validation", "te_combination": "disclosed_regression",
               "te_mm02_combo_a": "new_blind", "te_mm02_combo_b": "new_blind"}


def read(path):
    return json.loads(path.read_text())


def write(path, value, *, lines=False):
    tmp = path.with_suffix(path.suffix + ".part")
    with tmp.open("w", encoding="utf-8") as f:
        if lines:
            for v in value:
                f.write(json.dumps(v, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
        else:
            json.dump(value, f, ensure_ascii=False, allow_nan=False, indent=2)
            f.write("\n")
    tmp.replace(path)


def ratio(a, b):
    return float(a / b) if b else None


def stage_directories(run, final):
    yield run/"initial"
    yield run/"pilot_development"
    for directory in sorted(run.glob("round[1-6]")):
        for name in ("collection", "development", "recovery_train", "recovery_validation"):
            yield directory/name
    if final:
        if not (run/"terminal_freeze.json").exists():
            raise ValueError("Terminal freeze must precede formal student evaluation and reporting")
        for name in ("formal", "reload"):
            yield run/name
        for group in sorted((run/"repeats").glob("*")):
            if group.is_dir():
                yield group


def load_case(path, run, selected):
    result = read(path)
    episode = path.parent/"episode"
    meta = read(episode/"metadata.json")
    def arr(name):
        return np.load(episode/(name + ".npy"), mmap_mode="r", allow_pickle=False)

    if result["id"] != meta["episode_id"] or result["sha"] != meta["source_checkpoint_sha256"]:
        raise ValueError(f"Case/checkpoint identity differs at {path}")
    t, sub, source = arr("t"), arr("substeps"), arr("execution_source")
    actual, student, expert = arr("executed_action_raw"), arr("student_action_raw"), arr("expert_action_raw")
    clipped, previous = arr("executed_action_clipped"), arr("previous_action")
    valid, label_ok = arr("valid_transition"), arr("expert_label_valid")
    phases = arr("phase")
    judge_phase = arr("judge_phase")
    n = len(sub)
    if (n != result["decision_calls"] or len(t) != n + 1 or sum(sub) != result["physics_steps"] or
            not np.allclose(np.diff(t), .002*sub, atol=1e-8, rtol=0) or not np.array_equal(valid, sub == 10)):
        raise ValueError(f"Decision or physical interval accounting differs at {path}")
    if (not np.array_equal(actual, np.where(source[:, None], expert, student)) or
            not np.array_equal(previous[1:], clipped) or
            not np.array_equal(valid & label_ok, arr("action_supervision_mask")) or
            not np.allclose(np.clip(actual, -1, 1), clipped, rtol=0, atol=1e-7) or
            not np.allclose(np.clip(expert, -1, 1), arr("expert_action_target"), rtol=0, atol=1e-7)):
        raise ValueError(f"Inconsistent expert, actual action, predecessor or BC membership at {path}")
    mode = result["mode"]
    recovery = mode == "recovery"
    blocks = meta["block_executors"]
    if ((mode == "pure" and np.any(source)) or (recovery and not np.all(source)) or
            (mode == "mixed" and not np.array_equal(np.repeat(blocks, 10)[:n], source))):
        raise ValueError(f"Unexpected actual controller sequence at {path}")
    if result["bc_labels"] != int(np.sum(valid & label_ok)) or int(source.sum()) != result["teacher_steps"]:
        raise ValueError(f"Actual source or label count differs at {path}")
    if result["scene"] in ("te_mm02_combo_a", "te_mm02_combo_b") and not (run/"terminal_freeze.json").exists():
        raise ValueError(f"Blind student result before terminal freeze at {path}")

    qpos, obj = arr("qpos"), arr("object_state")
    # The passive hinge is the last joint appended by p6_scene.build. Verify its
    # recorded float32 supervision column before using full-precision differences.
    if not np.allclose(qpos[:, -1], obj[:, 0], atol=2e-7, rtol=1e-6):
        raise ValueError(f"Recorded hinge order differs at {path}")
    start, end = (float(np.rad2deg(qpos[i, -1])) for i in (0, -1))
    span = [2*x["scale"] for x in meta["action_channels"][16:22]]
    rms_ratio = result["joint_servo_rmse_over_range"]
    baseline = {"seen_contact": 0, "two_finger": 0, "wrong_contact": 0, "steps": 0, "events": []}
    anchor_phase = None
    if recovery:
        c = selected[result["anchor_key"]]
        # Read the locally generated integration receipt for inherited counters.
        # The recovery result contains the independent judge's full episode clock.
        with Path(c["path"]).open("rb") as f:
            original = pickle.load(f)
        baseline = original["judge"]
        anchor_phase = original["phase"]
        if baseline["steps"] != round(t[0]/.002) or original["key"] != result["anchor_key"]:
            raise ValueError(f"Recovery clock differs from its parent at {path}")
    all_events = result["events"]
    events = all_events[len(baseline["events"]):]
    if (tuple(e["phase"] for e in all_events) != PHASES[:len(all_events)]
            or any(e["end_step"] <= baseline["steps"] for e in events)):
        raise ValueError(f"Independent event order or recovery prefix differs at {path}")
    if not recovery and result["success"] != (len(events) == len(PHASES) and not result["first_failure"]):
        raise ValueError(f"Full-task success is inconsistent at {path}")
    level = path.parent.parent.relative_to(run).as_posix()
    failure = result["first_failure"]
    joint_margin = result["joint_min_margin_rad"]
    actual_over = np.abs(actual) > 1 + 1e-7
    teacher_over = np.abs(expert) > 1 + 1e-7
    denom = result["goal"] - start
    exec_teacher = source.astype(bool)
    phase_counts = Counter(meta["phases"][int(i)] for i in phases)
    judge_counts = Counter(PHASES[int(i)] for i in judge_phase)
    qualified_phases = Counter(meta["phases"][int(i)] for i in phases[label_ok])
    differing_query = (np.max(np.abs(arr("expert_action_target")-clipped),axis=1) > 1e-4)
    # Preserve exact joint/extremum and event times for individual failures.
    return dict(
        id=result["id"], partition=level, round=result["round"], branch=result["branch"], mode=mode,
        scene=result["scene"], scene_role=SCENE_ROLES[result["scene"]], side=result["side"], goal=result["goal"],
        checkpoint_sha256=result["sha"], reset_sha256=result["initial_state_sha256"],
        raw_episode=episode.relative_to(run).as_posix(),
        status=("h32_complete" if result["horizon_complete"] else "shortened_recovery") if recovery else
               ("success" if result["success"] else "failure"),
        success=None if recovery else result["success"], first_failure=failure["reason"] if failure else None,
        failure_phase=failure["phase"] if failure else None, failure_step=failure["step"] if failure else None,
        next_phase=result["next_phase"], events=[[e["phase"], e["end_step"]] for e in events],
        parent_episode=result.get("parent_episode"), anchor_phase=anchor_phase, anchor_tick=result["parent_tick"],
        anchor_key=result.get("anchor_key"), parent_events=len(baseline["events"]),
        evaluated_physics_steps=result["physics_steps"], post_action_start_s=float(t[0]), end_s=float(t[-1]),
        decisions=n, valid_transitions=int(valid.sum()), eligible_bc_labels=int(label_ok.sum()),
        labels_with_complete_successor=int(np.sum(label_ok & valid)),
        labels_on_partial_final_interval=int(np.sum(label_ok & ~valid)),
        student_steps_with_distinct_qualified_expert=int(np.sum(~exec_teacher & label_ok & differing_query)),
        expert_qualification=result["expert_label_reason_counts"], frames=result["camera_frames"],
        fresh_exposures=int(np.count_nonzero(arr("image_t") >= t[0]-1e-9)),
        teacher_decisions=result["teacher_steps"], teacher_physics_steps=int(sub[exec_teacher].sum()),
        student_decisions=n-result["teacher_steps"], teacher_blocks=result["teacher_blocks"],
        total_blocks=result["selected_blocks"], registered_teacher_probability=result["probability"] if mode=="mixed" else None,
        teacher_decision_fraction=ratio(result["teacher_steps"], n), teacher_control_phases=dict(phase_counts),
        judge_control_phases=dict(judge_counts), qualified_expert_phases=dict(qualified_phases),
        student_request_out_of_range_channels=int((abs(student)>1+1e-7).sum()),
        executed_request_out_of_range_channels=int(actual_over.sum()),
        expert_request_out_of_range_channels=int(teacher_over.sum()),
        door_contact_steps=result["robot_door_contact_steps"]-baseline["seen_contact"],
        bilateral_steps=result["bilateral_contact_steps"]-baseline["two_finger"],
        unexpected_contact_steps=result["unexpected_contact_steps"]-baseline["wrong_contact"],
        initial_deg=start, final_deg=end, target_error_deg=end-result["goal"],
        final_within_angle_tolerance=abs(end-result["goal"]) <= 2,
        angle_progress_ratio=ratio(end-start, denom),
        minimum_margin_j1_to_j6_rad=[round(x, 10) for x in joint_margin],
        j1_to_j6_servo_rmse_rad=[round(x*y, 10) for x,y in zip(rms_ratio,span)],
        j1_to_j6_servo_rmse_over_range=[round(x, 10) for x in rms_ratio],
        last_station_error_m=result["last"].get("station_error_m"), closest_station_m=result["closest_station_m"] if not recovery else None,
        last_base_speed_m_s=result["last"].get("base_speed_m_s"), wall_s=result["wall_s"])


def totals(rows):
    def total(k):
        return sum(r[k] for r in rows)
    duration_steps = total("evaluated_physics_steps")
    event_counts = Counter(e[0] for r in rows for e in r["events"])
    qualified, phases, qualified_phases, anchors = Counter(), Counter(), Counter(), Counter()
    for r in rows:
        qualified.update(r["expert_qualification"])
        phases.update(r["teacher_control_phases"])
        qualified_phases.update(r["qualified_expert_phases"])
        if r["anchor_phase"]:
            anchors[r["anchor_phase"]] += 1
    row_n = len(rows)
    complete_episode = [r for r in rows if r["success"] is not None]
    costs = {k: total(k) for k in ("decisions", "valid_transitions", "eligible_bc_labels",
                                   "labels_with_complete_successor", "labels_on_partial_final_interval",
                                   "student_steps_with_distinct_qualified_expert", "frames",
                                   "fresh_exposures", "teacher_decisions", "student_decisions",
                                   "teacher_physics_steps", "door_contact_steps", "bilateral_steps",
                                   "unexpected_contact_steps", "teacher_blocks", "total_blocks",
                                   "student_request_out_of_range_channels", "executed_request_out_of_range_channels",
                                   "expert_request_out_of_range_channels")}
    weights = [r["evaluated_physics_steps"] for r in rows]
    rmse = np.array([r["j1_to_j6_servo_rmse_rad"] for r in rows])
    norm_rmse = np.array([r["j1_to_j6_servo_rmse_over_range"] for r in rows])
    return dict(
        attempts=row_n, full_task_successes=sum(r["success"] for r in complete_episode),
        full_episode_denominator=len(complete_episode), statuses=dict(Counter(r["status"] for r in rows)),
        pure_student_successes=sum(r["success"] for r in rows if r["mode"]=="pure"),
        pure_student_denominator=sum(r["mode"]=="pure" for r in rows),
        first_failure_reason=dict(Counter(r["first_failure"] for r in rows if r["first_failure"])),
        first_failure_phase=dict(Counter(r["failure_phase"] for r in rows if r["failure_phase"])),
        completed_event_counts={p:event_counts[p] for p in PHASES}, expert_qualification=dict(qualified),
        teacher_phase_decisions=dict(phases), valid_bc_by_teacher_phase=dict(qualified_phases),
        recovery_anchors_by_judge_phase=dict(anchors),
        cases_with_door_contact=sum(r["door_contact_steps"]>0 for r in rows),
        cases_with_bilateral_contact=sum(r["bilateral_steps"]>0 for r in rows),
        cases_with_unexpected_contact=sum(r["unexpected_contact_steps"]>0 for r in rows),
        frame_ends_within_angle_tolerance=sum(r["final_within_angle_tolerance"] for r in rows),
        mean_angle_progress_ratio=float(np.mean([r["angle_progress_ratio"] for r in rows
                                                if r["angle_progress_ratio"] is not None]))
                                  if any(r["angle_progress_ratio"] is not None for r in rows) else None,
        max_abs_hinge_change_deg=max(abs(r["final_deg"]-r["initial_deg"]) for r in rows),
        minimum_arm_margin_rad=np.min([r["minimum_margin_j1_to_j6_rad"] for r in rows], axis=0).tolist(),
        pooled_arm_servo_rmse_rad=np.sqrt(np.average(rmse**2, axis=0, weights=weights)).tolist(),
        pooled_arm_servo_rmse_over_range=np.sqrt(np.average(norm_rmse**2, axis=0, weights=weights)).tolist(),
        physics_steps=duration_steps, simulated_s=.002*duration_steps, sum_worker_case_wall_s=total("wall_s"),
        actual_teacher_fraction_policy=ratio(costs["teacher_decisions"], costs["decisions"]),
        actual_teacher_fraction_physics=ratio(costs["teacher_physics_steps"], duration_steps),
        actual_teacher_fraction_blocks=ratio(costs["teacher_blocks"], costs["total_blocks"]),
        **costs)


def command_pairs(run, rows):
    key = lambda r: (r["partition"], r["branch"], r["checkpoint_sha256"], r["scene"], r["side"])
    paired = []
    for _, items in groupby(sorted((r for r in rows if r["mode"]=="pure"), key=key), key):
        members = sorted(items, key=lambda r: r["goal"])
        if [r["goal"] for r in members] != [15, 25]:
            # Terminal reloads, repeated successes and live partial calls can legitimately lack the other goal.
            continue
        a,b = members
        pa,pb = run/a["raw_episode"], run/b["raw_episode"]
        same = {}
        for k in ("qpos", "qvel", "proprio", "previous_action", "rgb", "depth", "depth_valid"):
            x,y = (np.load(p/(k+".npy"), mmap_mode="r", allow_pickle=False) for p in (pa,pb))
            same[k] = bool(np.array_equal(x[0],y[0]))
        if not all(same.values()) or a["reset_sha256"]!=b["reset_sha256"]:
            raise ValueError(f"Instruction pair changed initial state or causal observations: {a['id']}, {b['id']}")
        xa,xb = (np.load(p/"executed_action_clipped.npy", mmap_mode="r") for p in (pa,pb))
        n = min(len(xa),len(xb))
        diff = np.abs(xa[:n] - xb[:n])
        paired.append(dict(partition=a["partition"], branch=a["branch"], scene=a["scene"], side=a["side"],
                           ids=[a["id"],b["id"]], same_reset_and_first_observations=True,
                           first_clipped_action_max_abs_diff=float(diff[0].max()),
                           common_decisions=n, common_time_mean_abs_action_diff=float(diff.mean(dtype=np.float64)),
                           success=[r["success"] for r in members], final_deg=[r["final_deg"] for r in members],
                           ratio_15_25=[r["angle_progress_ratio"] for r in members],
                           angle_difference_25_minus_15_deg=b["final_deg"]-a["final_deg"]))
    return paired


def matched_benefit(rows):
    matrix = defaultdict(dict)
    for r in rows:
        if r["branch"] in BRANCHES and r["mode"]=="pure":
            key = (r["partition"],r["scene"],r["side"],r["goal"])
            if r["branch"] in matrix[key]:
                # Success repeats can share all four keys. They are reported individually.
                if r["partition"].startswith("repeats/"):
                    continue
                raise ValueError(f"Duplicate branch/case pair {key}")
            matrix[key][r["branch"]]=r
    pairs = []
    for key,pair in sorted(matrix.items()):
        if set(pair)!=set(BRANCHES) or key[0].startswith("repeats/"):
            continue
        a,b = [pair[branch] for branch in BRANCHES]
        if a["reset_sha256"]!=b["reset_sha256"]:
            raise ValueError(f"Paired branches have different reset states at {key}")
        pairs.append(dict(partition=key[0], scene=key[1], scene_role=a["scene_role"], side=key[2], goal=key[3],
                          ids=[a["id"], b["id"]], complete=[a["success"], b["success"]],
                          event_counts=[len(a["events"]),len(b["events"])],
                          first_failures=[a["first_failure"], b["first_failure"]],
                          door_contact_steps=[a["door_contact_steps"], b["door_contact_steps"]],
                          bilateral_steps=[a["bilateral_steps"], b["bilateral_steps"]],
                          final_degrees=[a["final_deg"], b["final_deg"]],
                          angle_progress_ratios=[a["angle_progress_ratio"], b["angle_progress_ratio"]]))
    def compare(v):
        n=len(v)
        successes=[sum(int(r["complete"][i]) for r in v) for i in (0,1)]
        event_delta=[r["event_counts"][1]-r["event_counts"][0] for r in v]
        return dict(matched_cases=n, successes=successes, model_gain_percentage_points=100*(successes[1]-successes[0])/n,
                    ordered_event_totals=[sum(r["event_counts"][i] for r in v) for i in (0,1)],
                    model_event_wins=sum(d>0 for d in event_delta), model_event_ties=event_delta.count(0),
                    model_event_losses=sum(d<0 for d in event_delta),
                    door_contact_cases=[sum(r["door_contact_steps"][i]>0 for r in v) for i in (0,1)],
                    bilateral_cases=[sum(r["bilateral_steps"][i]>0 for r in v) for i in (0,1)])
    groups={}
    for partition in sorted({r["partition"] for r in pairs}):
        section=[r for r in pairs if r["partition"]==partition]
        groups[partition]=dict(all=compare(section))
        if partition=="formal":
            for label in sorted({r["scene_role"] for r in section}):
                groups[partition][label]=compare([r for r in section if r["scene_role"]==label])
    return groups,pairs


def training_comparison(run):
    paired={}
    for path in sorted(run.glob("round[1-6]")):
        stages={}
        for stage in ("bc","paired"):
            files=[path/b/stage/"receipt.json" for b in BRANCHES]
            if not all(p.is_file() for p in files):
                continue
            a,b=map(read,files)
            checks={key:a[key]==b[key] for key in ("membership_signature","sequence_sha256","retained_actor","actual_bc_rows")}
            if not all(checks.values()):
                raise ValueError(f"Branches differ in the registered BC pairing for {path.name}/{stage}: {checks}")
            stages[stage]=dict(matched=checks,bc_rows_per_branch=a["actual_bc_rows"],actor_updates_per_branch=a["retained_actor"],
                               parent_sha256_equal=a["parent_sha256"]==b["parent_sha256"],batch_order_sha256=a["sequence_sha256"],
                               retained_h32_actor_steps=[a["retained_h32_actor"],b["retained_h32_actor"]],
                               h32_imagined_queries=[a["h32_imagined_queries"],b["h32_imagined_queries"]],
                               new_label_pool_count=a["new_label_count"],old_label_pool_count=a["old_label_count"],
                               training_loop_wall_s=[a["training_wall_s"],b["training_wall_s"]],
                               model_to_supervised_training_loop_time_ratio=ratio(b["training_wall_s"],a["training_wall_s"]))
        paired[path.name]=stages
    return paired


def main(run, output, final=False):
    run,output=run.resolve(),output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for directory in stage_directories(run, final):
        selection=directory/"selection.json"
        selected={x["key"]: x for x in read(selection)} if selection.is_file() else {}
        for f in sorted(directory.glob("*/result.json")):
            rows.append(load_case(f,run,selected))
    if not rows:
        raise ValueError("No completed recorded student cases in the chosen run")
    bins=defaultdict(list)
    for r in rows:
        bins[(r["partition"],r["branch"],r["mode"])].append(r)
    partition={stage:dict() for stage in sorted({r["partition"] for r in rows})}
    for (stage,branch,mode),v in bins.items():
        partition[stage].setdefault(branch,{})[mode]=totals(v)
    formal={}
    for branch in BRANCHES:
        subset=[r for r in rows if r["partition"]=="formal" and r["branch"]==branch]
        if subset:
            if len({r["checkpoint_sha256"] for r in subset})!=1:
                raise ValueError("Formal cases for a branch use multiple checkpoint hashes")
            formal[branch]={k:totals([r for r in subset if r["scene_role"]==k])
                            for k in sorted({r["scene_role"] for r in subset})}
    matched,pairs=matched_benefit(rows)
    command=command_pairs(run,rows)
    costs={}
    for stage in partition:
        section=[r for r in rows if r["partition"]==stage]
        costs[stage]=dict(cases=len(section),physics_steps=sum(r["evaluated_physics_steps"] for r in section),
                          decisions=sum(r["decisions"] for r in section),
                          summed_episode_wall_s=sum(r["wall_s"] for r in section))
    audit=run/"teacher_audit"/"teacher_cases.json"
    if audit.exists():
        teachers=read(audit)
        for role in ("adapter", "blind_teacher_only"):
            part=[r for r in teachers if r["case_role"]==role]
            costs[role]=dict(cases=len(part), physics_steps=sum(r["physics_steps"] for r in part),
                             decisions=sum(r["teacher_decision_count"] for r in part),
                             summed_episode_wall_s=sum(r["wall_s"] for r in part),
                             complete_successes=sum(r["success"] for r in part))
        probes=[r["same_state_restore"] for r in teachers if r["same_state_restore"]]
        costs["teacher_restore_checks"]=dict(cases=len(probes),physics_steps=sum(r["extra_physics_steps"] for r in probes),
                                            decisions=len(probes))
    if (run/"restore_probes.json").is_file():
        probes=read(run/"restore_probes.json")
        costs["student_snapshot_reexecution"]=dict(cases=len(probes),physics_steps=sum(r["physical_substeps"] for r in probes),
                                                   decisions=len(probes))
    if final:
        freeze=read(run/"terminal_freeze.json")
        scenes={"tr_nominal", "va_pose", "te_combination", "te_mm02_combo_a", "te_mm02_combo_b"}
        expected={(s,side,goal) for s in scenes for side in ("pull","push") for goal in (15,25)}
        for branch in BRANCHES:
            cases=[r for r in rows if r["partition"]=="formal" and r["branch"]==branch]
            if (len(cases)!=20 or {(r["scene"],r["side"],r["goal"]) for r in cases}!=expected or
                    any(r["checkpoint_sha256"]!=freeze["branches"][branch]["deployment_sha256"] for r in cases)):
                raise ValueError(f"Incomplete or nonterminal formal suite for {branch}")
    result=dict(method="M1Piper-Multimodal-DAggerWM-v2",stage="frozen" if final else "pre_freeze",
                input_root=str(run), inferred_from_recorded_episodes=True,
                definitions={
                    "physics_steps":"actual native 2 ms integrator calls; control intervals can have a partial terminal step",
                    "goal_ratio":"(final hinge - start hinge)/(command - start hinge), degrees, no clipping",
                    "joint_error":"J1..J6 post-step measured angle against held physical servo target on that substep; normalize each RMSE by the full allowed joint range",
                    "door_contact":"independent judge's any door-robot contact above threshold; inspect bilateral_steps and unexpected_contact_steps separately",
                    "events":"[ordered judge event, absolute 2 ms step]; recovery reports newly reached events and subtracts inherited contact steps",
                    "recovery":"teacher-controlled continuation from a student snapshot; horizon completion describes 32 physical intervals; full-task denominator empty",
                    "eligible_bc_labels":"query-qualified labels independently of successor duration; labels_with_complete_successor counts their intersection with legal 20 ms intervals; fitting uses training partitions only",
                    "student_steps_with_distinct_qualified_expert":"student-executed decision whose qualified clipped expert target differs from the issued action by over 0.0001 normalized units on at least one channel",
                    "fresh_exposures":"recorded exposure at or after segment start; a recovery can carry its previous image",
                    "success_gain":"percentage-point difference in the same branch-paired frame0 test; order supervised_aggregate, model_trajectory",
                    "wall":"sum of actual per-case wall times in concurrently executing workers; excludes process start/some I/O and is not elapsed job time"},
                costs=costs, total_recorded_physics_steps=sum(x["physics_steps"] for x in costs.values()),
                partitions=partition, formal_by_scene_role=formal, matched_model_gain=matched,
                matched_training_by_round=training_comparison(run),
                case_index="aggregates_cases.jsonl",paired_goal_commands="aggregates_goal_pairs.jsonl",
                paired_branches="aggregates_paired_branches.jsonl")
    write(output/"aggregates_cases.jsonl",rows,lines=True)
    write(output/"aggregates_goal_pairs.jsonl",command,lines=True)
    write(output/"aggregates_paired_branches.jsonl",pairs,lines=True)
    write(output/"aggregates.json",result)
    print(json.dumps(dict(indexed_cases=len(rows),goal_pairs=len(command),matched_branch_pairs=len(pairs),
                          physics_steps=result["total_recorded_physics_steps"],partitions=list(partition))))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--final",action="store_true")
    args=parser.parse_args()
    main(args.run,args.output,args.final)
