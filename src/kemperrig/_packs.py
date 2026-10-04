"""Read a Rig Manager rig or preset pack — rows in, records out. Layout: docs/format.md."""

from __future__ import annotations

import sqlite3

from kemperrig import _sysex
from kemperrig._tables import _text
from kemperrig.records import Pack, Preset, Rig

_PACK_TABLES = ("packs", "rigs", "rigdata")
_CONTENT = {"Rigs": "rigs", "Presets": "presets"}
# Rig field ← the payload string at address `00 00 <n>`.
_STRING_FIELDS = {
    "comment": 0x04, "amp_name": 0x10, "amp_location": 0x14, "source_amp": 0x15,
    "amp_comment": 0x16, "amp_model": 0x18, "amp_channel": 0x19, "amp_pickup": 0x1a,
    "amp_model_year": 0x1b, "cabinet_name": 0x20, "mic_type": 0x26, "mic_position": 0x28,
    "cabinet_configuration": 0x29, "speaker_manufacturer": 0x2c, "speaker_model": 0x2d,
}


def _table_names(con: sqlite3.Connection) -> set[str]:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def is_pack(con: sqlite3.Connection, name: str) -> bool:
    try:
        return set(_PACK_TABLES) <= _table_names(con)
    except sqlite3.DatabaseError as e:   # a truncated db deserializes, then fails on read
        raise ValueError(f"{name}: unreadable database: {e}") from e


def read_pack(con: sqlite3.Connection, name: str) -> Pack:
    """The pack in `con`; `name` labels its errors. A file holding more than one pack, or
    content other than rigs or presets, is refused rather than guessed at."""
    try:
        return _read(con, name)
    except sqlite3.DatabaseError as e:   # a truncated db deserializes, then fails on read
        raise ValueError(f"{name}: unreadable pack: {e}") from e


def _read(con: sqlite3.Connection, name: str) -> Pack:
    packs = con.execute("SELECT name, author, copyright, releasedate FROM packs").fetchall()
    if len(packs) != 1:
        raise ValueError(f"{name}: {len(packs)} packs in one file — expected one")
    content = _content(con, name)
    rows = con.execute("SELECT r.name, r.author, r.createdate, d.rig FROM rigs r "
                       "LEFT JOIN rigdata d ON d.id = r.rig_id ORDER BY r.id").fetchall()
    pack_name, author, copyright_, released = (_text(v) for v in packs[0])
    rows = [(*(_text(v) for v in row[:3]), row[3]) for row in rows]
    rigs = [_rig(*row) for row in rows] if content == "rigs" else []
    presets = ([Preset(name=r[0] or "", folder="", blob=_payload(r[3])) for r in rows]
               if content == "presets" else [])
    return Pack(name=pack_name, author=author, copyright=copyright_, released=released,
                content=content, rigs=rigs, presets=presets)


def _content(con: sqlite3.Connection, name: str) -> str:
    row = (con.execute("SELECT val FROM properties WHERE key = 'Content'").fetchone()
           if "properties" in _table_names(con) else None)
    if row is None:
        raise ValueError(f"{name}: no Content property — cannot tell rigs from presets")
    if row[0] not in _CONTENT:
        raise ValueError(f"{name}: pack content {row[0]!r} is neither rigs nor presets")
    return _CONTENT[row[0]]


def _payload(track: bytes | None) -> bytes:
    return _sysex.krig(track) if isinstance(track, bytes) and track else b""


def _rig(name: str | None, author: str | None, date: str | None, track: bytes | None) -> Rig:
    blob = _payload(track)
    try:
        messages = _sysex.iter_messages(blob)
    except ValueError:   # kept with its payload so doctor reports it and the rest still reads
        return Rig(name=name or "", folder="", author=author, date=date, blob=blob)
    strings = _sysex.addressed_strings(messages)
    fields = {f: strings.get(bytes([0, 0, n])) or None for f, n in _STRING_FIELDS.items()}
    gain = _sysex.amp_gain(messages)
    return Rig(name=name or "", folder="", author=author, date=date,
               gain=None if gain is None else round(gain, 1), blob=blob, **fields)
