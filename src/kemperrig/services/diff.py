"""What changed between two backups, compared as a `Fingerprint` per record (field values
plus payload digest) so a caller can keep those without the blobs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from operator import attrgetter

from kemperrig._tables import _PERF_SLOTS
from kemperrig.model import Backup, Performance

KINDS = ("rigs", "performances", "presets")


def _slot(n: int) -> Callable[[Performance], str | None]:
    return lambda p: next((s.rig_name for s in p.slots if s.index == n), None)


def _attrs(*names: str) -> tuple[tuple[str, Callable], ...]:
    return tuple((n, attrgetter(n)) for n in names)


# Fields reported per kind, as (name, getter); the blob is compared separately, as a digest.
_FIELDS: dict[str, tuple[tuple[str, Callable], ...]] = {
    "rigs": _attrs("gain", "amp_model", "cabinet_name", "author", "comment", "profile_type",
                   "mic_type", "mic_position", "speaker_manufacturer", "speaker_model"),
    "performances": (*_attrs("tempo"),
                     *((f"slot {n}", _slot(n)) for n in range(1, _PERF_SLOTS + 1))),
    "presets": _attrs("preset_class", "preset_type", "preset_category"),
}


@dataclass(frozen=True)
class FieldChange:
    field: str
    before: object
    after: object


@dataclass(frozen=True)
class Changed:
    key: str
    changes: list[FieldChange]


@dataclass(frozen=True)
class Diff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[Changed] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


@dataclass(frozen=True, slots=True)
class Fingerprint:
    """All a diff compares of one record: its reported field values and its payload digest."""
    values: tuple
    payload: str | None


def digest(blob: bytes) -> str | None:
    return hashlib.sha256(blob).hexdigest()[:12] if blob else None


def _key(kind: str, record) -> str:
    return record.name if kind == "performances" else record.path


def fingerprints(backup: Backup, kind: str) -> dict[str, list[Fingerprint]]:
    """Key → the fingerprints of the records under it, in the order the backup holds them."""
    fields = _FIELDS[kind]
    out: dict[str, list[Fingerprint]] = {}
    for r in getattr(backup, kind):
        fp = Fingerprint(tuple(get(r) for _, get in fields), digest(r.blob))
        out.setdefault(_key(kind, r), []).append(fp)
    return out


def _align(before: list[Fingerprint], after: list[Fingerprint]
           ) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Pair records that share a key, by position in each list. Same payload means the same
    rig whatever order the databases yielded them in; the rest pair positionally, and the
    overflow is a real addition or removal rather than a field change on a survivor."""
    left, right = list(range(len(before))), list(range(len(after)))
    pairs = []
    for same in (lambda i, j: after[j] == before[i],
                 lambda i, j: after[j].payload == before[i].payload):
        for i in list(left):
            j = next((j for j in right if same(i, j)), None)
            if j is not None:
                left.remove(i)
                right.remove(j)
                pairs.append((i, j))
    while left and right:
        pairs.append((left.pop(0), right.pop(0)))
    return pairs, left, right


def _label(key: str, n: int, total: int) -> str:
    """`key`, or `key #n` when several records share it: the record's position under the key
    in the backup it is listed from — the newer one for added and changed, the older for
    removed."""
    return key if total == 1 else f"{key} #{n}"


def compare(kind: str, before: dict[str, list[Fingerprint]],
            after: dict[str, list[Fingerprint]]) -> Diff:
    fields = _FIELDS[kind]
    added, removed, changed = [], [], []
    for key in sorted(set(before) | set(after)):
        b_fps, a_fps = before.get(key, []), after.get(key, [])
        pairs, gone, new = _align(b_fps, a_fps)
        removed += [_label(key, i + 1, len(b_fps)) for i in gone]
        added += [_label(key, j + 1, len(a_fps)) for j in new]
        for i, j in sorted(pairs, key=lambda ij: ij[1]):
            x, y = b_fps[i], a_fps[j]
            rows = [FieldChange(f, u, v)
                    for (f, _), u, v in zip(fields, x.values, y.values, strict=True) if u != v]
            if x.payload != y.payload:
                rows.append(FieldChange("payload", x.payload, y.payload))
            if rows:
                changed.append(Changed(_label(key, j + 1, len(a_fps)), rows))
    return Diff(added=sorted(added), removed=sorted(removed), changed=changed)


def _diff(kind: str, before: Backup, after: Backup) -> Diff:
    return compare(kind, fingerprints(before, kind), fingerprints(after, kind))


def diff_rigs(before: Backup, after: Backup) -> Diff:
    return _diff("rigs", before, after)


def diff_performances(before: Backup, after: Backup) -> Diff:
    return _diff("performances", before, after)


def diff_presets(before: Backup, after: Backup) -> Diff:
    return _diff("presets", before, after)
