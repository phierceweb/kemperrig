"""Where a pack's rigs or presets stand against a library: already in it, new, or sharing a
name with something different.

A pack payload is the rig or preset as Rig Manager stores it, so "already in it" means the
same payload bytes, whatever the library calls it now.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from kemperrig.model import Backup, Pack, Preset, Rig

IN_LIBRARY = "in_library"
NEW = "new"
NAME_TAKEN = "name_taken"
STATUSES = (IN_LIBRARY, NEW, NAME_TAKEN)


@dataclass(frozen=True)
class Placement:
    """One pack item's standing, and the library records (folder, name) that decided it —
    the same payload for IN_LIBRARY, the same name for NAME_TAKEN."""
    status: str
    where: list[tuple[str, str]] = field(default_factory=list)


def placements(pack: Pack, library: Backup) -> list[Placement]:
    """One Placement per pack rig — or preset, for a preset pack — in pack order."""
    if pack.content == "presets":
        return _place(pack.presets, library.presets)
    return _place(pack.rigs, library.rigs)


def counts(placed: list[Placement]) -> dict[str, int]:
    return {s: sum(p.status == s for p in placed) for s in STATUSES}


def _place(items: list[Rig] | list[Preset],
           library: list[Rig] | list[Preset]) -> list[Placement]:
    by_payload: dict[bytes, list[tuple[str, str]]] = {}
    by_name: dict[str, list[tuple[str, str]]] = {}
    for r in library:
        if r.blob:
            by_payload.setdefault(hashlib.sha256(r.blob).digest(), []).append((r.folder, r.name))
        by_name.setdefault(r.name, []).append((r.folder, r.name))
    out = []
    for item in items:
        same = by_payload.get(hashlib.sha256(item.blob).digest()) if item.blob else None
        if same:
            out.append(Placement(IN_LIBRARY, same))
        elif item.name in by_name:
            out.append(Placement(NAME_TAKEN, by_name[item.name]))
        else:
            out.append(Placement(NEW))
    return out
