"""Documents for `diff` and `history`."""

from __future__ import annotations

from dataclasses import asdict

from kemperrig.services.diff import Diff
from kemperrig.services.history import History, Source


def _diff(d: Diff) -> dict:
    return {"added": d.added, "removed": d.removed,
            "changed": [{"key": c.key,
                         "changes": [{"field": f.field, "before": f.before, "after": f.after}
                                     for f in c.changes]}
                        for c in d.changed]}

def diff_doc(rigs: Diff, performances: Diff, presets: Diff) -> dict:
    return {"identical": rigs.empty and performances.empty and presets.empty,
            "rigs": _diff(rigs), "performances": _diff(performances),
            "presets": _diff(presets)}

def _source(s: Source) -> dict:
    return {"path": s.path, "label": s.label, "device": s.device}

def history_doc(h: History) -> dict:
    doc: dict = {"order": h.order, "files": len(h.entries),
                 "skipped": [{"path": p, "reason": r} for p, r in h.skipped]}
    if h.rig is not None:
        doc["rig"] = {
            "name": h.rig.name,
            "first": h.rig.first and _source(h.rig.first),
            "last": h.rig.last and _source(h.rig.last),
            "versions": [{"version": n, "digest": v.digest, "files": v.count,
                          "first": _source(v.first), "last": _source(v.last)}
                         for n, v in enumerate(h.rig.versions, 1)],
            "sightings": [{**_source(s.source), "versions": s.versions, "changed": s.changed}
                          for s in h.rig.sightings]}
        return doc
    doc["timeline"] = [
        {**_source(e.source), **e.totals, "empty": e.empty,
         "since": None if e.step is None else
         {**_source(e.step.since), **{k: asdict(c) for k, c in e.step.counts.items()}}}
        for e in h.entries]
    return doc
