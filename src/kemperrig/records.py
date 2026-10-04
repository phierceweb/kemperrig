"""The things a `.rmbackup` holds: rigs, performances and their slots, presets, and the
archive's own info block — plus a rig or preset pack. Plain frozen dataclasses — no I/O, no
decoding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CAB_IR_CLASS = "6"      # Preset Class 6 = Cabinet IR; class 3 = effect module

# Boost/overdrive cues seen in the Amp Comment free-text field (pedals + generic drive words).
# The short ones sit inside ordinary words ("good", "strat"), so they match only as words.
_BOOST_TEXT = ("808", "tube screamer", "screamer", "klon", "centaur", "maxon", "keeley",
               "overdrive", "boost", "blues driver", "direwolf", "flux drive", "green scream",
               "ts9", "sd-1", "sd1", "timmy")
_BOOST_WORDS = ("od", "rat")
_BOOST = re.compile("|".join([*map(re.escape, _BOOST_TEXT),
                              *(rf"\b{w}\b" for w in _BOOST_WORDS)]))
# A negation covers the cues after it, up to the end of its clause; an un-negated cue wins.
_CLAUSE = re.compile(r"[,;.:()\n]|\bbut\b")
_NEGATION = re.compile(r"\b(?:no|not|non|without|w/o)\b|\b(?:un|non)(?=boost)")


def library_path(folder: str | None, name: str) -> str:
    """`folder/name`, or the bare name where there are no folders (a snapshot, a pack)."""
    return f"{folder}/{name}" if folder else name


@dataclass(frozen=True)
class Info:
    version: str | None
    user: str | None


@dataclass(frozen=True)
class Rig:
    name: str
    folder: str
    filename: str | None = None
    author: str | None = None
    date: str | None = None
    comment: str | None = None
    gain: float | None = None
    amp_model: str | None = None
    cabinet_name: str | None = None
    mic_type: str | None = None
    mic_position: str | None = None
    speaker_manufacturer: str | None = None
    speaker_model: str | None = None
    profile_type: str | None = None      # raw and uninterpreted
    profile_revision: str | None = None
    cabinet_type: str | None = None      # raw and uninterpreted — not a DI flag
    cabinet_configuration: str | None = None
    amp_name: str | None = None          # descriptive amp name as the profiler stores it
    amp_comment: str | None = None       # drive/boost + tube notes, e.g. "Maxon 808", "Unboosted"
    amp_channel: str | None = None       # "Clean" / "Lead" / "Crunch" / "Red (Modern)" …
    source_amp: str | None = None        # manufacturer, e.g. "Mesa Boogie"
    amp_model_year: str | None = None
    amp_location: str | None = None
    amp_pickup: str | None = None        # "Humbucker" / "Single Coil" / "HB\\SC" …
    blob: bytes = b""  # the raw .krig payload (KThd/KTrk SysEx); decoded by _sysex

    @property
    def path(self) -> str:
        return library_path(self.folder, self.name)

    @property
    def is_di(self) -> bool:
        """A DI/direct profile carries no baked-in cab (you supply the IR / real cab)."""
        cab = (self.cabinet_name or "").strip()
        return cab in ("", "N/A", "DIRECT")

    @property
    def is_boosted(self) -> bool | None:
        """Whether a boost/overdrive sits in front, read from the Amp Comment text. True/False when
        the text is conclusive, None when it carries no drive info (e.g. only tube specs)."""
        c = (self.amp_comment or "").lower()
        if not c or c in ("n/a", "none", "direct"):
            return None
        negated = False
        for clause in _CLAUSE.split(c):
            neg = _NEGATION.search(clause)
            cut = neg.start() if neg else len(clause)
            if _BOOST.search(clause[:cut]):
                return True
            negated = negated or bool(_BOOST.search(clause, cut))
        return False if negated else None


@dataclass(frozen=True)
class Slot:
    index: int
    name: str | None
    enable: str | None
    rig_name: str | None
    amp_name: str | None
    cab_name: str | None


@dataclass(frozen=True)
class Performance:
    name: str
    filename: str | None
    tempo: str | None
    slots: list[Slot] = field(default_factory=list)
    blob: bytes = b""  # the raw .kperformance payload (header + 5 slot tracks)


@dataclass(frozen=True)
class Preset:
    name: str
    folder: str
    filename: str | None = None
    preset_class: str | None = None      # "6" = Cabinet IR, "3" = effect module
    preset_category: str | None = None
    preset_type: str | None = None       # the effect name for class-3 presets, e.g. "Green Scream"
    blob: bytes = b""

    @property
    def path(self) -> str:
        return library_path(self.folder, self.name)

    @property
    def is_cab_ir(self) -> bool:
        return self.preset_class == _CAB_IR_CLASS


@dataclass(frozen=True)
class Pack:
    """A Rig Manager rig or preset pack: who made it, and the rigs or presets it carries."""
    name: str
    author: str | None                   # the vendor
    copyright: str | None
    released: str | None                 # `releasedate` as stored, e.g. "20200102030405"
    content: str                         # "rigs" or "presets"
    rigs: list[Rig] = field(default_factory=list)
    presets: list[Preset] = field(default_factory=list)
