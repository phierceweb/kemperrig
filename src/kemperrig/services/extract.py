"""`extract`: write rigs as standalone `.krig` files, verbatim — a stored payload is the
`.krig`. `write` re-runs `refusal` itself, and nothing is ever deleted."""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pf_core.utils.io import atomic_write_bytes

from kemperrig import _sysex
from kemperrig.model import Rig, is_same_file, write_refusal

SUFFIX = ".krig"
_MAX_STEM_BYTES = 200
_UNSAFE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
# Windows reserves these device names whatever the extension.
_DEVICE = re.compile(r"(con|prn|aux|nul|com[0-9]|lpt[0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class Planned:
    """One selected rig and the file it becomes; `file` is None when it is skipped."""
    rig: Rig
    file: str | None
    skipped: str | None = None


def file_name(name: str) -> str:
    """`name` as a portable file name: path separators, control and Windows-reserved
    characters become `_`, leading dots and edge spaces go, the length is capped."""
    stem = _UNSAFE.sub("_", unicodedata.normalize("NFC", name)).strip().lstrip(".")
    stem = stem.encode()[:_MAX_STEM_BYTES].decode("utf-8", "ignore").strip().rstrip(" .")
    if _DEVICE.fullmatch(stem.split(".", 1)[0]):
        stem = "_" + stem
    return (stem or "rig") + SUFFIX


def _key(file: str) -> str:
    """Names one file on a case- and normalisation-insensitive filesystem."""
    return unicodedata.normalize("NFC", file).casefold()


def plan(rigs: list[Rig]) -> list[Planned]:
    """Each rig's file, by folder, name and payload so the names never depend on storage
    order; a name already taken gets ` (2)`, ` (3)`, … A rig with no payload, or one that does
    not parse, is skipped."""
    ordered = sorted(rigs, key=lambda r: (r.folder, r.name, hashlib.sha256(r.blob).digest()))
    used: set[str] = set()
    out = []
    for rig in ordered:
        if not rig.blob:
            out.append(Planned(rig, None, "empty payload"))
            continue
        if _sysex.parse_tracks(rig.blob) is None:
            out.append(Planned(rig, None, "payload does not parse"))
            continue
        file = file_name(rig.name)
        n = 1
        while _key(file) in used:
            n += 1
            file = f"{file_name(rig.name)[:-len(SUFFIX)]} ({n}){SUFFIX}"
        used.add(_key(file))
        out.append(Planned(rig, file))
    return out


def refusal(out_dir: str | Path, *, source: str, planned: list[Planned],
            force: bool) -> str | None:
    """Why writing `planned` into `out_dir` is unsafe, or None when it is not."""
    if not str(out_dir).strip():
        return "-o names no folder"
    out = Path(out_dir)
    why = write_refusal(out, source, "-o")
    if why:
        return why
    if out.exists() and not out.is_dir():
        return f"{out} exists and is not a folder — choose a different -o"
    targets = [out / p.file for p in planned if p.file]
    for t in targets:
        if t.exists() and os.path.exists(source) and is_same_file(t, source):
            return f"refusing to overwrite the source {source} — choose a different -o"
        if t.is_dir():
            return f"{t} exists and is not a file — choose a different -o"
    existing = [t for t in targets if os.path.lexists(t)]
    if existing and not force:
        return (f"{len(existing)} file(s) already in {out}, e.g. {existing[0].name} — "
                "choose a different -o, or pass --force")
    return None


def write(planned: list[Planned], out_dir: str | Path, *, source: str, force: bool) -> int:
    """Write every planned file into `out_dir`, creating it when there is something to write.
    Checks `refusal` first and raises ValueError on it, before anything is written."""
    why = refusal(out_dir, source=source, planned=planned, force=force)
    if why:
        raise ValueError(why)
    todo = [p for p in planned if p.file]
    if todo:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    for p in todo:
        atomic_write_bytes(Path(out_dir) / p.file, p.rig.blob)
    return len(todo)
