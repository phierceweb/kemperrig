"""Text view of `doctor`: definite findings first, then the informational ones."""

from __future__ import annotations

from kemperrig.records import library_path
from kemperrig.services.diff import digest
from kemperrig.services.doctor import AmbiguousSlot, Checkup, NameMismatch, SlotRef


_SHOWN = 20


def _slot(s: SlotRef) -> str:
    return f"{s.performance} · slot {s.slot} · {s.rig_name!r}"


def _section(title: str, rows: list[str], why: str = "", *,
             total: int | None = None) -> list[str]:
    count = len(rows) if total is None else f"{len(rows)} of {total}"
    lines = [f"  {title}: {count}" + (f"  ({why})" if why else "")]
    lines += [f"    {r}" for r in rows[:_SHOWN]]
    if len(rows) > _SHOWN:
        lines.append(f"    … and {len(rows) - _SHOWN} more (--json lists all)")
    return lines


def _ambiguous(a: AmbiguousSlot) -> str:
    return f"{_slot(a.slot)} — " + ", ".join(
        f"{r.folder or '(no folder)'} {digest(r.blob) or '(empty)'}" for r in a.rigs)


def _renamed(m: NameMismatch) -> str:
    where = f"rig {m.rig.path}" if m.rig else f"slot {_slot(m.slot)}"
    return f"{where} — the payload says {m.payload!r}"


def render_doctor(c: Checkup) -> str:
    """Definite findings are what `--strict` fails on; the rest are for a person to judge."""
    lines = [f"doctor: {c.rigs} rigs · {c.performances} performances, {c.slots} slots · "
             f"{c.cab_irs} cab IRs", "definite (--strict exits 1 on any)"]
    lines += _section("dangling slots", [_slot(s) for s in c.dangling],
                      "no library rig has the name")
    lines += _section("ambiguous slots", [_ambiguous(a) for a in c.ambiguous],
                      "rigs with different payloads share the name")
    lines += _section("broken payloads", [
        f"{b.kind} {library_path(b.folder, b.name)} — {b.problem}" for b in c.broken])
    lines.append("informational")
    if c.device_only is not None:
        lines += _section("on the device only", [_slot(s) for s in c.device_only],
                          "dangling here, but the device backup holds the rig")
    lines += _section("payloads with bytes nothing reads", [
        f"{u.kind} {library_path(u.folder, u.name)} — "
        + ", ".join(f"track {n}: {k} of {size} bytes" for n, k, size in u.tracks)
        for u in c.unread], "damage, or an encoding not decoded")
    lines += _section("amp gain differs from the payload", [
        f"{g.rig.path} — stored {g.rig.gain:.1f}, decoded {g.decoded:.1f}"
        for g in c.gain_mismatches])
    lines += _section("name differs from the payload", [_renamed(m) for m in c.name_mismatches])
    lines += _section("unused cab IRs", [p.path for p in c.unused_cab_irs],
                      "no rig or slot loads them", total=c.cab_irs)
    return "\n".join(lines)
