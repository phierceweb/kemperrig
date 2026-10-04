"""One rig's payload decoded for display: its amp gain, effect chain, cab IR and strings."""

from __future__ import annotations

from dataclasses import dataclass

from kemperrig import _sysex, _sysex_effects
from kemperrig.model import Rig


def rig_messages(rig: Rig) -> list[_sysex.Message]:
    """The rig's payload messages; one that does not parse is a ValueError naming the rig."""
    try:
        return _sysex.iter_messages(rig.blob)
    except ValueError as e:
        raise ValueError(f"rig {rig.path!r}: {e}") from e


@dataclass(frozen=True)
class RigDetail:
    rig: Rig
    amp_gain: float | None
    effects: list[_sysex_effects.Effect]
    cab_ir: str | None          # the first `.wav` among the strings
    strings: list[str]


def _detail(rig: Rig, messages: list[_sysex.Message]) -> RigDetail:
    strings = _sysex.decode_strings(messages)
    wavs = _sysex.ir_files(strings)
    return RigDetail(rig, _sysex.amp_gain(messages), _sysex_effects.effect_chain(messages),
                     wavs[0] if wavs else None, strings)


def rig_detail(rig: Rig) -> RigDetail:
    return _detail(rig, rig_messages(rig))


def try_rig_detail(rig: Rig) -> RigDetail | None:
    """`rig_detail`, or None for a payload that does not parse."""
    messages = _sysex.parse_messages(rig.blob)
    return None if messages is None else _detail(rig, messages)
