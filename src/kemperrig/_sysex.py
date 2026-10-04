"""Decode a Kemper `.krig` / `.kperformance` payload: framing, string parameters, per-track
structure and amp gain. Module blocks are in `_sysex_effects`; the layout is in
docs/format.md."""

from __future__ import annotations

from dataclasses import dataclass

_MFR = b"\x00\x20\x33"
_STRING_HEADER = b"\x00\x00\x03"  # payload[3:6] for a string parameter


@dataclass(frozen=True)
class Message:
    """One Kemper SysEx payload — bytes from the manufacturer id up to (not incl.) the `F7`."""
    payload: bytes

    @property
    def is_kemper(self) -> bool:
        return self.payload[:3] == _MFR

    @property
    def header(self) -> bytes:
        return self.payload[3:6] if self.is_kemper else b""

    @property
    def is_string(self) -> bool:
        return self.header == _STRING_HEADER


def _read_vlq(buf: bytes, i: int, end: int) -> tuple[int, int]:
    val = 0
    while True:
        if i >= end:
            raise ValueError("truncated blob: a length runs past the end of its track")
        b = buf[i]
        i += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            return val, i


def _skip_delta(buf: bytes, i: int, end: int) -> int:
    """Where the event after the delta time at `i` starts — past `end` when the delta runs off
    the track, so the walk stops there instead of raising."""
    while i < end and buf[i] & 0x80:
        i += 1
    return i + 1


def _parse_track(data: bytes, start: int, end: int) -> tuple[list[Message], int]:
    """The track's SysEx events, and where they stop: `end`, or the first event that is not
    one, which nothing here reads."""
    msgs: list[Message] = []
    i = start
    while i < end:
        event = i
        i = _skip_delta(data, i, end)
        if i >= end or data[i] != 0xF0:
            return msgs, event
        i += 1
        length, i = _read_vlq(data, i, end)
        if i + length > end:
            raise ValueError("truncated blob: a SysEx event runs past the end of its track")
        payload = data[i:i + length - 1]   # drop the trailing F7
        i += length
        msgs.append(Message(payload=bytes(payload)))
    return msgs, end


_TRACK_TAGS = (b"KTrk", b"MTrk")  # Kemper-branded or standard-MIDI chunk tag (both occur)


def _chunks(blob: bytes) -> list[tuple[bytes, int, int]]:
    """(tag, body start, body end) of each chunk. A chunk running past the end of the blob,
    or bytes left after the last chunk, is a ValueError."""
    out: list[tuple[bytes, int, int]] = []
    pos, n = 0, len(blob)
    while pos + 8 <= n:
        tag = blob[pos:pos + 4]
        size = int.from_bytes(blob[pos + 4:pos + 8], "big")
        body = pos + 8
        if body + size > n:
            label = tag.decode() if tag.isalpha() else tag.hex(" ")
            raise ValueError(f"truncated blob: a {label} chunk declares {size} bytes, "
                             f"{n - body} present")
        out.append((tag, body, body + size))
        pos = body + size
    if pos < n:
        raise ValueError(f"truncated blob: {n - pos} bytes after the last chunk, too few for "
                         "another")
    return out


_PERFORMANCE_TRACKS = 6   # a header track, then one per slot


def walk(blob: bytes, *, performance: bool = False
         ) -> tuple[list[list[Message]], list[tuple[int, int, int]]]:
    """The blob's tracks, and (track, unread bytes, track size) for each whose SysEx events
    stop before its end. A payload cut short is a ValueError; so, for a `performance`, is
    any track count but a header and 5 slots (an empty payload has none)."""
    found = [(start, end, *_parse_track(blob, start, end))
             for tag, start, end in _chunks(blob) if tag in _TRACK_TAGS]
    if performance and blob and len(found) != _PERFORMANCE_TRACKS:
        raise ValueError(f"a performance payload holds {len(found)} tracks, not "
                         f"{_PERFORMANCE_TRACKS} (a header and 5 slots)")
    return ([msgs for _, _, msgs, _ in found],
            [(n, end - stop, end - start) for n, (start, end, _, stop) in enumerate(found)
             if stop < end])


def tracks(blob: bytes) -> list[list[Message]]:
    """Split a blob into its tracks (a rig has one; a performance a header + 5 slot tracks).
    Both `KTrk` and `MTrk` chunks occur; a payload cut short is a ValueError."""
    return walk(blob)[0]


def iter_messages(blob: bytes) -> list[Message]:
    return [m for track in tracks(blob) for m in track]


def performance_tracks(blob: bytes) -> list[list[Message]]:
    """A performance payload's tracks: the header, then slot n at index n. A payload holding
    any other number of tracks is a ValueError; an empty one has none."""
    return walk(blob, performance=True)[0]


def parse_tracks(blob: bytes) -> list[list[Message]] | None:
    """`tracks`, or None for a payload that does not parse."""
    try:
        return tracks(blob)
    except ValueError:
        return None


def parse_performance(blob: bytes) -> list[list[Message]] | None:
    """`performance_tracks`, or None for a performance payload that does not parse."""
    try:
        return performance_tracks(blob)
    except ValueError:
        return None


def parse_messages(blob: bytes) -> list[Message] | None:
    """`iter_messages`, or None for a payload that does not parse."""
    found = parse_tracks(blob)
    return None if found is None else [m for t in found for m in t]


# Every stored rig and preset opens with this header (format 0, one track, 480 ticks).
_KRIG_HEADER = b"KThd" + (6).to_bytes(4, "big") + b"\x00\x00\x00\x01\x01\xe0"


def krig(track: bytes) -> bytes:
    """A standalone rig or preset payload holding one bare track body: the header a stored
    rig carries, then the track as its one `KTrk` chunk."""
    return _KRIG_HEADER + b"KTrk" + len(track).to_bytes(4, "big") + track


def _string_value(m: Message) -> str:
    # payload = 00 20 33 | 00 00 03 | <3-byte address> | <utf8> | 00  → string starts at byte 9
    return m.payload[9:].split(b"\x00", 1)[0].decode("utf-8", "replace").strip()


def decode_strings(messages: list[Message]) -> list[str]:
    """All non-empty string-parameter values, in order."""
    return [s for s in (_string_value(m) for m in messages if m.is_string) if s]


def ir_files(strings: list[str]) -> list[str]:
    """The cab-IR `.wav` file names among decoded strings, in order."""
    return [s for s in strings if s.lower().endswith(".wav")]


# String addresses whose meaning was checked against the metadata columns they mirror.
_RIG_NAME_ADDRESS = b"\x00\x00\x01"   # the Rigs `Name` / slot `RigName`
_CAB_NAME_ADDRESS = b"\x00\x00\x20"   # the loaded cab's name; slot `CabName`


def addressed_strings(messages: list[Message]) -> dict[bytes, str]:
    """Each string parameter's value by its 3-byte address; the first occurrence wins."""
    out: dict[bytes, str] = {}
    for m in messages:
        if m.is_string:
            out.setdefault(m.payload[6:9], _string_value(m))
    return out


def _string_at(messages: list[Message], address: bytes) -> str | None:
    for m in messages:
        if m.is_string and m.payload[6:9] == address:
            return _string_value(m) or None
    return None


def rig_name(track: list[Message]) -> str | None:
    """The rig name a rig's track, or a performance slot's, carries — what the Profiler shows."""
    return _string_at(track, _RIG_NAME_ADDRESS)


def cab_name(track: list[Message]) -> str | None:
    """The name of the cab a rig's or slot's track loads, and a cab preset's own name."""
    return _string_at(track, _CAB_NAME_ADDRESS)


_AMP_PAGE = 0x0a
# (function, body length) of every amp-block shape whose gain was checked against the
# metadata Gain column. Function 02 carries 14-bit param pairs; function 08's framing is not
# decoded beyond the gain.
_AMP_BLOCK_SHAPES = frozenset({(0x02, 36), (0x02, 40), (0x02, 50), (0x02, 54),
                               (0x08, 74), (0x08, 94), (0x08, 102)})
_GAIN_OFFSET = 14                # body offset of the 14-bit amp-gain value, in every shape
_GAIN_FULLSCALE = 1638.4         # 16383 ≙ 10.0, so gain = raw / 1638.4
# The Gain column stores one decimal: a decode agrees within half a step plus one raw step.
GAIN_TOLERANCE = 0.05 + 1 / _GAIN_FULLSCALE


def amp_block(messages: list[Message]) -> bytes | None:
    """The body of the rig's amp-definition block (page `0x0a` from param 0), or None when
    no block of a verified shape is present."""
    for m in messages:
        body = m.payload[3:]
        if (m.is_kemper and len(body) > 6 and body[:2] == b"\x00\x00" and body[3] == 0
                and body[4] == _AMP_PAGE and body[5] == 0
                and (body[2], len(body)) in _AMP_BLOCK_SHAPES):
            return body
    return None


def amp_gain(messages: list[Message]) -> float | None:
    """The amp's Gain knob (0.0–10.0), decoded from a standalone rig's amp-definition block.

    The raw 14-bit value / 1638.4 agrees with the metadata Gain to within the one-decimal
    rounding that column stores. None when the rig has no amp block of a verified shape. A
    performance slot's gain is read via its referenced rig instead."""
    body = amp_block(messages)
    if body is None:
        return None
    high, low = body[_GAIN_OFFSET], body[_GAIN_OFFSET + 1]
    if (high | low) & 0x80:   # not SysEx data, so not a gain
        return None
    return ((high << 7) | low) / _GAIN_FULLSCALE


def effects_locked(slot_tracks: list[list[Message]]) -> tuple[int, int, float | None]:
    """How many of the first slot track's parameter messages every other slot track repeats
    byte for byte (locked), out of its total; the rest are the per-slot amp. The ratio is None
    when there are fewer than two tracks or the first holds nothing to compare."""
    kemper = [[m.payload for m in t if m.is_kemper] for t in slot_tracks]
    if len(kemper) < 2 or not kemper[0]:
        return (0, len(kemper[0]) if kemper else 0, None)
    others = [set(t) for t in kemper[1:]]
    locked = sum(1 for payload in kemper[0] if all(payload in o for o in others))
    return (locked, len(kemper[0]), locked / len(kemper[0]))
