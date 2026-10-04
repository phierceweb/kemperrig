"""Narrow a library to caller-supplied amp patterns, at a gain floor.

DI-only by default: with the cab held constant the comparison is one-variable.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from kemperrig.model import Rig
from kemperrig.services.filter import filter_rigs

_DEFAULT_GAIN_FLOOR = 5.0


def load_criteria(path: str | Path) -> dict:
    """Read and shape-check a criteria file (docs/criteria.md). It is the one file a user
    writes by hand, and the CLI boundary catches `ValueError`, not `TypeError` — an unchecked
    bare string would match `matches_amp` character by character."""
    with open(path, encoding="utf-8") as fh:
        crit = json.load(fh)
    if not isinstance(crit, dict):
        raise ValueError(f"{path}: top level must be an object, got {type(crit).__name__}")
    pats = crit.get("amp_patterns")
    if isinstance(pats, dict):
        crit["amp_families"] = pats
        pats = [p for group in pats.values() for p in _as_pattern_list(path, group)]
        crit["amp_patterns"] = pats
    else:
        crit["amp_patterns"] = pats = _as_pattern_list(path, pats)
    if not pats:
        raise ValueError(f"{path}: no amp_patterns")
    gain = crit.get("gain_min")
    if gain is not None and not isinstance(gain, (int, float)) or isinstance(gain, bool):
        raise ValueError(f"{path}: gain_min must be a number, got {type(gain).__name__}")
    if isinstance(gain, float) and not math.isfinite(gain):
        raise ValueError(f"{path}: gain_min must be a finite number, got {gain}")
    return crit


def _as_pattern_list(path: str | Path, value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        got = "a string" if isinstance(value, str) else type(value).__name__
        raise ValueError(f"{path}: amp_patterns must be a list of strings, got {got}")
    if any(not v.strip() for v in value):
        raise ValueError(f"{path}: amp_patterns holds an empty pattern, which would match "
                         "every amp")
    return value


def matches_amp(amp_model: str | None, patterns: tuple[str, ...] | list[str]) -> bool:
    text = (amp_model or "").lower()
    return any(tok.lower() in text for tok in patterns)


def shortlist(rigs: list[Rig], amp_patterns: tuple[str, ...] | list[str], *,
              gain_min: float = _DEFAULT_GAIN_FLOOR, di_only: bool = True) -> list[Rig]:
    """Rigs on matching amps at or above `gain_min`, sorted by gain descending then name.

    DI-only by default: holding the cab constant makes it a comparison of the profile alone."""
    candidates = filter_rigs(rigs, gain_min=gain_min, di=(True if di_only else None))
    picked = [r for r in candidates if matches_amp(r.amp_model, amp_patterns)]
    return sorted(picked, key=lambda r: (-(r.gain or 0.0), r.name))
