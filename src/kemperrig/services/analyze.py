"""Curation checks over a library — orphans, coverage gaps, duplicates, the drive split, cab-IR
and effect use — cross-referencing what is already decoded."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from kemperrig import _sysex, _sysex_effects
from kemperrig.model import Backup, Performance, Rig
from kemperrig.services.performance import gain_ladder, rig_gain_index

_CLEAN_MAX = 3.0      # gain < 3.0 = clean/edge
_HIGH_MIN = 6.5       # gain > 6.5 = high-gain
_GAP_MIN_RIGS = 3     # fewer rigs of one amp is too few to call a missing band a gap


def _performance_rig_names(backup: Backup) -> set[str]:
    return {s.rig_name for p in backup.performances for s in p.slots if s.rig_name}


def orphaned_rigs(backup: Backup, *, rack_folder: str | None = None) -> list[Rig]:
    """Rigs no performance references. Rigs in `rack_folder` (pulled off the Profiler) count as
    in use; there is no default, because the folder is a filing convention."""
    used = _performance_rig_names(backup)
    return [r for r in backup.rigs
            if r.name not in used and (rack_folder is None or r.folder != rack_folder)]


@dataclass(frozen=True)
class AmpCoverage:
    count: int
    gain_min: float | None
    gain_max: float | None
    has_clean: bool
    has_mid: bool
    has_high: bool


def amp_coverage(backup: Backup) -> dict[str, AmpCoverage]:
    """Per amp model: how many rigs and whether the clean / mid / high gain bands are covered."""
    by_amp: dict[str, list[float]] = {}
    counts: Counter[str] = Counter()
    for r in backup.rigs:
        if not r.amp_model:
            continue
        counts[r.amp_model] += 1
        if r.gain is not None:
            by_amp.setdefault(r.amp_model, []).append(r.gain)
    out = {}
    for amp, n in counts.items():
        gains = by_amp.get(amp, [])
        out[amp] = AmpCoverage(
            count=n,
            gain_min=min(gains) if gains else None,
            gain_max=max(gains) if gains else None,
            has_clean=any(g < _CLEAN_MAX for g in gains),
            has_mid=any(_CLEAN_MAX <= g <= _HIGH_MIN for g in gains),
            has_high=any(g > _HIGH_MIN for g in gains),
        )
    return out


def _grouped(keyed: Iterable[tuple[Rig, object]]) -> list[list[Rig]]:
    groups: dict[object, list[Rig]] = {}
    for r, k in keyed:
        if k is not None:
            groups.setdefault(k, []).append(r)
    return [g for g in groups.values() if len(g) > 1]


def similar_groups(backup: Backup) -> list[list[Rig]]:
    """Rigs sharing author, amp model, gain and boost state — a prompt to listen, not evidence
    of a duplicate. A rig with no amp model or gain is unknown, so it is left out."""
    return _grouped((r, None if r.amp_model is None or r.gain is None
                     else (r.author, r.amp_model, r.gain, r.is_boosted)) for r in backup.rigs)


_Tracks = list[list[_sysex.Message]]


@dataclass(frozen=True)
class Payloads:
    """Every rig and performance payload, parsed once; None for one that does not parse."""
    rigs: list[tuple[Rig, _Tracks | None]]
    performances: list[tuple[Performance, _Tracks | None]]


def payloads(backup: Backup) -> Payloads:
    return Payloads([(r, _sysex.parse_tracks(r.blob)) for r in backup.rigs],
                    [(p, _sysex.parse_performance(p.blob)) for p in backup.performances])


def _messages(tracks: _Tracks) -> list[_sysex.Message]:
    return [m for t in tracks for m in t]


def identical_amp_groups(found: Payloads) -> list[list[Rig]]:
    """Rigs whose amp-definition blocks are byte-identical — the same amp at the same
    settings, whatever effects are wrapped around it. Evidence, not inference."""
    return _grouped((r, _sysex.amp_block(_messages(t)) if t else None) for r, t in found.rigs)


def identical_profiles(backup: Backup) -> list[list[Rig]]:
    """Rigs whose whole payload is byte-identical — the same file stored twice."""
    return _grouped((r, hashlib.sha256(r.blob).digest() if r.blob else None)
                    for r in backup.rigs)


def drive_breakdown(backup: Backup) -> dict[str, int]:
    """Counts of boosted / unboosted / unknown across the library (from Amp Comment)."""
    out = {"boosted": 0, "unboosted": 0, "unknown": 0}
    for r in backup.rigs:
        b = r.is_boosted
        out["boosted" if b else "unboosted" if b is False else "unknown"] += 1
    return out


def ir_inventory(found: Payloads) -> list[tuple[str, int]]:
    """Cab-IR `.wav` filenames loaded across rig + performance blobs, most common first."""
    counter: Counter[str] = Counter()
    for _, tracks in [*found.rigs, *found.performances]:
        if tracks:
            counter.update(_sysex.ir_files(_sysex.decode_strings(_messages(tracks))))
    return counter.most_common()


def effect_categories(found: Payloads) -> list[tuple[str, int]]:
    """How many module slots each effect category fills, most-used first. Categories come
    from the same runtime table as the names, so this is empty without one."""
    counter: Counter[str] = Counter()
    for _, tracks in found.rigs:
        for e in _sysex_effects.effect_chain(_messages(tracks or [])):
            if e.category and e.category != "-":
                counter[e.category] += 1
    return counter.most_common()


@dataclass(frozen=True)
class Unparsed:
    rigs: list[Rig]
    performances: list[Performance]


def unparsed(found: Payloads) -> Unparsed:
    """Rigs and performances whose payload does not parse. Every decode here skips them;
    `doctor` says what is wrong with each."""
    return Unparsed(rigs=[r for r, t in found.rigs if t is None],
                    performances=[p for p, t in found.performances if t is None])


def non_monotonic_performances(backup: Backup) -> list[tuple[Performance, list[float | None]]]:
    """Performances whose resolved gain ladder is not non-decreasing (clean→hi out of order or
    with a backward step) — candidates to re-order the slots."""
    index = rig_gain_index(backup.rigs)
    out = []
    for p in backup.performances:
        ladder = gain_ladder(p, index)
        known = [g for g in ladder if g is not None]
        if len(known) >= 2 and any(a > b for a, b in zip(known, known[1:], strict=False)):
            out.append((p, ladder))
    return out


@dataclass(frozen=True)
class Analysis:
    """Every analysis of one library, taken once for the text view, `--json` and `--strict`."""
    user: str | None
    rigs: int
    rack_folder: str | None
    orphans: list[Rig]
    coverage: dict[str, AmpCoverage]
    similar: list[list[Rig]]
    identical_amps: list[list[Rig]]
    identical_profiles: list[list[Rig]]
    drive: dict[str, int]
    effect_categories: list[tuple[str, int]]
    ir_inventory: list[tuple[str, int]]
    misordered: list[tuple[Performance, list[float | None]]]
    unparsed: Unparsed

    @property
    def coverage_gaps(self) -> dict[str, AmpCoverage]:
        """Amps with enough rigs to judge that have no clean rig or no high-gain one."""
        return {amp: c for amp, c in self.coverage.items()
                if c.count >= _GAP_MIN_RIGS and not (c.has_clean and c.has_high)}

    @property
    def actionable(self) -> bool:
        """What `--strict` fails on. Similar metadata is a prompt to listen, not a defect —
        gating on it would fail every library holding two profiles of one amp."""
        return bool(self.orphans or self.identical_profiles or self.misordered
                    or self.unparsed.rigs or self.unparsed.performances)


def analysis(backup: Backup, *, rack_folder: str | None = None) -> Analysis:
    found = payloads(backup)
    return Analysis(
        user=backup.info.user, rigs=len(backup.rigs), rack_folder=rack_folder,
        orphans=orphaned_rigs(backup, rack_folder=rack_folder),
        coverage=amp_coverage(backup), similar=similar_groups(backup),
        identical_amps=identical_amp_groups(found),
        identical_profiles=identical_profiles(backup), drive=drive_breakdown(backup),
        effect_categories=effect_categories(found), ir_inventory=ir_inventory(found),
        misordered=non_monotonic_performances(backup), unparsed=unparsed(found))
