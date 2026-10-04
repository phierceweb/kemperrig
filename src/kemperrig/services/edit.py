"""`rename`: write a new `.rmbackup` with a rig renamed in its row, its payload and every slot
that loads it; every other zip entry is copied verbatim. The emitted archive has not been
confirmed to restore into Rig Manager."""

from __future__ import annotations

import io
import os
import sqlite3
import warnings
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from pf_core.utils.io import atomic_write_bytes

from kemperrig import _sysex
from kemperrig._archive import open_zip, read_entry
from kemperrig._sysex import _RIG_NAME_ADDRESS
from kemperrig._sysex_edit import replace_string
from kemperrig._tables import (
    _PERF_DB,
    _PERF_SLOTS,
    _has_table,
    _read_rig_names,
    _read_slot_rig_names,
)
from kemperrig.model import names_folder, rig_folder, write_refusal, zip_layout_problem

# No payload rig name in real backups is longer, or uses anything but printable ASCII.
_MAX_NAME = 32


class Renamed(NamedTuple):
    rigs: int            # library rows renamed
    slots: int           # performance slots re-pointed
    rig_payloads: int    # rig payloads whose own name was rewritten
    slot_payloads: int   # slot tracks whose own name was rewritten


def name_problem(name: str) -> str | None:
    """Why `name` cannot be written into a payload, or None."""
    if not name or name != name.strip():
        return f"{name!r}: a rig name must be non-empty with no surrounding spaces"
    if not (name.isascii() and name.isprintable()):
        return f"{name!r}: a rig name must be printable ASCII — the payload holds 7-bit text"
    if len(name) > _MAX_NAME:
        return (f"{name!r}: longer than {_MAX_NAME} characters, the longest rig name seen in "
                "real payloads")
    return None


def _rewrite_payloads(con: sqlite3.Connection, table: str, targets: dict[int, set[int] | None],
                      old: str, new: str, *, performance: bool = False) -> int:
    """Rewrite the rig-name string in each payload of `table` keyed in `targets`, in the tracks
    given (None: all). A payload that does not parse — for a `performance`, any of its tracks
    or its track count — or that names another rig, is left as it is."""
    if not _has_table(con, table):
        return 0
    changed = 0
    for row_id, tracks in targets.items():
        row = con.execute(f'SELECT data FROM "{table}" WHERE id = ?', (row_id,)).fetchone()
        if (row is None or not isinstance(row[0], bytes)
                or performance and _sysex.parse_performance(row[0]) is None):
            continue
        try:
            blob, n = replace_string(row[0], _RIG_NAME_ADDRESS, old, new, tracks=tracks)
        except ValueError:
            continue
        if n:
            con.execute(f'UPDATE "{table}" SET data = ? WHERE id = ?', (blob, row_id))
            changed += n
    return changed


def _rename_in_db(db_bytes: bytes, old: str, new: str) -> tuple[bytes, int, int]:
    """Return (db_bytes, rows renamed, payloads rewritten). If nothing changed, the ORIGINAL
    bytes are returned (not a re-serialized copy) so untouched dbs stay byte-identical."""
    con = sqlite3.connect(":memory:")
    try:
        con.deserialize(db_bytes)
        if not _has_table(con, "Rigs"):
            return db_bytes, 0, 0
        ids = [r[0] for r in con.execute('SELECT id FROM Rigs WHERE "Name" = ?', (old,))]
        if not ids:
            return db_bytes, 0, 0
        con.execute('UPDATE Rigs SET "Name" = ? WHERE "Name" = ?', (new, old))
        payloads = _rewrite_payloads(con, "Rigs_blobs", dict.fromkeys(ids), old, new)
        con.commit()
        return con.serialize(), len(ids), payloads
    finally:
        con.close()


def _repoint_slots(db_bytes: bytes, old: str, new: str) -> tuple[bytes, int, int]:
    """Re-point performance slots at the renamed rig: the slot's column, and the name inside
    the slot's own track (track n holds slot n). Returns (db_bytes, slots, payloads)."""
    con = sqlite3.connect(":memory:")
    try:
        con.deserialize(db_bytes)
        if not _has_table(con, "Performances"):
            return db_bytes, 0, 0
        cols = {row[1] for row in con.execute('PRAGMA table_info("Performances")')}
        targets: dict[int, set[int]] = {}
        for slot in range(1, _PERF_SLOTS + 1):
            col = f"Slot{slot}RigName"
            if col in cols:
                for (row_id,) in con.execute(
                        f'SELECT id FROM Performances WHERE "{col}" = ?', (old,)):
                    targets.setdefault(row_id, set()).add(slot)
                con.execute(f'UPDATE Performances SET "{col}" = ? WHERE "{col}" = ?', (new, old))
        slots = sum(len(s) for s in targets.values())
        if not slots:
            return db_bytes, 0, 0
        payloads = _rewrite_payloads(con, "Performances_blobs", dict(targets), old, new,
                                     performance=True)
        con.commit()
        return con.serialize(), slots, payloads
    finally:
        con.close()


def _content_refusal(names: list[str], read: Callable[[str], bytes], *, source: str,
                     old: str, new: str) -> str | None:
    """Why the archive holding the entries `names` cannot take this rename: it is not a Rig
    Manager backup, it would rename nothing, or it would attach a slot to a rig the slot was
    not built from. Reads only the names in the dbs rename rewrites."""
    why = zip_layout_problem(source, names)
    if why:
        return why
    rigs: set[str] = set()
    slots: set[str] = set()
    for entry in names:
        if entry == _PERF_DB:
            slots |= _read_slot_rig_names(read(entry), f"{entry} in {source}")
        elif rig_folder(entry) is not None:
            rigs |= _read_rig_names(read(entry), f"{entry} in {source}")
    if old not in rigs:
        return f"no rig named {old!r} in {source} — nothing to rename"
    if new == old:
        return f"{new!r} is already that rig's name"
    if new in rigs:
        return (f"a rig named {new!r} is already in {source} — every slot loading either rig "
                "would become ambiguous; choose another name")
    if new in slots:
        return (f"a performance slot already loads a rig named {new!r}, which no rig in "
                f"{source} has — renaming onto it would attach that slot to this rig; choose "
                "another name")
    return None


def _path_refusal(dst: str, *, source: str, force: bool, new_name: str) -> str | None:
    problem = name_problem(new_name)
    if problem:
        return problem
    if os.path.isdir(source) or (os.path.isfile(source) and not zipfile.is_zipfile(source)):
        return f"{source}: rename takes a .rmbackup archive, not a folder, snapshot or pack"
    if not str(dst).strip():
        return "-o names no file"
    why = write_refusal(dst, source, "-o")
    if why:
        return why
    if names_folder(dst):
        return f"{dst} is a folder — name a file"
    if os.path.lexists(dst) and not force:
        return f"{dst} already exists — choose a different -o, or pass --force"
    return None


def refusal(dst: str, *, source: str, force: bool, old_name: str,
            new_name: str) -> str | None:
    """Why renaming `source` into `dst` is unsafe or cannot work, or None when it is fine.
    Reads the source last, once every check on the paths has passed."""
    why = _path_refusal(dst, source=source, force=force, new_name=new_name)
    if why:
        return why
    with open_zip(source) as zf:
        return _content_refusal(zf.namelist(), lambda entry: read_entry(zf, entry, source),
                                source=source, old=old_name, new=new_name)


def rename_rig(src: str, dst: str, old_name: str, new_name: str, *,
               force: bool = False) -> Renamed:
    """Copy `src` to `dst`, renaming every rig named `old_name` to `new_name` — row and
    payload — and re-pointing the performance slots that loaded it. A payload whose own name
    is not `old_name` keeps it. Every other entry is copied byte-for-byte. Raises ValueError
    on `refusal` before writing."""
    why = _path_refusal(dst, source=src, force=force, new_name=new_name)
    if why:
        raise ValueError(why)
    with open_zip(src) as zin:
        items = [(info, read_entry(zin, info, src)) for info in zin.infolist()]
    data_of = {info.filename: data for info, data in items}
    why = _content_refusal(list(data_of), data_of.__getitem__, source=src, old=old_name,
                           new=new_name)
    if why:
        raise ValueError(why)

    rigs = slots = rig_payloads = slot_payloads = 0
    out: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info, data in items:
        if info.filename == _PERF_DB:
            data, n, p = _repoint_slots(data, old_name, new_name)
            slots, slot_payloads = slots + n, slot_payloads + p
        elif rig_folder(info.filename) is not None:
            data, n, p = _rename_in_db(data, old_name, new_name)
            rigs, rig_payloads = rigs + n, rig_payloads + p
        out.append((info, data))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout, warnings.catch_warnings():
        warnings.filterwarnings("ignore", "Duplicate name", UserWarning)   # as the source has
        for info, data in out:
            zout.writestr(info, data)   # ZipInfo preserves filename + timestamp
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(dst, buf.getvalue())
    return Renamed(rigs, slots, rig_payloads, slot_payloads)
