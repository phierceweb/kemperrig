"""Select rigs by metadata and by what their payloads decode to — an effect, a cab IR.

A rig the decode cannot judge is reported, never silently dropped: one whose payload does
not parse, and one that misses `effect` only because a slot of it is undecoded."""

from __future__ import annotations

from dataclasses import dataclass

from kemperrig.model import Rig
from kemperrig.services.decode import RigDetail, try_rig_detail
from kemperrig.services.filter import contains, filter_rigs


@dataclass(frozen=True)
class Selection:
    rigs: list[Rig]
    unparsed: list[Rig]     # a decode filter could not judge them: the payload does not parse
    undecoded: list[Rig]    # missed `effect`, but a slot of theirs is undecoded
    decoded: bool           # a decode filter ran
    details: list[RigDetail | None] | None = None   # per rig in `rigs`, when asked for


def _has_effect(detail: RigDetail, text: str) -> bool:
    return any(e.decoded and (contains(e.type_name, text) or contains(e.category, text))
               for e in detail.effects)


def select_rigs(rigs: list[Rig], *, effect: str | None = None, ir: str | None = None,
                decode: bool = False, **metadata) -> Selection:
    """`filter_rigs(rigs, **metadata)`, then — when `effect` or `ir` is given — rigs with a
    decoded effect whose type name or category contains `effect`, and whose cab IR contains
    `ir`. Matches are case-insensitive substrings; an effect matches whether on or off.
    `decode` also returns each selected rig's detail (None where the payload does not parse)."""
    picked = filter_rigs(rigs, **metadata)
    if effect is None and ir is None:
        details = [try_rig_detail(r) for r in picked] if decode else None
        return Selection(picked, [], [], decoded=False, details=details)
    matched, kept, unparsed, undecoded = [], [], [], []
    for rig in picked:
        detail = try_rig_detail(rig)
        if detail is None:
            unparsed.append(rig)
            continue
        if ir is not None and not contains(detail.cab_ir, ir):
            continue
        if effect is None or _has_effect(detail, effect):
            matched.append(rig)
            kept.append(detail)
        elif any(not e.decoded for e in detail.effects):
            undecoded.append(rig)
    return Selection(matched, unparsed, undecoded, decoded=True,
                     details=kept if decode else None)
