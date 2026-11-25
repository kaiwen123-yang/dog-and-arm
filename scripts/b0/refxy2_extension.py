"""Decide whether both registered RefXY2 branches extend, from original physics alone."""
import argparse
from scripts.b0.refxy2_physics import OUT, read, write

LABELS = ("measured_200", "shared_0", "zero_200")


def original_progress(series):
    measured, *controls = series
    get = lambda group, key: [r[key] for r in group]
    events = [get(group,"event_level") for group in series]
    complete = all(r["p95_mm"] is not None for group in series for r in group)
    event_gain = min(events[0]) > max(max(e) for e in events[1:])
    event_preserved = min(events[0]) >= max(max(e) for e in events[1:])
    preserved_station = all(r["approach_and_park"] for r in measured)
    if complete:
        p95 = [get(group,"p95_mm") for group in series]
        ready = [get(group,"ready_ticks") for group in series]
        count = [get(group,"position_ticks") for group in series]
        effects=[dict(comparator=label, p95_treatment_worst_minus_control_best_mm=max(p95[0])-min(group),
                      p95_treatment_best_minus_control_worst_mm=min(p95[0])-max(group))
                 for label,group in zip(LABELS[1:],p95[1:])]
        non_degraded = all(min(p95[0])<=max(p) for p in p95[1:])
        p95_gain = (all(max(p95[0])<min(p) for p in p95[1:]) and
                    min(ready[0])>=max(max(r) for r in ready[1:]) and
                    min(count[0])>=max(max(c) for c in count[1:]))
        ready_gain = min(ready[0])>max(max(r) for r in ready[1:]) and non_degraded
    else:
        p95_gain = ready_gain = non_degraded = False
        effects=[]
    # In a native case with the same reached event, compare each matching
    # control separately. Superior original events take precedence over P95.
    def native_preserves(control):
        if min(events[0])>max(r["event_level"] for r in control):
            return True
        if min(events[0])<max(r["event_level"] for r in control):
            return False
        if any(r["p95_mm"] is None for r in [*measured, *control]):
            return False
        return min(r["p95_mm"] for r in measured)<=max(r["p95_mm"] for r in control)
    return dict(approach_and_park=preserved_station,events_preserved=event_preserved,event_gain=event_gain,
                p95_gain=p95_gain,ready_gain=ready_gain,p95_non_degraded=non_degraded,effects=effects,
                warp_pass=preserved_station and event_preserved and (event_gain or p95_gain or ready_gain),
                native_pass=preserved_station and event_preserved and all(native_preserves(c) for c in controls))


def key(case):
    return case["id"].split("/",1)[1]


def decide(repeated):
    root=OUT/"assessment"
    labels=list(LABELS)
    docs={label:read(root/label/"package.json")["cases"] for label in labels}
    if repeated:
        docs.update({label+"_repeat":read(root/(label+"_repeat")/"package.json")["cases"] for label in labels})
    def point(row):
        w=row["windows"]
        fixed=w["fixed"]
        return dict(id=row["id"],events=row["events"],event_level=len(row["events"]),
                    approach_and_park=row["events"][:2]==["approach_base","settle"],fixed_ticks=w["fixed_available"],
                    p95_mm=fixed["p95_mm"] if fixed else None,p95_over_3mm=fixed["p95_over_3mm"] if fixed else None,
                    ready_ticks=w["original_longest_ready_ticks"],
                    position_ticks=fixed["position_ticks"] if fixed else None,
                    fixed_window_original_ready_ticks=fixed["longest_original_ready_ticks"] if fixed else None,
                    first_failure=row["first_failure"])
    tested={}
    for backend in ("warp","native"):
        for side in ("pull","push"):
            def extract(label):
                return point(next(r for r in docs[label] if r["kind"]=="full" and
                                  r["side"]==side and r["backend"]==backend))
            runs={label:[extract(label)] for label in labels}
            if repeated:
                for label in labels:
                    runs[label].append(extract(label+"_repeat"))
            result=original_progress(list(runs.values()))
            tested[f"{backend}/{side}"]=dict(measurements=runs,comparison=result)
    passed_sets = {label:{key(row) for row in docs[label] if row["kind"] in ("contact","free") and row["passed"]}
                   for label in labels}
    losses={other:sorted(passed_sets[other]-passed_sets["measured_200"]) for other in labels[1:]}
    # The archived u10000 passed none of these contact or free cases.
    # Report the zero-control gains separately; only inherited/shared qualifications are prior.
    bilateral_warp=all(tested["warp/"+s]["comparison"]["warp_pass"] for s in ("pull","push"))
    native_events=all(tested["native/"+s]["comparison"]["approach_and_park"] and
                      tested["native/"+s]["comparison"]["events_preserved"] for s in ("pull","push"))
    native_complete=all(tested["native/"+s]["comparison"]["native_pass"] for s in ("pull","push"))
    plausible=bool(bilateral_warp and native_events and not losses["shared_0"])
    extend=bool(plausible and native_complete) if repeated else None
    decision=dict(repeat_scored=repeated,case_counts={label:len(rows) for label,rows in docs.items()},
                  bilateral_warp=bilateral_warp,native_preserved_events=native_events,
                  native_preserved=native_complete,lost_original_nominal_or_free_cases_vs=losses,
                  request_reverse_repeats=plausible if not repeated else False,
                  extend=extend if repeated or plausible else False,
                  disposition=("extend" if extend else "close") if repeated or not plausible else "measure_reverse_repeats",
                  sides=tested)
    write(root/("extension_final.json" if repeated else "extension_first_pass.json"),decision)
    print(decision["disposition"])


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repeated",action="store_true")
    decide(p.parse_args().repeated)
