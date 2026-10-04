"""Rewrite one string parameter inside a blob, keeping every other byte as it was."""

from __future__ import annotations

from kemperrig._sysex import (
    _TRACK_TAGS,
    Message,
    _chunks,
    _read_vlq,
    _skip_delta,
    _string_value,
)


def _vlq(n: int) -> bytes:
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(out)


def _is_target(payload: bytes, address: bytes, old: str) -> bool:
    m = Message(payload)
    return m.is_string and payload[6:9] == address and _string_value(m) == old.strip()


def _rewrite_track(track: bytes, address: bytes, old: str, new: bytes) -> tuple[bytes, int]:
    """The track with each matching event re-encoded; anything after the SysEx events, such
    as an end-of-track meta event, is carried over untouched."""
    out = bytearray()
    i, count, end = 0, 0, len(track)
    while i < end:
        j = _skip_delta(track, i, end)
        if j >= end or track[j] != 0xF0:
            break
        length, k = _read_vlq(track, j + 1, end)
        if k + length > end:
            raise ValueError("truncated blob: a SysEx event runs past the end of its track")
        payload = track[k:k + length - 1]
        if _is_target(payload, address, old):
            tail = payload[9:].partition(b"\x00")[2]
            event = payload[:9] + new + b"\x00" + tail + track[k + length - 1:k + length]
            out += track[i:j + 1] + _vlq(len(event)) + event
            count += 1
        else:
            out += track[i:k + length]
        i = k + length
    return bytes(out + track[i:]), count


def replace_string(blob: bytes, address: bytes, old: str, new: str, *,
                   tracks: set[int] | None = None) -> tuple[bytes, int]:
    """`blob` with the string at `address` changed from `old` to `new` (ASCII), in the tracks
    numbered in `tracks` (0-based, as `_sysex.tracks` counts them) or in all of them. Returns
    the blob and how many strings changed; with none, the original bytes come back."""
    encoded = new.encode("ascii")
    out = bytearray()
    count = index = 0
    for tag, start, end in _chunks(blob):
        if tag in _TRACK_TAGS:
            if tracks is None or index in tracks:
                track, changed = _rewrite_track(blob[start:end], address, old, encoded)
                if changed:
                    out += tag + len(track).to_bytes(4, "big") + track
                    count += changed
                    index += 1
                    continue
            index += 1
        out += blob[start - 8:end]
    return (bytes(out), count) if count else (blob, 0)
