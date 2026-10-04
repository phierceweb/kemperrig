"""Performance-level figures: each slot's gain, read from the library rig its name resolves
to rather than from the slot's own copy of the rig, and how much of their effects the slots
share.
"""

from __future__ import annotations

from kemperrig import _sysex
from kemperrig.model import Performance, Rig


def rig_gain_index(rigs: list[Rig]) -> dict[str, float | None]:
    """Map rig name -> gain. A name shared by rigs of differing gain is ambiguous -> None."""
    seen: dict[str, set[float | None]] = {}
    for r in rigs:
        seen.setdefault(r.name, set()).add(r.gain)
    return {name: (next(iter(gains)) if len(gains) == 1 else None)
            for name, gains in seen.items()}


def gain_ladder(perf: Performance, gain_index: dict[str, float | None]) -> list[float | None]:
    """Per-slot amp gain (the Clean→Hi ladder), one entry per slot. None where the slot's rig
    isn't found or its name is ambiguous."""
    return [gain_index.get(s.rig_name) for s in perf.slots]


def slot_tracks(perf: Performance, tracks: list[list[_sysex.Message]]
                ) -> list[list[_sysex.Message]]:
    """The payload tracks of the slots `perf` uses, in slot order; track n holds slot n."""
    return [tracks[s.index] for s in perf.slots if s.index < len(tracks)]


def locked_ratio(perf: Performance) -> float | None:
    """The share of the first used slot's parameter messages every other used slot repeats.
    None when the payload does not parse or fewer than two slots can be compared."""
    found = _sysex.parse_performance(perf.blob)
    return None if found is None else _sysex.effects_locked(slot_tracks(perf, found))[2]
