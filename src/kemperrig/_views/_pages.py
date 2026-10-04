"""Text views of raw parameter blocks: one rig's, and the library-wide census."""

from __future__ import annotations

from kemperrig import _sysex_effects
from kemperrig.model import Rig
from kemperrig.services.pages import PageCensus


def _page_col(page: int) -> str:
    label = _sysex_effects.page_label(page)
    return f"0x{page:02x} {label}" if label else f"0x{page:02x}"


def render_pages(rig: Rig, blocks: dict[tuple[int, int], list[int]],
                 other: list[tuple[bytes, int]]) -> str:
    """A rig's parameter blocks as raw 14-bit values, in the order the blob holds them."""
    lines = [f"{rig.name}  —  {rig.folder}", f"  {'page':<18}{'start':>5}{'count':>7}  values"]
    for (page, start), values in blocks.items():
        lines.append(f"  {_page_col(page):<18}{start:>5}{len(values):>7}  "
                     + " ".join(map(str, values)))
    if other:
        lines.append("  other framings, not decoded (first six bytes · length):")
        lines += [f"    {head.hex(" ")}  ·  {length}" for head, length in other]
    return "\n".join(lines)


def render_page_census(c: PageCensus) -> str:
    """Which pages occur across the library, in how many rigs, and at what lengths."""
    lines = [f"pages across {c.rigs} rigs", f"  {'page':<18}{'rigs':>6}  starts · param counts"]
    for p in c.pages:
        lines.append(f"  {_page_col(p.page):<18}{p.rigs:>6}  "
                     f"{' '.join(map(str, p.starts))} · {' '.join(map(str, p.param_counts))}")
    if c.other:
        lines.append("  other framings, not decoded (first six bytes · rigs · lengths):")
        lines += [f"    {o.header.hex(" ")}  ·  {o.rigs}  ·  {' '.join(map(str, o.lengths))}"
                  for o in c.other]
    if c.unparsed:
        lines.append(f"  payloads that do not parse ({len(c.unparsed)}; `doctor` says why):")
        lines += [f"    {where}" for where in c.unparsed]
    return "\n".join(lines)
