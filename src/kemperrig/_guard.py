"""Where a writer may write: never at its source, an alias of it, or inside any Rig Manager
library — decided by file identity, never by comparing path strings."""

from __future__ import annotations

import errno
import os
from pathlib import Path

from kemperrig._tables import _LIB_PREFIX, _PERF_DB, _PRESET_PREFIX, _REPOSITORY_DB

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
