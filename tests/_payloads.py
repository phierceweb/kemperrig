"""SysEx payload builders for synthetic rigs and performances: Kemper messages and
the KThd/KTrk (or MThd/MTrk) chunks that carry them."""

from __future__ import annotations

import struct

_MFR = b"\x00\x20\x33"  # Kemper manufacturer id
PERF_SLOTS = 5


def _vlq(n: int) -> bytes:
    """MIDI variable-length quantity (big-endian, 7 bits/byte, high bit = continue)."""
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def string_msg(text: str, sid: int = 1) -> bytes:
    """A Kemper string-parameter payload: 00 20 33 | 00 00 03 | 00 00 <sid> | <utf8> | 00."""
    return _MFR + b"\x00\x00\x03" + bytes([0, 0, sid]) + text.encode("utf-8") + b"\x00"


def param_msg(addr: bytes, value: bytes) -> bytes:
    """A Kemper numeric-parameter payload: 00 20 33 | 00 00 02 | <addr> | <value>."""
    return _MFR + b"\x00\x00\x02" + addr + value


def module_msg(page: int, params: list[int], *, start: int = 0) -> bytes:
    """A multi-parameter-change module block: 00 20 33 | 00 00 02 00 | <page> <start> |
    <14-bit param pairs>. param[0]=Type, param[3]=On/Off for stomp pages. Mirrors real backups."""
    body = bytearray([0x00, 0x00, 0x02, 0x00, page, start])
    for v in params:
        body += bytes([(v >> 7) & 0x7F, v & 0x7F])
    return _MFR + bytes(body)


def f08_msg(page: int, *, start: int = 0, length: int = 40) -> bytes:
    """A function-08 module block, `length` bytes after the manufacturer id. Only the header
    is meaningful: nothing here decodes this framing beyond the amp gain."""
    body = bytearray(length)
    body[0:6] = bytes([0x00, 0x00, 0x08, 0x00, page, start])
    return _MFR + bytes(body)


# (function, body length) of each amp-block shape seen in real backups.
AMP_SHAPES = ((0x02, 36), (0x02, 40), (0x02, 50), (0x02, 54),
              (0x08, 74), (0x08, 94), (0x08, 102))


def amp_msg(gain: float, *, func: int = 0x02, length: int = 40, page: int = 0x0a,
            start: int = 0) -> bytes:
    """An amp block: `00 00 <func> 00 | <page 0x0a> <start 0> | ...`, `length` bytes after the
    manufacturer id, with the 14-bit amp gain (0..16383 = 0.0..10.0) at body offset 14. The
    40-byte function-02 form is profile type 1; the other shapes are later generations."""
    body = bytearray(length)
    body[0:6] = bytes([0x00, 0x00, func, 0x00, page, start])
    raw = min(16383, round(gain * 1638.4))
    body[14] = (raw >> 7) & 0x7F
    body[15] = raw & 0x7F
    return _MFR + bytes(body)


def rig_track(name: str, *, cab: str | None = None) -> list[bytes]:
    """A rig's track, or a performance slot's: the rig name at string address 01, and the
    loaded cab's name at 0x20 when one is loaded."""
    return [string_msg(name, 0x01)] + ([string_msg(cab, 0x20)] if cab else [])


def performance_blob(*slots: list[bytes]) -> bytes:
    """A performance payload: a header track, then one track per slot — five, as every real
    performance holds. Slots not given get an empty track, which no real payload confirms:
    every one seen uses all five slots."""
    return make_blob([[string_msg("2", 0x00)], *slots, *[[]] * (PERF_SLOTS - len(slots))])


def make_blob(tracks: list[list[bytes]], magic: str = "K") -> bytes:
    """`<magic>Thd` header + one `<magic>Trk` per track. A rig = 1 track; a performance = header
    + 5 slot tracks. Real backups use both `K`-branded chunks and standard-MIDI `M` chunks."""
    thd = magic.encode() + b"Thd"
    trk = magic.encode() + b"Trk"
    head = thd + struct.pack(">I", 6) + b"\x00\x01\x00\x06\x01\xe0"
    return head + b"".join(trk + struct.pack(">I", len(body)) + body
                           for body in (_track_body(t) for t in tracks))


def _track_body(payloads: list[bytes]) -> bytes:
    body = bytearray()
    for p in payloads:
        msg = p + b"\xf7"
        body += b"\x00" + b"\xf0" + _vlq(len(msg)) + msg
    return bytes(body)
