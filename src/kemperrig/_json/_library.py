"""Documents for the read commands over one library: summary, rigs, presets, performances."""

from __future__ import annotations

from dataclasses import asdict

from kemperrig.model import Performance, Preset, Rig
from kemperrig.services.decode import RigDetail
from kemperrig.services.diff import digest
from kemperrig.services.performance import gain_ladder, locked_ratio
from kemperrig.services.report import LibraryReport
from kemperrig.services.select import Selection


def _rig(r: Rig) -> dict:
    d = {k: v for k, v in asdict(r).items() if k != "blob"}
    d["is_di"] = r.is_di
    d["is_boosted"] = r.is_boosted
    d["digest"] = digest(r.blob)
    return d


def decode_doc(d: RigDetail) -> dict:
    return {"amp_gain": d.amp_gain, "cab_ir": d.cab_ir,
            "effects": [asdict(e) for e in d.effects], "strings": d.strings}


def rig_doc(d: RigDetail) -> dict:
    return _rig(d.rig) | {"decode": decode_doc(d)}

def _performance(p: Performance) -> dict:
    return {"name": p.name, "tempo": p.tempo,
            "slots": [{k: v for k, v in asdict(s).items()} for s in p.slots]}

def _preset(p: Preset) -> dict:
    d = {k: v for k, v in asdict(p).items() if k != "blob"}
    d["is_cab_ir"] = p.is_cab_ir
    return d

def summary_doc(report: LibraryReport, *, info_user: str | None = None) -> dict:
    return {"user": info_user,
            "rigs": report.total_rigs, "di": report.di_count, "studio": report.studio_count,
            "performances": report.performance_count,
            "gain": {"min": report.gain_min, "max": report.gain_max,
                     "mean": report.gain_mean,
                     "bands": {str(k): v for k, v in sorted(report.gain_bands.items())}},
            "amp_models": [{"name": n, "count": c} for n, c in report.amp_models],
            "authors": [{"name": n, "count": c} for n, c in report.authors]}

def rigs_doc(rigs: list[Rig], *, selection: Selection | None = None) -> dict:
    """With details, each rig carries `decode` and `unparsed` lists the null ones; after a
    decode filter, `unchecked` lists the rigs it could not judge."""
    entries = [_rig(r) for r in rigs]
    doc: dict = {"count": len(rigs), "rigs": entries}
    if selection is not None and selection.details is not None:
        for entry, d in zip(entries, selection.details, strict=True):
            entry["decode"] = None if d is None else decode_doc(d)
        doc["unparsed"] = [r.path for r, d in zip(rigs, selection.details, strict=True)
                          if d is None]
    if selection is not None and selection.decoded:
        doc["unchecked"] = unchecked_doc(selection)
    return doc


def unchecked_doc(s: Selection) -> dict:
    """The rigs a decode filter could not judge, by path."""
    return {"unparsed": [r.path for r in s.unparsed], "undecoded": [r.path for r in s.undecoded]}

def performances_doc(performances: list[Performance], gain_index: dict) -> dict:
    return {"count": len(performances),
            "performances": [{**_performance(p),
                              "gain_ladder": gain_ladder(p, gain_index),
                              "locked_ratio": locked_ratio(p)}
                             for p in performances]}

def presets_doc(presets: list[Preset]) -> dict:
    return {"count": len(presets), "presets": [_preset(p) for p in presets]}
