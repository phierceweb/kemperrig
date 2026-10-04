"""Module blocks inside a rig blob: the raw 14-bit parameter pages, the messages in other
framings, and which effect type each module slot holds."""

from __future__ import annotations

from dataclasses import dataclass

from kemperrig import _enums
from kemperrig._sysex import _AMP_PAGE, Message

# Layout in docs/format.md; page numbers from Kemper's MIDI Parameter Documentation. 0x4b is
# the pre-2019 REV, a room size on its own list: the global enum would call value 1 "Wah Wah".
# Delay page 0x4A is inert since OS 4.0 — delays live in the DLY stomp slot.
_MULTI_HEADER = b"\x00\x00\x02\x00"
_F08_HEADER = b"\x00\x00\x08\x00"
_STOMP_PAGES = {0x32: "A", 0x33: "B", 0x34: "C", 0x35: "D", 0x38: "X", 0x3a: "MOD", 0x3c: "DLY"}
_REV_PAGE = 0x3d
_LEGACY_REV_PAGE = 0x4b
_PAGE_LABELS = {**_STOMP_PAGES, _REV_PAGE: "REV", _LEGACY_REV_PAGE: "REV (legacy)",
                _AMP_PAGE: "amp"}


@dataclass(frozen=True)
class Effect:
    slot: str               # A/B/C/D/X/MOD/DLY/REV, in signal-flow order
    type_value: int | None  # None for an undecoded slot
    type_name: str | None   # None when the active table doesn't know the value
    on: bool | None
    category: str | None = None   # Kemper's own grouping, when the table supplies one
    decoded: bool = True    # False: the slot exists only in the function-08 framing


def blocks(messages: list[Message]) -> dict[tuple[int, int], list[int]]:
    """Every multi-parameter block, keyed (page, start number), as its 14-bit values in
    param order. Blocks appear in message order; a repeated key keeps its first block."""
    out: dict[tuple[int, int], list[int]] = {}
    for m in messages:
        body = m.payload[3:]
        if m.is_kemper and len(body) >= 6 and body[:4] == _MULTI_HEADER:
            out.setdefault((body[4], body[5]), [((body[i] & 0x7f) << 7) | (body[i + 1] & 0x7f)
                                                for i in range(6, len(body) - 1, 2)])
    return out


def other_messages(messages: list[Message]) -> list[tuple[bytes, int]]:
    """(first six body bytes, body length) of every Kemper message that is neither a string
    nor a 14-bit block — framings nothing here decodes."""
    return [(m.payload[3:9], len(m.payload) - 3) for m in messages
            if m.is_kemper and not m.is_string and m.payload[3:7] != _MULTI_HEADER]


def page_label(page: int) -> str | None:
    """The slot name for a page the decoder reads; None for every other page."""
    return _PAGE_LABELS.get(page)


def _effect(slot: str, params: list[int], names: dict[int, str],
            categories: dict[int, str] | None = None) -> Effect:
    tv = params[0]
    return Effect(slot=slot, type_value=tv, type_name=names.get(tv),
                  on=bool(params[3]) if len(params) > 3 else None,
                  category=(categories or {}).get(tv))


def f08_pages(messages: list[Message]) -> set[int]:
    """Pages present as a function-08 block from param 0 — a framing nothing here decodes
    beyond the amp gain."""
    return {m.payload[7] for m in messages
            if m.is_kemper and len(m.payload) >= 9 and m.payload[3:7] == _F08_HEADER
            and m.payload[8] == 0}


def _undecoded(slot: str) -> Effect:
    return Effect(slot=slot, type_value=None, type_name=None, on=None, decoded=False)


def effect_chain(messages: list[Message]) -> list[Effect]:
    """Loaded effects per module slot (empty slots — type 0 — omitted), in signal-flow order.
    A slot whose only block is function 08 is undecoded: its type, and whether it holds an
    effect at all, are unknown. A function-02 block always decides its slot."""
    t = _enums.tables()
    found = blocks(messages)
    f08 = f08_pages(messages)
    out = []
    for page, slot in _STOMP_PAGES.items():
        params = found.get((page, 0))
        if params is not None:
            if params and params[0]:
                out.append(_effect(slot, params, t.types, t.categories))
        elif page in f08:
            out.append(_undecoded(slot))
    rev = found.get((_REV_PAGE, 0))
    legacy = found.get((_LEGACY_REV_PAGE, 0))
    if rev and rev[0]:
        out.append(_effect("REV", rev, t.types, t.categories))
    elif legacy and legacy[0]:
        out.append(_effect("REV", legacy, t.legacy_reverb))
    elif rev is None and legacy is None and f08 & {_REV_PAGE, _LEGACY_REV_PAGE}:
        out.append(_undecoded("REV"))
    return out
