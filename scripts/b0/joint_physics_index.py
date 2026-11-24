"""Summarize the registered first-action, boundary and pure Actor evidence."""
import argparse

from scripts.b0.joint_physics_audit import OUT,read,write
from scripts.b0.score_temporal_wm import csv_file


def main(node):
    rows=[]; total=dict(branches=0,physics_microsteps=0,new_prefix_microsteps=0,eligible_train_h1=0,eligible_train_h7=0)
    boundary=[]
    for identity in ("formal_2ms","training"):
        for repeat in (0,1):
            run=read(OUT/f"boundary_{identity}_r{repeat}.json")
            total["branches"]+=run["branches"]
            total["physics_microsteps"]+=run["microsteps"]
            total["eligible_train_h1"]+=run["training_h1"]
            boundary.extend(run["rows"])
            loops=read(OUT/f"closedloop_{node}_{identity}_r{repeat}.json")
            rows.extend(loops["rows"])
    costs={}
    for identity in ("formal_2ms","training"):
        subset=[r for r in rows if r["identity"]==identity]
        costs[identity]=dict(runs=len(subset),trajectories=2,registration_starts=6,actor_calls=sum(r["actor_queries"] for r in subset),
            prefix_microsteps=sum(r["recomputed_prefix_ticks"] for r in subset),integrated_microsteps=sum(r["integrated_policy_ticks"] for r in subset),
            observed_microsteps=sum(r["scored_ticks"] for r in subset),physically_accepted_first20=sum(r["first_20ms_survived"] for r in subset),
            second_queries=sum(r["second_actor_queried"] for r in subset),any_dual=sum(bool(r["both_ticks"]) for r in subset),
            phase_events=sum(len(r["events"]) for r in subset),segment_passes=sum(r["passed"] for r in subset))
    for r in rows:
        r["stop_reason"]=(r["first_failure"] or {}).get("reason")
        r["judge_observed_end_s"]=(r["first_failure"] or {}).get("interval_end_s")
    csv_file(OUT/f"pure_actor_{node}_cases.csv",rows)
    csv_file(OUT/"boundary_cases.csv",boundary)
    servo=read(OUT/"raw_audit.json")
    grip=[r for r in servo["hold"] if r["node"] in ("shared_u0","experiment_u10")]
    write(OUT/f"physics_summary_{node}.json",dict(node=node,first20_archive_branches=servo["branches"],first20_archive_microsteps=servo["raw_solve_ticks"],
        reconstructed_force_max_error=servo["max_abs_force_error"],boundary_budget=total,
        budget_note="All 112 restored-start branches complete exactly one 20ms interval. Their 200 ms historical prefixes are reused from the original two physical identities. Recomputed closed-loop prefixes and post-judge integration ticks appear in the separate closed-loop budget.",
        coupled_boundary_train_terminal_h1=sum(r["train_h1"] and r["training_terminal_tick"]>0 for r in boundary),
        hold_servo_by_node=grip,closed_loop=costs,endpoint_direction=read(OUT/"derivative_summary.json"),
        videos=read(OUT/("videos_"+node+".json"))))
    print(total,costs)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--node",default="shared_u0")
    main(p.parse_args().node)
