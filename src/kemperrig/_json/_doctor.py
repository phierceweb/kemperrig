"""The `doctor` document."""

from __future__ import annotations

from dataclasses import asdict

from kemperrig.services.diff import digest
from kemperrig.services.doctor import Checkup, NameMismatch, SlotRef


def _slot(s: SlotRef) -> dict:
    return {"performance": s.performance, "slot": s.slot, "rig_name": s.rig_name}

def _renamed(m: NameMismatch) -> dict:
    where = ({"kind": "rig", "folder": m.rig.folder, "stored": m.rig.name} if m.rig
             else {"kind": "slot", **_slot(m.slot), "stored": m.slot.rig_name})
    return {**where, "payload": m.payload}

def doctor_doc(c: Checkup) -> dict:
    """`definite` holds what `--strict` fails on; `informational` the rest."""
    return {
        "defective": c.defective,
        "rigs": c.rigs, "performances": c.performances, "slots": c.slots, "cab_irs": c.cab_irs,
        "definite": {
            "dangling_slots": [_slot(s) for s in c.dangling],
            "ambiguous_slots": [{**_slot(a.slot),
                                 "rigs": [{"folder": r.folder, "name": r.name,
                                           "digest": digest(r.blob)} for r in a.rigs]}
                                for a in c.ambiguous],
            "broken_payloads": [asdict(b) for b in c.broken],
        },
        "informational": {
            "device_only_slots": (None if c.device_only is None
                                  else [_slot(s) for s in c.device_only]),
            "unread_payloads": [{"kind": u.kind, "name": u.name, "folder": u.folder,
                                 "tracks": [{"track": n, "unread": k, "bytes": size}
                                            for n, k, size in u.tracks]}
                                for u in c.unread],
            "gain_mismatches": [{"folder": g.rig.folder, "name": g.rig.name,
                                 "stored": g.rig.gain, "decoded": round(g.decoded, 4)}
                                for g in c.gain_mismatches],
            "name_mismatches": [_renamed(m) for m in c.name_mismatches],
            "unused_cab_irs": [{"folder": p.folder, "name": p.name} for p in c.unused_cab_irs],
        },
    }
