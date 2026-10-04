"""Referential integrity: slot names that resolve to no rig or to several, and payloads that
are broken or disagree with their own metadata. A payload that does not parse is reported
once, as broken, and skipped by every other check."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from kemperrig import _sysex
from kemperrig.model import Backup, Preset, Rig
from kemperrig.services.diff import digest


@dataclass(frozen=True)
class SlotRef:
    performance: str
    slot: int
    rig_name: str


@dataclass(frozen=True)
class AmbiguousSlot:
    slot: SlotRef
    rigs: list[Rig]


@dataclass(frozen=True)
class BrokenPayload:
    kind: str               # "rig", "performance" or "preset"
    name: str
    folder: str | None      # None for a performance
    problem: str


@dataclass(frozen=True)
class UnreadPayload:
    """A payload that parses but holds track bytes that are not SysEx events."""
    kind: str
    name: str
    folder: str | None
    tracks: list[tuple[int, int, int]]   # (track, unread bytes, track size)


@dataclass(frozen=True)
class GainMismatch:
    rig: Rig
    decoded: float


@dataclass(frozen=True)
class NameMismatch:
    """A library row and its payload naming the rig differently; `rig` or `slot` says where."""
    payload: str
    rig: Rig | None = None
    slot: SlotRef | None = None


def _slots(backup: Backup) -> Iterator[tuple[SlotRef, list[_sysex.Message] | None]]:
    """Every named slot, with its own track when the performance payload has one."""
    for p in backup.performances:
        found = _sysex.parse_performance(p.blob) or []
        for s in p.slots:
            track = found[s.index] if s.index < len(found) else None
            yield SlotRef(p.name, s.index, s.rig_name), track


def _rigs_by_name(backup: Backup) -> dict[str, list[Rig]]:
    out: dict[str, list[Rig]] = {}
    for r in backup.rigs:
        out.setdefault(r.name, []).append(r)
    return out


def dangling_slots(backup: Backup) -> list[SlotRef]:
    """Slots whose rig name no library rig has — the rig they were built from is gone."""
    names = _rigs_by_name(backup)
    return [ref for ref, _ in _slots(backup) if ref.rig_name not in names]


def ambiguous_slots(backup: Backup) -> list[AmbiguousSlot]:
    """Slots whose rig name is held by rigs with different payloads, so which of them the
    slot came from is undefined. Identical copies under one name are not ambiguous."""
    names = _rigs_by_name(backup)
    return [AmbiguousSlot(ref, names[ref.rig_name]) for ref, _ in _slots(backup)
            if len({digest(r.blob) for r in names.get(ref.rig_name, [])}) > 1]


def _examine(kind: str, blob: bytes) -> tuple[str | None, list[tuple[int, int, int]]]:
    """What is wrong with a payload, or None; and, when nothing is, its unread tracks."""
    if not blob:
        return "empty payload", []
    try:
        found, unread = _sysex.walk(blob, performance=kind == "performance")
    except ValueError as e:
        return str(e), []
    if not any(m.is_kemper for t in found for m in t):
        return "no Kemper SysEx", []
    return None, unread


def _payloads(backup: Backup) -> list[tuple[str, str, str | None, bytes]]:
    return ([("rig", r.name, r.folder, r.blob) for r in backup.rigs]
            + [("performance", p.name, None, p.blob) for p in backup.performances]
            + [("preset", p.name, p.folder, p.blob) for p in backup.presets])


def payload_findings(backup: Backup) -> tuple[list[BrokenPayload], list[UnreadPayload]]:
    """Rigs, performances and presets whose payload is broken — empty, does not parse, or
    holds no Kemper SysEx, so nothing the Profiler could load — and those that parse but
    carry track bytes no decoder reads: damage, or an encoding nothing here decodes."""
    broken, unread = [], []
    for kind, name, folder, blob in _payloads(backup):
        problem, tracks = _examine(kind, blob)
        if problem is not None:
            broken.append(BrokenPayload(kind, name, folder, problem))
        elif tracks:
            unread.append(UnreadPayload(kind, name, folder, tracks))
    return broken, unread


def gain_mismatches(backup: Backup) -> list[GainMismatch]:
    """Rigs whose decoded amp gain and stored Gain differ by more than display rounding."""
    out = []
    for r in backup.rigs:
        messages = _sysex.parse_messages(r.blob)
        decoded = _sysex.amp_gain(messages) if messages else None
        if (decoded is not None and r.gain is not None
                and abs(decoded - r.gain) > _sysex.GAIN_TOLERANCE):
            out.append(GainMismatch(r, decoded))
    return out


def _differs(stored: str, payload: str | None) -> bool:
    return payload is not None and payload.strip() != stored.strip()


def name_mismatches(backup: Backup) -> list[NameMismatch]:
    """Rigs and slots whose name in the library differs from the name their payload carries,
    which is the one the Profiler shows."""
    out = []
    for r in backup.rigs:
        payload = _sysex.rig_name(_sysex.parse_messages(r.blob) or [])
        if _differs(r.name, payload):
            out.append(NameMismatch(payload, rig=r))
    for ref, track in _slots(backup):
        payload = _sysex.rig_name(track or [])
        if _differs(ref.rig_name, payload):
            out.append(NameMismatch(payload, slot=ref))
    return out


def _loaded_cabs(backup: Backup) -> set[str]:
    tracks = [t for r in backup.rigs for t in _sysex.parse_tracks(r.blob) or []]
    tracks += [t for _, t in _slots(backup) if t is not None]
    return {name for t in tracks if (name := _sysex.cab_name(t))}


def unused_cab_irs(backup: Backup) -> list[Preset]:
    """Cab-IR presets no rig or performance slot loads, matched on the cab name the preset
    and every track loading it carry. A preset whose own name does not decode is left out."""
    loaded = _loaded_cabs(backup)
    return [p for p in backup.presets if p.is_cab_ir
            and (name := _sysex.cab_name(_sysex.parse_messages(p.blob) or []))
            and name not in loaded]


@dataclass(frozen=True)
class Checkup:
    """Every check over one library. `defective` covers only the definite findings."""
    rigs: int
    performances: int
    slots: int
    cab_irs: int
    dangling: list[SlotRef]
    device_only: list[SlotRef] | None     # None when no device backup was checked
    ambiguous: list[AmbiguousSlot]
    broken: list[BrokenPayload]
    unread: list[UnreadPayload]
    gain_mismatches: list[GainMismatch]
    name_mismatches: list[NameMismatch]
    unused_cab_irs: list[Preset]

    @property
    def defective(self) -> bool:
        return bool(self.dangling or self.ambiguous or self.broken)


def checkup(backup: Backup, *, device: Backup | None = None) -> Checkup:
    """Run every check. With `device`, a dangling slot whose rig that backup holds is on the
    device only rather than gone."""
    dangling = dangling_slots(backup)
    broken, unread = payload_findings(backup)
    on_device = {r.name for r in device.rigs} if device is not None else set()
    return Checkup(
        rigs=len(backup.rigs), performances=len(backup.performances),
        slots=sum(len(p.slots) for p in backup.performances),
        cab_irs=sum(1 for p in backup.presets if p.is_cab_ir),
        dangling=[s for s in dangling if s.rig_name not in on_device],
        device_only=(None if device is None
                     else [s for s in dangling if s.rig_name in on_device]),
        ambiguous=ambiguous_slots(backup), broken=broken, unread=unread,
        gain_mismatches=gain_mismatches(backup), name_mismatches=name_mismatches(backup),
        unused_cab_irs=unused_cab_irs(backup))
