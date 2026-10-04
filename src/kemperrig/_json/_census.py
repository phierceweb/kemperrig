"""The library census `summary --write-golden` writes."""

from __future__ import annotations

import json

from kemperrig.services.census import Census

from ._library import summary_doc


CENSUS_FORMAT = 1

_CENSUS_COMMENT = (
    "Library census written by `kemperrig summary --write-golden`. tests/test_golden.py in "
    "kemperrig asserts the library still matches it when KEMPERRIG_GOLDEN points here and "
    "KEMPERRIG_LIBRARY at the library. It names rigs and counts from a private library: keep "
    "it out of public repositories, and regenerate it when the library changes.")

def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)

def census_doc(c: Census) -> dict:
    """The census as written: `summary`'s totals and gain block, then the decode anchors."""
    s = summary_doc(c.report, info_user=c.user)
    k = c.checkup
    return {
        "_comment": _CENSUS_COMMENT, "census": CENSUS_FORMAT, "user": s["user"],
        "totals": {"rigs": s["rigs"], "di": s["di"], "studio": s["studio"],
                   "performances": s["performances"], "slots": k.slots,
                   "presets": c.presets, "cab_irs": k.cab_irs,
                   "amp_models": len(s["amp_models"]), "authors": len(s["authors"])},
        "gain": {**{key: _rounded(s["gain"][key]) for key in ("min", "max", "mean")},
                 "bands": s["gain"]["bands"],
                 "decoded": c.gain_decoded, "undecoded": s["rigs"] - c.gain_decoded},
        "profile_types": {"none" if t is None else t:
                          {"rigs": p.rigs, "gain_decoded": p.gain_decoded}
                          | ({} if p.folders is None else {"folders": p.folders})
                          for t, p in c.profile_types.items()},
        "effects": c.effects,
        "effects_undecoded": c.effects_undecoded,
        "doctor": {"dangling_slots": len(k.dangling), "ambiguous_slots": len(k.ambiguous),
                   "broken_payloads": len(k.broken), "unread_payloads": len(k.unread),
                   "gain_mismatches": len(k.gain_mismatches),
                   "name_mismatches": len(k.name_mismatches),
                   "unused_cab_irs": len(k.unused_cab_irs)},
        "rig": c.rig and {
            "name": c.rig.rig.name, "folder": c.rig.rig.folder, "gain": c.rig.rig.gain,
            "amp_gain": _rounded(c.rig.amp_gain), "first_strings": c.rig.first_strings,
            "effects": c.rig.effects},
        "performance": c.performance and {
            "name": c.performance.performance.name,
            "slots": len(c.performance.performance.slots), "tracks": c.performance.tracks,
            "effects_locked": [c.performance.locked, c.performance.compared],
            "effects_locked_ratio": _rounded(c.performance.ratio),
            "cab_ir": c.performance.cab_ir, "gain_ladder": c.performance.gain_ladder},
    }

def census_text(c: Census) -> str:
    """`census_doc` as the census file holds it: sorted keys, so two runs diff cleanly."""
    return json.dumps(census_doc(c), indent=2, sort_keys=True, ensure_ascii=False,
                      allow_nan=False) + "\n"
