"""Text views comparing libraries: a diff of two, and history across snapshots."""

from __future__ import annotations

from kemperrig.services.diff import Diff
from kemperrig.services.history import History, RigHistory, Step


def render_diff(rigs: Diff, performances: Diff, presets: Diff) -> str:
    """What changed between two backups, section by section; silent sections are omitted."""
    out: list[str] = []
    for label, d in (("rigs", rigs), ("performances", performances), ("presets", presets)):
        if d.empty:
            continue
        out.append(f"{label}: +{len(d.added)} -{len(d.removed)} ~{len(d.changed)}")
        out += [f"  + {k}" for k in d.added]
        out += [f"  - {k}" for k in d.removed]
        for c in d.changed:
            out.append(f"  ~ {c.key}")
            for f in c.changes:
                out.append(f"      {f.field}: {f.before!r} -> {f.after!r}")
    return "\n".join(out) if out else "identical — no rig, performance or preset differences"


_SHORT = {"rigs": "rigs", "performances": "perfs", "presets": "presets"}


def _change(step: Step | None) -> str:
    if step is None:
        return ""
    parts = []
    for kind, c in step.counts.items():
        marks = " ".join(f"{sign}{n}" for sign, n in
                         (("+", c.added), ("-", c.removed), ("~", c.changed)) if n)
        if marks:
            parts.append(f"{_SHORT[kind]} {marks}")
    return " · ".join(parts) or "unchanged"


def _by_device(rows: list[tuple[str | None, str]]) -> list[str]:
    """Rows under a heading per run of one device, when more than one device is present."""
    many = len({device for device, _ in rows}) > 1
    out, current = [], object()
    for device, line in rows:
        if many and device != current:
            current = device
            out.append(f"device {device}" if device is not None else "other files")
        out.append(line)
    return out


def _rig_history(r: RigHistory, files: int) -> list[str]:
    if not r.sightings:
        return [f"rig {r.name!r}: in none of {files} files"]
    k = len(r.versions)
    lines = [f"rig {r.name!r}: in {len(r.sightings)} of {files} files · "
             f"{k} version{'' if k == 1 else 's'} · first {r.first.label} · "
             f"last {r.last.label}"]
    for n, v in enumerate(r.versions, 1):
        lines.append(f"  v{n}  {v.digest or '(no payload)':12}  {v.count} file(s)  "
                     f"{v.first.label} → {v.last.label}")
    return lines + _by_device([
        (s.source.device, f"  {s.source.label:19}  " + ", ".join(f"v{n}" for n in s.versions)
         + ("  changed" if s.changed else "")) for s in r.sightings])


def render_history(h: History) -> str:
    """The timeline, or with a rig, where that rig appears and where its payload changed."""
    skipped = f", {len(h.skipped)} skipped" if h.skipped else ""
    lines = [f"history: {len(h.entries)} files by {h.order}{skipped} · each compared with the "
             "previous file from its device"]
    if h.rig is not None:
        return "\n".join(lines + _rig_history(h.rig, len(h.entries)))
    lines.append(f"  {'file':19}  {'rigs':>5} {'perfs':>5} {'presets':>7}  change")
    return "\n".join(lines + _by_device([
        (e.source.device, f"  {e.source.label:19}  {e.totals['rigs']:>5} "
         f"{e.totals['performances']:>5} {e.totals['presets']:>7}  "
         f"{'empty — not compared' if e.empty else _change(e.step)}".rstrip())
        for e in h.entries]))
