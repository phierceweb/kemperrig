"""Text views of the library's contents: summary, rigs, one rig, presets, performances."""

from __future__ import annotations

from collections import Counter

from kemperrig.model import Performance, Preset, Rig
from kemperrig.services.decode import RigDetail
from kemperrig.services.performance import gain_ladder, locked_ratio
from kemperrig.services.report import LibraryReport
from kemperrig.services.select import Selection


def _effect_label(e) -> str:
    if not e.decoded:
        return f"{e.slot}=?"
    name = e.type_name or f"type {e.type_value}"
    state = "" if e.on is None else (" on" if e.on else " off")
    return f"{e.slot}={name}{state}"


def _raw_profile_columns(rig: Rig) -> list[str]:
    profile = f"profile type {rig.profile_type}" if rig.profile_type else ""
    if profile and rig.profile_revision:
        profile += f" rev {rig.profile_revision}"
    cab = [f"{label} {v}" for label, v in (("cabinet type", rig.cabinet_type),
                                           ("cabinet config", rig.cabinet_configuration))
           if v and v != "N/A"]
    return [profile, *cab] if profile else cab


def render_rig(detail: RigDetail) -> str:
    """One rig in detail: metadata + what its blob decodes to (incl. a loaded cab IR)."""
    rig = detail.rig
    gain = f"{rig.gain:.1f}" if rig.gain is not None else "-"
    kind = "DI" if rig.is_di else "studio"
    lines = [f"{rig.name}  —  {rig.amp_model or '?'}  g={gain}  {kind}  {rig.folder}"]
    if detail.amp_gain is not None:
        lines.append(f"  amp gain (decoded): {detail.amp_gain:.1f}")
    if rig.author:
        lines.append(f"  author: {rig.author}")
    amp_bits = [b for b in (rig.source_amp, rig.amp_name, rig.amp_channel,
                            rig.amp_model_year, rig.amp_location) if b and b != "N/A"]
    if amp_bits:
        lines.append("  amp: " + " · ".join(amp_bits))
    drive = "boosted" if rig.is_boosted else "unboosted" if rig.is_boosted is False else "?"
    if rig.amp_comment:
        lines.append(f"  drive: {drive}  ({rig.amp_comment})")
    if rig.amp_pickup and rig.amp_pickup != "N/A":
        lines.append(f"  profiled with: {rig.amp_pickup} pickup")
    raw = _raw_profile_columns(rig)
    if raw:
        lines.append("  " + " · ".join(raw))
    if detail.effects:
        lines.append("  effects: " + " · ".join(_effect_label(e) for e in detail.effects))
    if detail.cab_ir:
        lines.append(f"  cab IR: {detail.cab_ir}")
    if detail.strings:
        lines.append("  decoded strings: " + " · ".join(detail.strings))
    return "\n".join(lines)


def render_summary(report: LibraryReport, *, info_user: str | None = None) -> str:
    r = report
    lines = [f"Kemper library{f' — {info_user}' if info_user else ''}"]
    di_pct = (100 * r.di_count / r.total_rigs) if r.total_rigs else 0
    lines.append(f"  rigs: {r.total_rigs}   DI: {r.di_count} ({di_pct:.0f}%)   "
                 f"studio: {r.studio_count}   performances: {r.performance_count}")
    if r.gain_mean is not None:
        lines.append(f"  gain: min {r.gain_min:.1f}  max {r.gain_max:.1f}  mean {r.gain_mean:.2f}")
        bands = "  ".join(f"{b}.x:{c}" for b, c in r.gain_bands.items())
        lines.append(f"  gain bands: {bands}")
    lines.append(f"  amp models: {len(r.amp_models)}")
    for model, count in r.amp_models[:12]:
        lines.append(f"    {count:4d}  {model}")
    lines.append("  authors:")
    for author, count in r.authors[:8]:
        lines.append(f"    {count:4d}  {author}")
    return "\n".join(lines)


def _rig_line(rig: Rig, *, folder: bool = True) -> str:
    gain = f"{rig.gain:.1f}" if rig.gain is not None else " - "
    kind = "DI " if rig.is_di else "STU"
    line = f"  {rig.name[:34]:34s}  g={gain:>4}  {kind}  {(rig.amp_model or '')[:22]:22s}"
    return f"{line}  {rig.folder}" if folder else line


def _decode_line(d: RigDetail | None) -> str:
    if d is None:
        return "      payload does not parse"
    line = "      effects: " + (" · ".join(_effect_label(e) for e in d.effects) or "none")
    return f"{line}  ·  cab IR: {d.cab_ir}" if d.cab_ir else line


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} rig {one}" if n == 1 else f"{n} rigs {many}"


def unchecked_lines(s: Selection) -> list[str]:
    """One count line per kind of rig a decode filter could not judge."""
    lines = []
    if s.unparsed:
        lines.append(_plural(len(s.unparsed), "not checked: its payload does not parse",
                             "not checked: their payloads do not parse"))
    if s.undecoded:
        lines.append(_plural(len(s.undecoded), "not ruled out: it has an undecoded effect slot",
                             "not ruled out: they have an undecoded effect slot"))
    return lines


def render_rigs(rigs: list[Rig], *, title: str = "rigs", selection: Selection | None = None) -> str:
    details = selection.details if selection is not None else None
    rows = list(zip(rigs, details if details is not None else [None] * len(rigs), strict=True))
    body = []
    for rig, detail in sorted(rows, key=lambda rd: (-(rd[0].gain or 0.0), rd[0].name)):
        body.append(_rig_line(rig))
        if details is not None:
            body.append(_decode_line(detail))
    tail = unchecked_lines(selection) if selection is not None else []
    return "\n".join([f"{title}: {len(rigs)}", *body, *tail])


def render_presets(presets: list[Preset]) -> str:
    cabs = [p for p in presets if p.is_cab_ir]
    effects = [p for p in presets if p.preset_type]
    other = len(presets) - len(cabs) - len(effects)
    lines = [f"presets: {len(presets)}  (cab-IR {len(cabs)} · effects {len(effects)} · other {other})"]
    by_type = Counter(p.preset_type for p in effects)
    if by_type:
        lines.append("  effect presets by type:")
        for t, n in by_type.most_common():
            lines.append(f"    {n:4d}  {t}")
    cab_folders = Counter(p.folder for p in cabs)
    if cab_folders:
        lines.append(f"  cab-IR presets by folder ({len(cabs)}):")
        for f, n in cab_folders.most_common(12):
            lines.append(f"    {n:4d}  {f}")
    return "\n".join(lines)


def render_performances(perfs: list[Performance],
                        gain_index: dict[str, float | None] | None = None) -> str:
    lines = [f"performances: {len(perfs)}   (locked% = effects shared; g = per-slot amp gain ladder)"]
    for p in perfs:
        slots = " / ".join(s.rig_name or "-" for s in p.slots)
        ratio = locked_ratio(p)
        locked = "  - " if ratio is None else f"{ratio * 100:.0f}%"
        ladder = "/".join(f"{g:.1f}" if g is not None else "?"
                          for g in gain_ladder(p, gain_index)) if gain_index else ""
        gtxt = f"g {ladder:18s}" if ladder else " " * 20
        lines.append(f"  {p.name[:30]:30s}  [{len(p.slots)}]  locked {locked:>4}  {gtxt}  {slots}")
    return "\n".join(lines)
