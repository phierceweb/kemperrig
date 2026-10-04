"""Filter rigs by metadata predicates. All string matches are case-insensitive substrings."""

from __future__ import annotations

from kemperrig.model import Rig
from kemperrig.services.diff import digest


def contains(haystack: str | None, needle: str) -> bool:
    return needle.lower() in (haystack or "").lower()


def filter_rigs(
    rigs: list[Rig],
    *,
    names: list[str] | None = None,
    amp_model: str | None = None,
    author: str | None = None,
    folder: str | None = None,
    source: str | None = None,
    channel: str | None = None,
    comment: str | None = None,
    gain_min: float | None = None,
    gain_max: float | None = None,
    di: bool | None = None,
    boosted: bool | None = None,
) -> list[Rig]:
    """Return rigs matching every supplied predicate (AND). `names` matches whole names exactly,
    any of them. `di`/`boosted`: True keeps only that state, False keeps the opposite, None
    keeps all (boosted ignores rigs of unknown drive state)."""
    out = []
    for r in rigs:
        if names is not None and r.name not in names:
            continue
        if amp_model is not None and not contains(r.amp_model, amp_model):
            continue
        if author is not None and not contains(r.author, author):
            continue
        if folder is not None and not contains(r.folder, folder):
            continue
        if source is not None and not contains(r.source_amp, source):
            continue
        if channel is not None and not contains(r.amp_channel, channel):
            continue
        if comment is not None and not contains(r.amp_comment, comment):
            continue
        if gain_min is not None and (r.gain is None or r.gain < gain_min):
            continue
        if gain_max is not None and (r.gain is None or r.gain > gain_max):
            continue
        if di is not None and r.is_di != di:
            continue
        if boosted is not None and r.is_boosted != boosted:
            continue
        out.append(r)
    return out


def find_rig(rigs: list[Rig], name: str, *, folder: str | None = None,
             payload: str | None = None) -> Rig:
    """The one rig called `name`, narrowed by a folder substring or a payload-digest prefix.
    Rigs sharing one non-empty payload are one answer. A missing or ambiguous name is a
    ValueError saying how to choose."""
    matches = [r for r in rigs if r.name == name
               and (folder is None or contains(r.folder, folder))
               and (payload is None or (digest(r.blob) or "").startswith(payload.lower()))]
    if not matches:
        raise ValueError(f"no rig named {name!r}")
    digests = {digest(r.blob) for r in matches}
    if len(matches) == 1 or (len(digests) == 1 and None not in digests):
        return matches[0]
    folders = sorted({r.folder for r in matches})
    if len(folders) == len(matches) and all(folders):
        raise ValueError(f"{len(matches)} rigs named {name!r} — narrow it with "
                         f"--folder ({', '.join(folders)})")
    choices = ", ".join(sorted(d or "no payload" for d in digests))
    raise ValueError(f"{len(matches)} rigs named {name!r} — pick one with --payload ({choices})")
