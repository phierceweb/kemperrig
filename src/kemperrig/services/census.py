"""A library census — `summary`'s numbers plus the anchors a golden test compares against —
and the third writer, which saves one to a file.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pw_foundation.utils.io import atomic_write_bytes

from kemperrig import _sysex, _sysex_effects
from kemperrig._guard import names_folder, write_refusal
from kemperrig.model import Backup, Performance, Rig
from kemperrig.services.diff import digest
from kemperrig.services.doctor import Checkup, checkup
from kemperrig.services.performance import gain_ladder, rig_gain_index, slot_tracks
from kemperrig.services.report import LibraryReport, build_report


@dataclass(frozen=True)
class ProfileType:
    """Rigs of one Profile Type and how many decode an amp gain. `folders` names where they
    are filed for every type but the library's most common, which is None."""
    rigs: int
    gain_decoded: int
    folders: list[str] | None = None


@dataclass(frozen=True)
class SampleRig:
    rig: Rig
    first_strings: list[str]
    amp_gain: float | None
    effects: dict[str, int]              # module slot -> effect type value


@dataclass(frozen=True)
class SamplePerformance:
    performance: Performance
    tracks: int
    locked: int
    compared: int
    ratio: float | None
    cab_ir: str | None
    gain_ladder: list[float | None]


@dataclass(frozen=True)
class Census:
    user: str | None
    report: LibraryReport
    checkup: Checkup
    presets: int
    gain_decoded: int
    profile_types: dict[str | None, ProfileType]
    effects: dict[str, int]              # module slot -> rigs with an effect loaded there
    effects_undecoded: dict[str, int]    # module slot -> rigs whose block there is undecoded
    rig: SampleRig | None
    performance: SamplePerformance | None


def _order(name: str, folder: str, blob: bytes) -> tuple[str, str, str]:
    return name, folder, digest(blob) or ""


def _profile_types(gains: list[tuple[Rig, float | None]]) -> dict[str | None, ProfileType]:
    by_type: dict[str | None, list[tuple[Rig, float | None]]] = {}
    for r, g in gains:
        by_type.setdefault(r.profile_type, []).append((r, g))
    common = min(by_type, key=lambda t: (-len(by_type[t]), t is None, t or ""), default=None)
    return {t: ProfileType(rigs=len(rs), gain_decoded=sum(g is not None for _, g in rs),
                           folders=None if t == common else sorted({r.folder for r, _ in rs}))
            for t, rs in by_type.items()}


def _sample_rig(parsed: list[tuple[Rig, list[_sysex.Message]]]) -> SampleRig | None:
    found = [(r, m) for r, m in parsed if m]
    if not found:
        return None
    rig, messages = min(found, key=lambda rm: _order(rm[0].name, rm[0].folder, rm[0].blob))
    return SampleRig(rig, _sysex.decode_strings(messages)[:3], _sysex.amp_gain(messages),
                     {e.slot: e.type_value for e in _sysex_effects.effect_chain(messages)})


def _sample_performance(backup: Backup) -> SamplePerformance | None:
    found = [(p, t) for p in backup.performances if (t := _sysex.parse_performance(p.blob))]
    if not found:
        return None
    perf, tracks = min(found, key=lambda pt: _order(pt[0].name, "", pt[0].blob))
    locked, compared, ratio = _sysex.effects_locked(slot_tracks(perf, tracks))
    wavs = _sysex.ir_files(_sysex.decode_strings([m for t in tracks for m in t]))
    return SamplePerformance(perf, len(tracks), locked, compared, ratio,
                             wavs[0] if wavs else None,
                             gain_ladder(perf, rig_gain_index(backup.rigs)))


def take(backup: Backup) -> Census:
    """Count what `summary` counts plus the census-only anchors. A payload that does not
    parse decodes nothing and is never a sample; `doctor` counts it as broken."""
    parsed = [(r, _sysex.parse_messages(r.blob) or []) for r in backup.rigs]
    gains = [(r, _sysex.amp_gain(m)) for r, m in parsed]
    chains = [e for _, m in parsed for e in _sysex_effects.effect_chain(m)]
    return Census(
        user=backup.info.user,
        report=build_report(backup),
        checkup=checkup(backup),
        presets=len(backup.presets),
        gain_decoded=sum(g is not None for _, g in gains),
        profile_types=_profile_types(gains),
        effects=dict(Counter(e.slot for e in chains if e.decoded)),
        effects_undecoded=dict(Counter(e.slot for e in chains if not e.decoded)),
        rig=_sample_rig(parsed),
        performance=_sample_performance(backup),
    )


_COMMENT_SOURCE_MAX = 1 << 20


def existing_comment(path: str | Path) -> str | None:
    """The `_comment` of a census already at `path`, which `--force` keeps; None unless
    `path` is a regular file of at most 1 MiB holding a census whose comment is text."""
    target = Path(path)
    try:
        if not target.is_file() or target.stat().st_size > _COMMENT_SOURCE_MAX:
            return None
        doc = json.loads(target.read_text(encoding="utf-8"))
        comment = doc.get("_comment") if isinstance(doc, dict) and "census" in doc else None
        if isinstance(comment, str):
            comment.encode("utf-8")   # a lone surrogate parses but cannot be written back
            return comment
    except (OSError, ValueError, RecursionError):   # UnicodeError is a ValueError
        pass
    return None


def refusal(path: str | Path, *, source: str, force: bool) -> str | None:
    """Why writing a census to `path` is unsafe, or None when it is not."""
    if not str(path).strip():
        return "no census file named"
    target = Path(path)
    why = write_refusal(target, source, "path")
    if why:
        return why
    if names_folder(str(path)):
        return f"{path} is a folder — name a file"
    if os.path.lexists(target) and not force:
        return f"{target} already exists — choose a different path, or pass --force"
    return None


def write(text: str, path: str | Path, *, source: str, force: bool) -> None:
    """Write `text` to `path`, creating its folder. Checks `refusal` first and raises
    ValueError on it, before anything is written."""
    why = refusal(path, source=source, force=force)
    if why:
        raise ValueError(why)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, text.encode("utf-8"))
