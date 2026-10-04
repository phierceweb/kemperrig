"""The parameter pages rig blobs carry, raw and asserting nothing: one rig's, and a census
of the library."""

from __future__ import annotations

from dataclasses import dataclass

from kemperrig import _sysex, _sysex_effects
from kemperrig.model import Rig
from kemperrig.services.decode import rig_messages


@dataclass(frozen=True)
class PageUse:
    page: int
    rigs: int                   # rigs carrying at least one block on this page
    starts: list[int]           # distinct start numbers
    param_counts: list[int]     # distinct block lengths, in 14-bit values


@dataclass(frozen=True)
class OtherUse:
    header: bytes               # first six body bytes of a message in another framing
    rigs: int
    lengths: list[int]          # distinct body lengths, in bytes


@dataclass(frozen=True)
class PageCensus:
    rigs: int
    pages: list[PageUse]
    other: list[OtherUse]
    unparsed: list[str]         # folder/name of each rig whose payload does not parse


def rig_pages(rig: Rig) -> tuple[dict[tuple[int, int], list[int]], list[tuple[bytes, int]]]:
    """One rig's parameter blocks and its messages in other framings, raw."""
    messages = rig_messages(rig)
    return _sysex_effects.blocks(messages), _sysex_effects.other_messages(messages)


def census(rigs: list[Rig]) -> PageCensus:
    pages: dict[int, tuple[set[int], set[int], set[int]]] = {}
    other: dict[bytes, tuple[set[int], set[int]]] = {}
    unparsed = []
    for n, rig in enumerate(rigs):
        messages = _sysex.parse_messages(rig.blob)
        if messages is None:
            unparsed.append(rig.path)
            continue
        for (page, start), values in _sysex_effects.blocks(messages).items():
            holders, starts, counts = pages.setdefault(page, (set(), set(), set()))
            holders.add(n)
            starts.add(start)
            counts.add(len(values))
        for header, length in _sysex_effects.other_messages(messages):
            holders, lengths = other.setdefault(header, (set(), set()))
            holders.add(n)
            lengths.add(length)
    return PageCensus(
        rigs=len(rigs),
        pages=[PageUse(page=p, rigs=len(h), starts=sorted(s), param_counts=sorted(c))
               for p, (h, s, c) in sorted(pages.items())],
        other=[OtherUse(header=k, rigs=len(h), lengths=sorted(ln))
               for k, (h, ln) in sorted(other.items())],
        unparsed=unparsed,
    )
