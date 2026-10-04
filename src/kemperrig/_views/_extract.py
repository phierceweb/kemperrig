"""Text view of what ``extract`` wrote and skipped."""

from __future__ import annotations

from kemperrig.services.extract import Planned
from kemperrig.services.select import Selection

from ._library import unchecked_lines


def render_extract(planned: list[Planned], *, out: str,
                   selection: Selection | None = None) -> str:
    tail = unchecked_lines(selection) if selection is not None else []
    if not planned:
        return "\n".join(["no rig matched — nothing written", *tail])
    written = [p for p in planned if p.file]
    skipped = [p for p in planned if not p.file]
    lines = [f"wrote {len(written)} .krig file(s) to {out}"]
    lines += [f"  {p.file}  <-  {p.rig.path}" for p in written]
    if skipped:
        lines.append(f"skipped {len(skipped)}:")
        lines += [f"  {p.rig.path}  ({p.skipped})" for p in skipped]
    return "\n".join(lines + tail)
