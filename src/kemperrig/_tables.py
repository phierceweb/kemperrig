"""Read the SQLite tables inside a `.rmbackup` — rows in, records out.

Each db is loaded from its bytes into an in-memory connection via `sqlite3.deserialize`;
which db is which is decided by the container layout in `model.py`.
"""

from __future__ import annotations

import math
import re
import sqlite3
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import TypeVar

from kemperrig.records import Info, Performance, Preset, Rig, Slot

_T = TypeVar("_T")

_INFO = "info.xml"
_LIB_PREFIX = "Local Library/"
_REPOSITORY_DB = "repositoryR2.db"
_DB_SUFFIX = "/" + _REPOSITORY_DB
_PERF_DB = "Prf/Local Library/repositoryR2.db"
_PERF_SLOTS = 5
_PRESET_PREFIX = "Prst/"
_RIG_TEXT = {
    "filename": "Filename", "author": "Author", "date": "Date", "comment": "Comment",
    "amp_model": "Amp Model", "amp_name": "Amp Name", "amp_comment": "Amp Comment",
    "amp_channel": "Amp Channel", "source_amp": "Source Amp", "amp_model_year": "Amp Model Year",
    "amp_location": "Amp Location", "amp_pickup": "Amp Pickup", "cabinet_name": "Cabinet Name",
    "mic_type": "Mic Type", "mic_position": "Mic Position",
    "speaker_manufacturer": "Speaker Manufacturer", "speaker_model": "Speaker Model",
    "profile_type": "Profile Type", "profile_revision": "Profile Revision",
    "cabinet_type": "Cabinet Type", "cabinet_configuration": "Cabinet Configuration",
}
# Rigs columns an older Rig Manager may not write; absent, they read as None.
_OPTIONAL_RIG_COLUMNS = ("Profile Type", "Profile Revision", "Cabinet Type",
                         "Cabinet Configuration")
_SQLITE_MAGIC = b"SQLite format 3\x00"
# A dated snapshot is one bare db; its ROMPresets table is factory content and is not read.
_SNAPSHOT_TABLES = ("Rigs", "Performances", "Presets")
_SNAPSHOT_DIR = "Backups"
_SNAPSHOT_SUFFIX = "R2.db"
_BACKUP_SUFFIX = ".rmbackup"
# Rig Manager stamps snapshot and backup file names with a local date-time.
_STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2})-(\d{2})-(\d{2})")
_SNAPSHOT_NAME = re.compile(r"(.+?) - \d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}R2\.db")


def _to_float(text: str | None) -> float | None:
    """The number in `text`, or None — also for NaN or an infinity, which no knob holds."""
    try:
        value = float(text)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _text(value: object) -> object:
    """A text column's value; a BLOB, which a TEXT column keeps as bytes, reads as NULL."""
    return None if isinstance(value, bytes) else value


def _payload(value: object) -> bytes:
    """A blob column's bytes; NULL or a non-BLOB value reads as an empty payload."""
    return value if isinstance(value, bytes) else b""


def _load_db(blob: bytes, name: str) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    try:
        con.deserialize(blob)
    except (MemoryError, sqlite3.Error) as e:  # a 0-byte db raises MemoryError, not DatabaseError
        con.close()
        raise ValueError(f"unreadable {name} ({len(blob)} bytes): {e}")
    con.row_factory = sqlite3.Row
    return con


def _has_table(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _read_info(blob: bytes, name: str) -> Info:
    raw = blob.decode("utf-8", "replace")
    # Kemper writes a malformed XML declaration (`encoding="UTF - 8"`, spaces around the hyphen)
    # that strict parsers reject — strip any leading declaration before parsing the body.
    raw = re.sub(r"^\s*<\?xml.*?\?>", "", raw, count=1, flags=re.DOTALL)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise ValueError(f"{name}: {e}") from e
    db = root.find("db")
    user = root.find("user")
    return Info(
        version=db.get("version") if db is not None else None,
        user=user.get("name") if user is not None else None,
    )


def _optional_columns(con: sqlite3.Connection) -> str:
    have = {row[1] for row in con.execute('PRAGMA table_info("Rigs")')}
    return ", ".join(f'r."{c}"' if c in have else f'NULL AS "{c}"'
                     for c in _OPTIONAL_RIG_COLUMNS)


def _read(blob: bytes, name: str, rows: Callable[[sqlite3.Connection], _T]) -> _T:
    """`rows` over the db in `blob`; a db that fails to read is a ValueError naming `name`."""
    con = _load_db(blob, name)
    try:
        return rows(con)
    except sqlite3.DatabaseError as e:   # a damaged db often deserializes, then fails on read
        raise ValueError(f"unreadable {name}: {e}") from e
    finally:
        con.close()


def _read_rigs(blob: bytes, folder: str, name: str) -> list[Rig]:
    return _read(blob, name, lambda con: _rigs(con, folder))


def _rigs(con: sqlite3.Connection, folder: str) -> list[Rig]:
    if not _has_table(con, "Rigs"):
        return []
    rows = con.execute(
        'SELECT r.Filename, r."Name", r."Date", r.Author, r.Comment, r.Gain, r."Amp Model", '
        'r."Amp Name", r."Amp Comment", r."Amp Channel", r."Source Amp", r."Amp Model Year", '
        'r."Amp Location", r."Amp Pickup", r."Cabinet Name", r."Mic Type", r."Mic Position", '
        f'r."Speaker Manufacturer", r."Speaker Model", {_optional_columns(con)}, '
        'b.data AS _blob FROM Rigs r LEFT JOIN Rigs_blobs b ON r.id = b.id'
    ).fetchall()
    return [Rig(name=_text(r["Name"]) or "", folder=folder, gain=_to_float(r["Gain"]),
                blob=_payload(r["_blob"]), **{f: _text(r[c]) for f, c in _RIG_TEXT.items()})
            for r in rows]


def _read_performances(blob: bytes, name: str) -> list[Performance]:
    return _read(blob, name, _performances)


def _performances(con: sqlite3.Connection) -> list[Performance]:
    if not _has_table(con, "Performances"):
        return []
    cols = ", ".join(
        f'p."Slot{n}{k}"'
        for n in range(1, _PERF_SLOTS + 1)
        for k in ("Name", "Enable", "RigName", "AmpName", "CabName")
    )
    rows = con.execute(
        f'SELECT p.Filename, p."Name", p."Tempo", {cols}, b.data AS _blob '
        'FROM Performances p LEFT JOIN Performances_blobs b ON p.id = b.id'
    ).fetchall()
    out = []
    for r in rows:
        slots = []
        for n in range(1, _PERF_SLOTS + 1):
            rig_name = _text(r[f"Slot{n}RigName"])
            if not rig_name:
                continue
            slots.append(Slot(
                index=n, name=_text(r[f"Slot{n}Name"]), enable=_text(r[f"Slot{n}Enable"]),
                rig_name=rig_name, amp_name=_text(r[f"Slot{n}AmpName"]),
                cab_name=_text(r[f"Slot{n}CabName"]),
            ))
        out.append(Performance(
            name=_text(r["Name"]) or "", filename=_text(r["Filename"]), tempo=_text(r["Tempo"]),
            slots=slots,
            blob=_payload(r["_blob"]),
        ))
    return out


def _read_rig_names(blob: bytes, name: str) -> set[str]:
    return _read(blob, name, _rig_names)


def _rig_names(con: sqlite3.Connection) -> set[str]:
    if not _has_table(con, "Rigs"):
        return set()
    return {_text(r[0]) or "" for r in con.execute('SELECT "Name" FROM Rigs')}


def _read_slot_rig_names(blob: bytes, name: str) -> set[str]:
    return _read(blob, name, _slot_rig_names)


def _slot_rig_names(con: sqlite3.Connection) -> set[str]:
    """The rig names performance slots load, from whichever slot columns the table has."""
    if not _has_table(con, "Performances"):
        return set()
    have = {row[1] for row in con.execute('PRAGMA table_info("Performances")')}
    cols = [c for n in range(1, _PERF_SLOTS + 1) if (c := f"Slot{n}RigName") in have]
    return {v for c in cols for (v,) in con.execute(f'SELECT "{c}" FROM Performances')
            if _text(v)}


def _read_presets(blob: bytes, folder: str, name: str) -> list[Preset]:
    return _read(blob, name, lambda con: _presets(con, folder))


def _presets(con: sqlite3.Connection, folder: str) -> list[Preset]:
    if not _has_table(con, "Presets"):
        return []
    rows = con.execute(
        'SELECT p.Filename, p."Name", p."Preset Class", p."Preset Category", '
        'p."Preset Type", b.data AS _blob '
        'FROM Presets p LEFT JOIN Presets_blobs b ON p.id = b.id'
    ).fetchall()
    return [
        Preset(
            name=_text(r["Name"]) or "", folder=folder, filename=_text(r["Filename"]),
            preset_class=_text(r["Preset Class"]),
            preset_category=_text(r["Preset Category"]),
            preset_type=_text(r["Preset Type"]), blob=_payload(r["_blob"]),
        )
        for r in rows
    ]


def _snapshot(con: sqlite3.Connection,
              name: str) -> tuple[list[Rig], list[Performance], list[Preset]]:
    """Rigs, performances and presets from one snapshot db. Nothing in it has a folder."""
    try:
        missing = [t for t in _SNAPSHOT_TABLES if not _has_table(con, t)]
        if missing:
            raise ValueError(f"{name}: no {' or '.join(missing)} table — not a Rig Manager "
                             "snapshot or pack")
        return _rigs(con, ""), _performances(con), _presets(con, "")
    except sqlite3.DatabaseError as e:   # a truncated db deserializes, then fails on read
        raise ValueError(f"{name}: unreadable snapshot: {e}") from e
