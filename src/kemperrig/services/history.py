"""A library across dated snapshots and backups: what changed from one file to the next.

Files are opened one at a time and reduced to diff fingerprints, and each is compared with
the previous file from the same device; docs/capabilities.md has the rules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from kemperrig.model import (
    OPEN_ERRORS,
    Backup,
    file_stamp,
    library_files,
    snapshot_device,
)
from kemperrig.services.diff import KINDS, Diff, Fingerprint, compare, digest, fingerprints

ORDERS = ("name", "mtime")


@dataclass(frozen=True)
class Source:
    path: str
    label: str              # the date-time in the file name, else the file name
    device: str | None      # a snapshot's device id; None for any other file
    stamp: str | None = None


@dataclass(frozen=True)
class Counts:
    added: int
    removed: int
    changed: int


@dataclass(frozen=True)
class Step:
    since: Source
    counts: dict[str, Counts]    # per kind in `KINDS`


@dataclass(frozen=True)
class Entry:
    source: Source
    totals: dict[str, int]       # per kind in `KINDS`
    step: Step | None            # None for the first readable file of its device
    empty: bool = False          # no rows at all: shown, but never a baseline


@dataclass(frozen=True)
class Sighting:
    source: Source
    versions: list[int]          # 1-based into `RigHistory.versions`
    changed: bool                # versions differ from the device's previous sighting


@dataclass(frozen=True)
class Version:
    digest: str | None
    first: Source
    last: Source
    count: int


@dataclass(frozen=True)
class RigHistory:
    name: str
    sightings: list[Sighting]
    versions: list[Version]
    first: Source | None = None
    last: Source | None = None


@dataclass(frozen=True)
class History:
    order: str
    entries: list[Entry]
    skipped: list[tuple[str, str]]   # (path, reason)
    rig: RigHistory | None = None


def describe(path: str) -> Source:
    name = os.path.basename(path)
    stamp = file_stamp(name)
    return Source(path=path, label=stamp or name, device=snapshot_device(name), stamp=stamp)


def _in_time(sources: list[Source]) -> list[Source]:
    """By the file names' date-times; in listing order when any lacks one — a name-ordered
    listing groups devices, so it is not a time order."""
    if all(s.stamp for s in sources):
        return sorted(sources, key=lambda s: s.stamp)
    return list(sources)


def collect(paths: list[str]) -> list[str]:
    """Directories expand to the snapshots and backups directly inside them; a file reached
    twice is read once."""
    out: list[str] = []
    for p in paths:
        if not p.strip():
            raise ValueError("a SOURCE is blank")
        if Path(p).is_dir():
            found = library_files(p)
            if not found:
                raise ValueError(f"{p}: no snapshots (*R2.db) or backups (*.rmbackup) in it")
            out += [str(f) for f in found]
        elif Path(p).exists():
            out.append(p)
        else:
            raise FileNotFoundError(f"{p}: no such file or directory")
    unique: dict[Path, str] = {}
    for p in out:
        unique.setdefault(Path(p).resolve(), p)
    return list(unique.values())


def _sorted(paths: list[str], order: str) -> list[str]:
    if order == "name":
        return sorted(paths, key=lambda p: (os.path.basename(p), p))
    if order == "mtime":
        return sorted(paths, key=lambda p: (os.stat(p).st_mtime, os.path.basename(p)))
    raise ValueError(f"unknown order {order!r} — use one of {', '.join(ORDERS)}")


def _reason(e: Exception, path: str) -> str:
    text = str(e)
    return text.removeprefix(f"{path}: ")


def _counts(d: Diff) -> Counts:
    return Counts(len(d.added), len(d.removed), len(d.changed))


def history(paths: list[str], *, order: str = "name", rig: str | None = None) -> History:
    """The timeline over `paths` (files, or directories of them) in `order`; with `rig`,
    also every file holding a rig of that exact name and each version of its payload."""
    entries: list[Entry] = []
    skipped: list[tuple[str, str]] = []
    sightings: list[tuple[Source, list[str | None]]] = []
    last: dict[str | None, tuple[Source, dict[str, dict[str, list[Fingerprint]]]]] = {}
    for path in _sorted(collect(paths), order):
        source = describe(path)
        try:
            backup = Backup.open(path)
        except OPEN_ERRORS as e:
            skipped.append((path, _reason(e, path)))
            continue
        prints = {kind: fingerprints(backup, kind) for kind in KINDS}
        totals = {kind: len(getattr(backup, kind)) for kind in KINDS}
        if rig is not None:
            found = [digest(r.blob) for r in backup.rigs if r.name == rig]
            if found:
                sightings.append((source, found))
        del backup
        if not any(totals.values()):
            entries.append(Entry(source, totals, None, empty=True))
            continue
        step = None
        if source.device in last:
            since, before = last[source.device]
            step = Step(since, {k: _counts(compare(k, before[k], prints[k])) for k in KINDS})
        last[source.device] = (source, prints)
        entries.append(Entry(source, totals, step))
    return History(order=order, entries=entries, skipped=skipped,
                   rig=None if rig is None else _rig_history(rig, sightings))


def _rig_history(name: str, seen: list[tuple[Source, list[str | None]]]) -> RigHistory:
    """Versions are distinct payload digests, numbered by when each was first seen."""
    holders: dict[str | None, list[Source]] = {}
    for source, digests in seen:
        for d in dict.fromkeys(digests):
            holders.setdefault(d, []).append(source)
    timeline = _in_time([source for source, _ in seen])
    rank = {source: n for n, source in enumerate(timeline)}
    ranked = sorted(holders, key=lambda d: min(rank[s] for s in holders[d]))
    number = {d: n for n, d in enumerate(ranked, 1)}
    previous: dict[str | None, list[int]] = {}
    sightings: list[Sighting] = []
    for source, digests in seen:
        held = sorted({number[d] for d in digests})
        changed = source.device in previous and previous[source.device] != held
        previous[source.device] = held
        sightings.append(Sighting(source, held, changed))
    versions = []
    for d in ranked:
        span = _in_time(holders[d])
        versions.append(Version(d, span[0], span[-1], len(span)))
    return RigHistory(name=name, sightings=sightings, versions=versions,
                      first=timeline[0] if timeline else None,
                      last=timeline[-1] if timeline else None)
