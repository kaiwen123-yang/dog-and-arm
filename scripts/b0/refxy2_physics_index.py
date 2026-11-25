"""Summarize physical denominators, gates and the provenance of each same-episode V0."""
from collections import Counter
from scripts.b0.refxy2_physics import OUT, read, write


def summarize():
    root=OUT/"assessment"
    entries=[]
    totals=Counter()
    videos=[]
    for path in sorted(root.glob("*/package.json")):
        doc=read(path)
        counts=Counter()
        passes=Counter()
        free={}
        nominal=[]
        for row in doc["cases"]:
            kind=row["kind"]
            key=kind+"/"+row["backend"]
            counts[key]+=1
            passes[key]+=bool(row["passed"])
            if kind=="free":
                ref=free.setdefault(row["reference"],{"cases":0,"passed":0})
                ref["cases"]+=1
                ref["passed"]+=bool(row["passed"])
            elif kind=="contact" and row["backend"]=="warp" and row["passed"]:
                nominal.append(row["id"])
        group="extension_decision_repeat" if doc["repeat"] else ("process_500" if doc["local_update"]==500 else "formal")
        for key,n in counts.items():
            totals[(group,key)]+=n
        for v in sorted(path.parent.glob("*_full/*/full/nominal/video_manifest.json")):
            videos.append(str(v))
        entries.append(dict(package=path.parent.name,stage=group,method_id=doc["method_id"],
                            node=doc["local_update"],case_index=str(path),
                            counts=dict(counts),passed={k:passes[k] for k in counts},free_by_ref=free,
                            warp_passed_nominal=nominal,eligible_for_contact_D=(len(nominal)==10)))
    write(root/"physics_manifest.json",dict(packages=entries,registered_cases=sum(totals.values()),
          groups=[dict(stage=stage,kind_backend=kind,n=n) for (stage,kind),n in totals.items()],
          video_count=len(videos),same_episode_video_manifests=videos))
    print([(e["package"],e["passed"]) for e in entries],sum(totals.values()))


if __name__=="__main__":
    summarize()
