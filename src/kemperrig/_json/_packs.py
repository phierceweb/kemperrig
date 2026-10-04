"""The `pack` document."""

from __future__ import annotations

from kemperrig.model import Pack
from kemperrig.services.diff import digest
from kemperrig.services.pack import Placement, counts

from ._library import _preset, _rig


def pack_doc(pack: Pack, placed: list[Placement] | None = None, *,
             against: str | None = None) -> dict:
    """Each item carries `status` and the `library` records behind it only when placed."""
    items = [(_rig(r) if pack.content == "rigs" else _preset(r)) | {"digest": digest(r.blob)}
             for r in (pack.rigs if pack.content == "rigs" else pack.presets)]
    for item, p in zip(items, placed or [], strict=placed is not None):
        item["status"] = p.status
        item["library"] = [{"folder": f, "name": n} for f, n in p.where]
    return {"pack": {"name": pack.name, "author": pack.author, "copyright": pack.copyright,
                     "released": pack.released, "content": pack.content},
            "against": against, "counts": None if placed is None else counts(placed),
            "count": len(items), pack.content: items}
