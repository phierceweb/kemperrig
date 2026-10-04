"""Text view of a rig or preset pack, and where its items stand against a library."""

from __future__ import annotations

import re

from kemperrig.model import Pack
from kemperrig.records import library_path
from kemperrig.services.pack import IN_LIBRARY, NAME_TAKEN, Placement, counts

from ._library import _rig_line

_STAMP = re.compile(r"(\d{4})(\d{2})(\d{2})\d{6}")


def _released(stamp: str | None) -> str | None:
    m = _STAMP.fullmatch(stamp or "")
    return f"{m[1]}-{m[2]}-{m[3]}" if m else stamp


def _status(p: Placement) -> str:
    places = ", ".join(library_path(f, n) for f, n in p.where)
    if p.status == IN_LIBRARY:
        return f"in library: {places}"
    if p.status == NAME_TAKEN:
        return f"name taken: {places} (different payload)"
    return "new"


def render_pack(pack: Pack, placed: list[Placement] | None = None, *,
                against: str | None = None) -> str:
    items = pack.rigs if pack.content == "rigs" else pack.presets
    head = " · ".join(b for b in (f"{pack.name} — {pack.author}" if pack.author else pack.name,
                                  pack.released and f"released {_released(pack.released)}",
                                  pack.copyright,
                                  f"{len(items)} {pack.content}") if b)
    lines = [head]
    if placed is not None:
        c = counts(placed)
        lines.append(f"  against {against}: in library {c['in_library']} · new {c['new']} · "
                     f"name taken {c['name_taken']}")
    for i, item in enumerate(items):
        line = _rig_line(item, folder=False) if pack.content == "rigs" else f"  {item.name[:34]:34s}"
        lines.append(line + (f"  {_status(placed[i])}" if placed is not None else ""))
    return "\n".join(lines)
