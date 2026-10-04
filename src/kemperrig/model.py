"""`Backup` — one Rig Manager library opened from any of its four forms: a `.rmbackup` zip,
the live directory, a dated snapshot, or a pack (layouts in docs/format.md). Which db is
which is decided here; rows become records in `_tables.py` and `_packs.py`. Nothing here
writes; `write_refusal` is the guard the three writers start from.
"""

from __future__ import annotations

import errno
import os
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kemperrig import _packs
from kemperrig._archive import open_zip, read_entry
from kemperrig._tables import (
    _BACKUP_SUFFIX,
    _DB_SUFFIX,
    _INFO,
    _LIB_PREFIX,
    _PERF_DB,
    _PRESET_PREFIX,
    _REPOSITORY_DB,
    _SNAPSHOT_DIR,
    _SNAPSHOT_NAME,
    _SNAPSHOT_SUFFIX,
    _SQLITE_MAGIC,
    _STAMP,
    _load_db,
    _read_info,
    _read_performances,
    _read_presets,
    _read_rigs,
    _snapshot,
)
from kemperrig.records import Info, Pack, Performance, Preset, Rig, Slot

__all__ = ["Backup", "Info", "Pack", "Performance", "Preset", "Rig", "Slot", "read_pack"]
_NO_INFO = Info(version=None, user=None)

# What `Backup.open` raises for a file Rig Manager did not write, or wrote only partly.
OPEN_ERRORS = (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile,
               sqlite3.DatabaseError, ET.ParseError)

def file_stamp(name: str) -> str | None:
    """`YYYY-MM-DD HH:MM:SS` from a snapshot's or backup's file name, if it carries one."""
    m = _STAMP.search(name)
    if not m:
        return None
    stamp = f"{m[1]} {m[2]}:{m[3]}:{m[4]}"
    try:
        datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return stamp


def snapshot_device(name: str) -> str | None:
    """The device id a dated snapshot's file name starts with; None for any other name."""
    m = _SNAPSHOT_NAME.fullmatch(name)
    return m[1] if m else None


def library_files(folder: str | Path) -> list[Path]:
    """The snapshots and backups directly inside `folder`, by name; dotfiles are skipped."""
    return sorted(f for f in Path(folder).iterdir()
                  if f.is_file() and not f.name.startswith(".")
                  and f.name.endswith((_SNAPSHOT_SUFFIX, _BACKUP_SUFFIX)))


def snapshot_dir(root: str | Path) -> Path:
    """The folder of dated snapshots inside a live Rig Manager directory."""
    path = Path(root) / _SNAPSHOT_DIR
    if not path.is_dir():
        raise ValueError(f"{root}: no {_SNAPSHOT_DIR}/ folder — not a live Rig Manager "
                         "directory; name the snapshots or backups to compare")
    return path


def read_pack(path: str | Path) -> Pack:
    """A rig or preset pack (`Rig Packs/*.rigpack`, `Preset Packs/*.presetpack`), told apart
    from a snapshot by its tables, not by its name."""
    data = Path(path).read_bytes()
    if data[:len(_SQLITE_MAGIC)] == _SQLITE_MAGIC:
        con = _load_db(data, str(path))
        try:
            if _packs.is_pack(con, str(path)):
                return _packs.read_pack(con, str(path))
        finally:
            con.close()
    raise ValueError(f"{path}: not a Rig Manager rig or preset pack")


# Folders only a Rig Manager library tree holds at its root.
_TREE_MARKERS = (_LIB_PREFIX.rstrip("/"), _PRESET_PREFIX.rstrip("/"), _PERF_DB.split("/")[0])


def library_root(path: str | Path) -> Path | None:
    """The Rig Manager library tree `path` lies in — the nearest of it and its ancestors that
    holds `Local Library/`, `Prst/`, `Prf/` or a `repositoryR2.db` — or None. `path` need not
    exist."""
    p = Path(path).resolve()
    for d in (p, *p.parents):
        if (d / _REPOSITORY_DB).is_file() or any((d / m).is_dir() for m in _TREE_MARKERS):
            return d
    return None


def within(path: Path, root: str | Path) -> bool:
    """`path` is `root` or lies under it, by file identity: case variants and symlinks count."""
    return any(d.exists() and os.path.samefile(d, root) for d in (path, *path.parents))


def is_same_file(a: str | Path, b: str | Path) -> bool:
    """True when two paths reach one file — case variants, symlinks and hardlinks included."""
    try:
        return os.path.samefile(a, b)
    except OSError:  # one does not exist yet, which is the normal case for an output
        return Path(a).resolve() == Path(b).resolve()


def _symlink_loop(path: str | Path) -> OSError | None:
    """The error a symlink loop on the way to `path` raises, or None. From Python 3.13 a
    non-strict `resolve()` returns a looping path instead of raising, so ask the filesystem."""
    try:
        os.stat(path)
    except OSError as e:
        if e.errno == errno.ELOOP:
            return e
    return None


def names_folder(target: str) -> bool:
    """`target` is a folder, or is spelled as one — `out/` — whether or not it exists."""
    return target.endswith(tuple(s for s in (os.sep, os.altsep) if s)) or os.path.isdir(target)


def write_refusal(target: str | Path, source: str, flag: str) -> str | None:
    """Why writing at `target` could reach `source` or a Rig Manager library, or None. Every
    writer runs this before its own checks; `flag` names the option in the message."""
    try:
        resolved = Path(target).resolve()
    except (RuntimeError, OSError) as e:   # a symlink loop, up to Python 3.12
        return f"cannot resolve {target}: {e}"
    if (loop := _symlink_loop(target)) is not None:
        return f"cannot resolve {target}: {loop.strerror}"
    if os.path.isfile(source) and is_same_file(target, source):
        return f"refusing to overwrite the source {source} — choose a different {flag}"
    if os.path.isdir(source) and within(resolved, source):
        return f"refusing to write inside the source {source} — choose a {flag} outside it"
    root = library_root(resolved)
    if root is not None:
        return (f"refusing to write inside the Rig Manager library at {root} — choose a "
                f"{flag} outside it")
    return None


def _mis_rooted(path: object) -> str:
    """Databases are present but none sat where the layout expects — almost always a path
    one level off, e.g. the parent of the Rig Manager tree rather than the tree itself."""
    return (f"{path}: repositoryR2.db files found, but none under '{_LIB_PREFIX}', "
            f"'{_PRESET_PREFIX}' or '{_PERF_DB}' — point at the Rig Manager library root")


def _folder(entry: str, prefix: str) -> str | None:
    if entry.startswith(prefix) and entry.endswith(_DB_SUFFIX):
        return entry[len(prefix):-len(_DB_SUFFIX)]
    return None


def rig_folder(entry: str) -> str | None:
    """The library folder whose rigs the db at `entry` (a path inside the tree) holds, or None
    when it holds none. The root folder is ''."""
    return _folder(entry, _LIB_PREFIX)


def preset_folder(entry: str) -> str | None:
    """The folder whose presets the db at `entry` holds, or None."""
    return _folder(entry, _PRESET_PREFIX)


def zip_layout_problem(path: str | Path, names: list[str]) -> str | None:
    """Why a zip holding the entries `names` is not a Rig Manager backup, or None."""
    if not any(n.endswith(_DB_SUFFIX) for n in names):
        return f"{path}: no repositoryR2.db inside — not a Rig Manager backup"
    if not any(n == _PERF_DB or rig_folder(n) is not None or preset_folder(n) is not None
               for n in names):
        return _mis_rooted(path)
    return None


@dataclass(frozen=True)
class Backup:
    info: Info
    rigs: list[Rig]
    performances: list[Performance]
    presets: list[Preset]

    @classmethod
    def open(cls, path: str) -> "Backup":
        """A .rmbackup zip, a live Rig Manager directory, a dated snapshot db, or a rig or
        preset pack — told apart by content, not by name."""
        if Path(path).is_dir():
            return cls.open_live(path)
        with open(path, "rb") as fh:
            head = fh.read(len(_SQLITE_MAGIC))
        if not head:
            raise ValueError(f"{path}: empty file — not a backup or snapshot")
        if head == _SQLITE_MAGIC:
            return cls._open_db(Path(path))
        with open_zip(path) as zf:
            names = zf.namelist()
            problem = zip_layout_problem(path, names)
            if problem:
                raise ValueError(problem)
            info = (_read_info(read_entry(zf, _INFO, path), f"{_INFO} in {path}")
                    if _INFO in names else _NO_INFO)
            rigs: list[Rig] = []
            presets: list[Preset] = []
            for entry in names:
                if (folder := rig_folder(entry)) is not None:
                    rigs.extend(_read_rigs(read_entry(zf, entry, path), folder,
                                           f"{entry} in {path}"))
                elif (folder := preset_folder(entry)) is not None:
                    presets.extend(_read_presets(read_entry(zf, entry, path), folder,
                                                 f"{entry} in {path}"))
            performances = (
                _read_performances(read_entry(zf, _PERF_DB, path), f"{_PERF_DB} in {path}")
                if _PERF_DB in names else []
            )
        return cls(info=info, rigs=rigs, performances=performances, presets=presets)

    @classmethod
    def _open_db(cls, path: Path) -> "Backup":
        """One bare SQLite db: a pack when it holds the pack tables, else a dated snapshot."""
        con = _load_db(path.read_bytes(), str(path))
        try:
            if _packs.is_pack(con, str(path)):
                return cls.from_pack(_packs.read_pack(con, str(path)))
            rigs, performances, presets = _snapshot(con, str(path))
        finally:
            con.close()
        return cls(info=_NO_INFO, rigs=rigs, performances=performances, presets=presets)

    @classmethod
    def from_pack(cls, pack: Pack) -> "Backup":
        """A pack's rigs or presets as a library of their own, with no folders."""
        return cls(info=_NO_INFO, rigs=pack.rigs, performances=[], presets=pack.presets)

    @classmethod
    def open_live(cls, root: str | Path) -> "Backup":
        """The live Rig Manager tree, read like the zip. Every db outside the rig, performance
        and preset locations (Rig Exchange caches, view prefs, nested Prf dbs) is ignored."""
        rootp = Path(root)
        if not any(rootp.rglob("repositoryR2.db")):
            raise FileNotFoundError(
                f"{rootp}: no repositoryR2.db found — not a Rig Manager library")
        rigs: list[Rig] = []
        presets: list[Preset] = []
        performances: list[Performance] = []
        matched = 0
        for db in sorted(rootp.rglob("repositoryR2.db")):
            entry = db.relative_to(rootp).as_posix()
            if entry == _PERF_DB:
                performances = _read_performances(db.read_bytes(), str(db))
            elif (folder := rig_folder(entry)) is not None:
                rigs.extend(_read_rigs(db.read_bytes(), folder, str(db)))
            elif (folder := preset_folder(entry)) is not None:
                presets.extend(_read_presets(db.read_bytes(), folder, str(db)))
            else:
                continue
            matched += 1
        if not matched:
            raise FileNotFoundError(_mis_rooted(rootp))
        return cls(info=_NO_INFO, rigs=rigs, performances=performances, presets=presets)
