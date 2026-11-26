"""Publish measured MM03 throughput without mixing optimizer cohorts and native task time."""
from pathlib import Path
import json

from scripts.multimodal.mm03_launch import read, write, now


SUBDIR = Path("performance/20261126-throughput")
FILES = ("baseline_1s.json", "two_seed_overlap_1s.json", "optimized_mixed_window.json",
         "frozen_actor_graph.json", "h7_backward.json", "h7_backward_verified.json",
         "dispatch_replay.json", "b_seed_cohort.json", "b_seed_cohort_r04.json",
         "cf_native_profile.json","native_scoring_comparison.json","cached_native_windows.json",
         "parallel_cf_handoff.json","parallel_cf_rates.json")


def stage_wall(receipt):
    journal=receipt.with_name("executions.jsonl")
    if journal.is_file():
        with journal.open() as stream:
            rows=[json.loads(line) for line in stream if line.endswith("\n")]
        for entry in reversed(rows):
            if entry["event"]=="ended" and entry["completed"]:
                return entry["time"]-entry["started"]
    return None


def summarize(root):
    src=root/SUBDIR
    cohort=read(src/"b_seed_cohort_r04.json").get("completed",{}).get("six_D23_H9")
    if not cohort:
        return None
    utilization={}
    for name in FILES[:3]:
        sample=read(src/name)
        if not sample:continue
        utilization[name]=dict(start=sample.get("begin",sample.get("start")),end=sample["end"],
            gpu_mean_percent=sample["global_gpu_pc_mean"],gpu_median_percent=sample["global_gpu_pc_median"],
            cores=sample["cores"],peak_used_MiB=sample["gpu_MiB_peak"],samples=len(sample["samples"]))
    inference=read(src/"frozen_actor_graph.json")
    h7=read(src/"h7_backward_verified.json")
    original=read(src/"native_scoring_comparison.json")
    cached=read(src/"cached_native_windows.json")
    inventory=read(root/"resources/native_models/index.json")
    timings=[]
    for f in sorted((root/"B/rounds").glob("r*/wm/seed*/receipt.json")):
        d=read(f)
        if d.get("graph_updates_last_run",0):
            predecessor=f.parents[3]/f"r{int(f.parents[2].name[1:])-1:02d}"/"wm"/f.parent.name/"receipt.json"
            prev=read(predecessor)
            timings.append(dict(round=f.parents[2].name,seed=f.parent.name,paid=d["paid"],
                retained=d["retained"],graph_updates=d["graph_updates_last_run"],check=d["h7_graph_check"],
                last_run_wall_s=d["wall_s_last_run"], previous_same_seed_wall_s=prev.get("wall_s_last_run"),
                full_stage_wall_s=stage_wall(f),previous_full_stage_wall_s=stage_wall(predecessor),
                extra_gradient_evaluations=d["extra_capture_gradient_evaluations_last_run"],source=str(f)))
    batches=[read(p) for p in (root/"B/native_batch_timings").glob("*.json")]
    shifted=[x for x in batches if x["predicted_cases"]>0]
    core=dict(as_of_beijing=now(),observed_cohort=dict(baseline_round=2,optimized_round=4,
              base_wall_s=cohort["previous_wall_s"],optimized_wall_s=cohort["current_wall_s"],
              throughput_ratio=cohort["ratio"],wall_reduction=cohort["elapsed_reduction"],
              paid=cohort["observed"]["paid"],overlap_s=cohort["observed"]["cross_seed_overlap_s"],
              scope="Three D23 and three H9 fits plus their shared WM. Includes launch, data and optimizer time. Full-task physical scoring has its own ledger."),
              graphics=utilization,frozen_task_actions=dict(
                cases=sum(d["decisions_compared"] for d in inference["rows"]),
                identical=inference["identical"],rows=inference["rows"]),
              h7_backward=dict(bench_loss_and_all_gradients_exact=h7.get("exact"),bench_eager_ms=h7.get("eager_ms"),
                  bench_graph_ms=h7.get("graph_ms"),bench_speedup=h7.get("speedup"),
                  qualified_production_stages=timings,
                  validation="Two actual eager warmup updates and a matching loss/all-gradient check at the first replay of each WM process. Sampling, clipping and the AdamW step retain their registered order."),
              native_dispatch=dict(measured_completed_reordered_batches=len(shifted),
                 counted_new_native_cases=sum(x["cases"] for x in shifted),worker_counts=sorted({x["workers"] for x in shifted}),
                 source=str(root/"B/native_batch_timings"),timing_replay="dispatch_replay.json"),
              native_short_forward=dict(warm_worker_speedup=original.get("cf",{}).get("speedup"),
                  matched_original_cases=[dict(mode=x["mode"],side=x["side"],goal=x["goal"],
                  events=len(x["events"]),native_substeps=x["physics_steps"]) for x in original.get("full_cases",[])],
                  cached_replay_steps=cached.get("diagnostic_native_substeps"),
                  compiled_geometries=inventory.get("unique_native_files"),compiled_bytes=inventory.get("total_bytes"),
                  case_configurations=len(inventory.get("models",{}))),
              native_cf_resources=read(root/"resources/worker_targets.json"),
              formal_results_source="physical_cases.jsonl",hardware_motion_commands=0)
    write(src/"summary.json",core)
    return core


def paragraph(data):
    c=data["observed_cohort"]
    g=data["graphics"]
    base=g["baseline_1s.json"]["gpu_mean_percent"]
    dual=g["two_seed_overlap_1s.json"]["gpu_mean_percent"]
    mixed=g["optimized_mixed_window.json"]["gpu_mean_percent"]
    return (f"三个种子的 D23 和 H9 共六条训练链完成相同更新预算，第 2 轮耗时 {c['base_wall_s']:.1f} 秒，"
            f"第 4 轮耗时 {c['optimized_wall_s']:.1f} 秒，训练阶段吞吐为原来的 {c['throughput_ratio']:.2f} 倍。"
            f"整卡 GPU 利用率在优化前的短窗口平均为 {base:.1f}%，双优化器重叠时为 {dual:.1f}%，"
            f"另一个包含物理采集的窗口为 {mixed:.1f}%。")

