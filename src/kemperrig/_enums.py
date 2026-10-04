"""Effect-type names, read at runtime from Rig Manager's own `Stomps.xml` — the names are
Kemper's, so none are vendored beyond a small set verified independently (each preset's
blob paired with the type name its own metadata carries). The CLI calls `install()` once;
everything else reads `tables()`."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# The Rig Manager install ships this; the file is latin-1, not UTF-8.
DEFAULT_PATH = "/Applications/Rig Manager.app/Contents/Resources/Stomps.xml"
_ENCODING = "iso-8859-1"

# Verified by decoding preset blobs and reading the type name from the same preset's
# metadata row — 12 pairs, no conflicts, and every one also agrees with Stomps.xml.
FALLBACK_TYPES: dict[int, str] = {
    33: "Green Scream", 38: "Kemper Fuzz", 97: "Graphic Equalizer", 98: "Studio Equalizer",
    113: "Treble Booster", 114: "Lead Booster", 146: "Single Delay", 147: "Dual Delay",
    164: "Quad Delay", 177: "Legacy Reverb", 178: "Natural Reverb", 181: "Cirrus Reverb",
}


@dataclass(frozen=True)
class Tables:
    types: dict[int, str] = field(default_factory=dict)
    categories: dict[int, str] = field(default_factory=dict)
    legacy_reverb: dict[int, str] = field(default_factory=dict)   # index-based, pre-OS-7 REV


def _valued(body: str) -> dict[int, str]:
    return {int(v): n.strip() for v, n in re.findall(r'<entry value="(\d+)">([^<]*)</entry>', body)}


def _indexed(body: str) -> dict[int, str]:
    """Entries with no value attribute — position is the value."""
    return {i: n.strip() for i, n in enumerate(re.findall(r"<entry>([^<]*)</entry>", body))}


def _list_body(raw: str, list_id: str) -> str:
    m = re.search(rf'<list id="{list_id}"[^>]*>(.*?)</list>', raw, re.S | re.I)
    return m.group(1) if m else ""


def load(path: str | Path | None) -> Tables:
    """Parse the table at `path`. An absent or unparseable file yields the fallback rather
    than raising — a missing Rig Manager is a degraded result, not a failure."""
    fallback = Tables(types=dict(FALLBACK_TYPES))
    if not path:
        return fallback
    try:
        raw = Path(path).read_text(encoding=_ENCODING)
    except OSError:
        return fallback
    types = _valued(_list_body(raw, "Types"))
    if not types:
        return fallback
    return Tables(types=types,
                  categories=_valued(_list_body(raw, "CategoryList")),
                  legacy_reverb=_indexed(_list_body(raw, "legacyreverbtypelist")))


_TABLES = Tables(types=dict(FALLBACK_TYPES))


def install(path: str | Path | None) -> Tables:
    """Set the table every decode reads. `None` restores the built-in fallback."""
    global _TABLES
    _TABLES = load(path)
    return _TABLES


def tables() -> Tables:
    return _TABLES


def use_effect_names(path: str | Path | None = DEFAULT_PATH) -> int:
    """Name effects in every later decode from the `Stomps.xml` at `path` — by default the one
    a standard Rig Manager install ships. None, or a file that is absent or unreadable, leaves
    the built-in subset. Returns how many effect types are named."""
    return len(install(path).types)
