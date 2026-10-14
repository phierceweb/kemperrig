"""The things a `.rmbackup` holds: rigs, performances and their slots, presets, and the
archive's own info block — plus a rig or preset pack. Plain frozen dataclasses — no I/O, no
decoding."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field

_CAB_IR_CLASS = "6"
_EFFECT_CLASS = "3"

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
# Cues named together form one run, decided by what follows its last cue: one pedal in two
# words ("Maxon 808", "Klon-style boost"), or pedals joined by and, &, + or /.
_RUN = re.compile(r"[\w-]*+[^\S\n]*+(?:(?:and|&|\+|/)[^\S\n]*+)?[\w-]*+")   # possessive: stays linear
_LABEL = re.compile(r"\w*[^\S\n]*[:=]")
# Between a run and what decides it: the rest of its word, punctuation ("Boost: off", "TS9
# (off)") and up to three linking words ("TS9 is set to off") — never a knob ("OD attack off").
_LINK = (r"\w*[^\S\n]*(?:[-:=()\[\]][^\S\n]*)*(?:(?:is|are|was|were|has|have|been|both"
         r"|turned|switched|switch|kept|left|set|to)[^\S\n]+){0,3}")
_LINKED = re.compile(_LINK)
_END = r"[^\S\n]*(?=[,;.:()\[\]!?\n]|$)"
# A toggle ("on/off") leaves the state open; "off axis" is a mic position, not a switch; "no"
# and "not on" decide only as the whole value ("Boost: no", never "TS9 no mods").
_DECIDES = re.compile(_LINK + r"""(?:
      (?P<toggle>(?:on|off)[^\S\n]*(?:/|or\b)[^\S\n]*(?:on|off)\b)
    | (?:off|bypassed|disengaged|disabled)\b(?![\s-]*axis)
    | (?:not|(?:is|are|was|were)n['’]t)[^\S\n]+
      (?:(?:engaged|used|active|needed)\b|on""" + _END + r""")
    | none\b | (?:no|n/a)""" + _END + ")", re.VERBOSE)
_CLOSES = re.compile(r"\w*[^\S\n]*[)\]]")


def _negated(c: str, cues: list[re.Match[str]]) -> list[bool]:
    """Per cue, whether a negation earlier in its clause covers it."""
    seps = list(_CLAUSE.finditer(c))
    starts = [0, *(m.end() for m in seps)]
    ends = [*(m.start() for m in seps), len(c)]
    first = [neg.start() if (neg := _NEGATION.search(c, s, e)) else e
             for s, e in zip(starts, ends, strict=True)]
    return [first[bisect_right(starts, cue.start()) - 1] < cue.start() for cue in cues]


def _starts_field(c: str, cue: re.Match[str], first: re.Match[str]) -> bool:
    """`cue` labels a new field, and the run from `first` it would join is the value of the
    field before: a value ends where the next label begins ("Drive: TS9 / Boost: none")."""
    if not _LABEL.match(c, cue.end()):
        return False
    pos = first.start()
    while pos and c[pos - 1] != "\n" and c[pos - 1].isspace():
        pos -= 1
    return pos > 0 and c[pos - 1] in ":="


def _decided_by_next(c: str, end: int, first: re.Match[str], last: re.Match[str]) -> bool:
    """The run `first`..`last` decides the run ending at `end`: after `:` or `=` ("Boost: TS9
    off") or alone in brackets ("Boost (TS9) off"), never as an aside or the next list item."""
    link = _LINKED.match(c, end)
    if link.end() != first.start():
        return False
    text = link.group()
    gloss = ("(" in text or "[" in text) and _CLOSES.match(c, last.end()) is not None
    return ":" in text or "=" in text or gloss


def _cue_states(c: str) -> list[bool | None]:
    """Each boost cue in `c`: True when on, False when negated or switched off, None when only
    toggled."""
    cues = list(_BOOST.finditer(c))
    runs: list[list[int]] = []
    for i, cue in enumerate(cues):
        if (runs and _RUN.fullmatch(c, cues[i - 1].end(), cue.start())
                and not _starts_field(c, cue, cues[runs[-1][0]])):
            runs[-1].append(i)
        else:
            runs.append([i])
    states: list[bool | None] = [True] * len(cues)
    for k in reversed(range(len(runs))):
        end = cues[runs[k][-1]].end()
        if m := _DECIDES.match(c, end):
            state = None if m["toggle"] else False
        elif k + 1 < len(runs) and _decided_by_next(c, end, cues[runs[k + 1][0]],
                                                    cues[runs[k + 1][-1]]):
            state = states[runs[k + 1][0]]
        else:
            state = True
        for i in runs[k]:
            states[i] = state
    return [False if neg else s for neg, s in zip(_negated(c, cues), states, strict=True)]


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
    instrument: str | None = None        # a rig pack's rigs.comment: Guitar, Bass, Acoustic
    kpaid: str | None = None             # a snapshot's KPAID, raw; unique in its snapshot
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
        the text is conclusive; None when it is not — no drive cue (e.g. only tube specs), or a
        pedal only toggled ("TS9 on/off") and none switched on."""
        c = (self.amp_comment or "").lower()
        if not c or c in ("n/a", "none", "direct"):
            return None
        states = _cue_states(c)
        if True in states:
            return True
        return False if states and None not in states else None


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
    prog_nr: str | None = None           # a snapshot's ProgNr, raw; 1–125, unique in its snapshot
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

    @property
    def is_effect(self) -> bool:
        return self.preset_class == _EFFECT_CLASS or bool(self.preset_type)


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
