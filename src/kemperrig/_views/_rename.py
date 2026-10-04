"""Text view of what `rename` changed."""

from __future__ import annotations

from kemperrig.services.edit import Renamed


def render_rename(r: Renamed, *, old: str, new: str, out: str) -> str:
    lines = [f"renamed {r.rigs} rig(s)  {old!r} -> {new!r}"]
    if r.slots:
        lines.append(f"re-pointed {r.slots} performance slot(s)")
    lines.append(f"rewrote the name inside {r.rig_payloads} rig payload(s) and "
                 f"{r.slot_payloads} slot(s)")
    left = max(0, r.rigs - r.rig_payloads) + max(0, r.slots - r.slot_payloads)
    if left:
        lines.append(f"left {left} payload(s) as they were — their own name is not {old!r}, "
                     "or they do not parse; `doctor` lists them")
    lines.append(f"wrote {out}")
    lines.append("not confirmed to restore into Rig Manager — keep the original")
    return "\n".join(lines)
