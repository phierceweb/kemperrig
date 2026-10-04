"""The `extract` document."""

from __future__ import annotations

from kemperrig.services.diff import digest
from kemperrig.services.extract import Planned
from kemperrig.services.select import Selection

from ._library import unchecked_doc


def extract_doc(planned: list[Planned], *, out: str, selection: Selection | None = None) -> dict:
    written = [p for p in planned if p.file]
    skipped = [p for p in planned if not p.file]
    unchecked = ({"unchecked": unchecked_doc(selection)}
                 if selection is not None and selection.decoded else {})
    return {"out": out, "count": {"written": len(written), "skipped": len(skipped)},
            "written": [{"folder": p.rig.folder, "name": p.rig.name, "file": p.file,
                         "digest": digest(p.rig.blob)} for p in written],
            "skipped": [{"folder": p.rig.folder, "name": p.rig.name, "reason": p.skipped}
                        for p in skipped]} | unchecked
