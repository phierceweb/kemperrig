"""Text views for curation: the library analysis and a shortlist."""

from __future__ import annotations

from kemperrig.model import Rig
from kemperrig.services.analyze import Analysis

from ._library import _rig_line


def render_shortlist(rigs: list[Rig], *, label: str = "shortlist",
                     context: str | None = None) -> str:
    head = f"{label}: {len(rigs)} rigs" + (f"  ({context})" if context else "")
    return "\n".join([head] + [_rig_line(r) for r in rigs])


def render_analysis(a: Analysis) -> str:
    lines = [f"Library analysis{f' — {a.user}' if a.user else ''}"]
    why = ("unused by any performance" if a.rack_folder is None
           else f"unused by any performance & not in {a.rack_folder!r}")
    lines.append(f"  rigs {a.rigs}  ·  orphaned {len(a.orphans)} ({why})")
    lines.append(f"  drive: boosted {a.drive['boosted']} · unboosted {a.drive['unboosted']} "
                 f"· unknown {a.drive['unknown']}")
    lines.append(f"  byte-identical profiles: {len(a.identical_profiles)} groups "
                 f"({sum(len(g) for g in a.identical_profiles)} rigs — the same file stored "
                 "twice)")
    lines.append(f"  byte-identical amp blocks: {len(a.identical_amps)} groups "
                 f"({sum(len(g) for g in a.identical_amps)} rigs — same amp and settings, "
                 "other effects)")
    lines.append(f"  similar metadata: {len(a.similar)} groups "
                 f"({sum(len(g) for g in a.similar)} rigs, same author+amp+gain+boost — "
                 f"a prompt to listen, not evidence)")
    lines.append(f"  performances with out-of-order gain ladder: {len(a.misordered)}")

    skipped = a.unparsed
    if skipped.rigs or skipped.performances:
        lines.append(f"\n  payloads that do not parse, skipped "
                     f"({len(skipped.rigs) + len(skipped.performances)}; `doctor` says why):")
        lines += [f"    rig {r.path}" for r in skipped.rigs]
        lines += [f"    performance {p.name}" for p in skipped.performances]

    gaps = a.coverage_gaps
    lines.append(f"\n  amp coverage gaps ({len(gaps)} amps with ≥3 rigs missing a clean or a high):")
    for amp, c in sorted(gaps.items(), key=lambda kv: -kv[1].count)[:15]:
        miss = ", ".join(m for m, ok in (("clean", c.has_clean), ("high", c.has_high)) if not ok)
        span = ("no parsed gain" if c.gain_min is None
                else f"gain {c.gain_min}-{c.gain_max}")
        lines.append(f"    {amp[:30]:30s} n={c.count:3d}  {span}  missing: {miss}")

    if a.effect_categories:
        top = "  ".join(f"{c} {n}" for c, n in a.effect_categories[:8])
        lines.append(f"\n  effect slots by category: {top}")

    lines.append(f"\n  cab IRs in use: {len(a.ir_inventory)} distinct")
    for name, n in a.ir_inventory[:10]:
        lines.append(f"    {n:4d}  {name}")

    lines.append(f"\n  orphaned rigs ({len(a.orphans)}) — prune candidates:")
    for r in sorted(a.orphans, key=lambda r: r.folder)[:20]:
        lines.append(f"    {r.name[:34]:34s}  {r.folder}")
    if len(a.orphans) > 20:
        lines.append(f"    … and {len(a.orphans) - 20} more")
    return "\n".join(lines)
