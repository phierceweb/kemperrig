"""Aggregate a Backup into a LibraryReport — the numbers behind the `summary` view."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from kemperrig.model import Backup


@dataclass(frozen=True)
class LibraryReport:
    total_rigs: int
    di_count: int
    studio_count: int
    gain_min: float | None
    gain_max: float | None
    gain_mean: float | None
    gain_bands: dict[int, int]          # floor(gain) -> count
    amp_models: list[tuple[str, int]]   # most-common first
    authors: list[tuple[str, int]]      # most-common first
    performance_count: int


def build_report(backup: Backup) -> LibraryReport:
    rigs = backup.rigs
    di = sum(1 for r in rigs if r.is_di)
    gains = [r.gain for r in rigs if r.gain is not None]
    bands: Counter[int] = Counter(int(g) for g in gains)
    models = Counter(r.amp_model for r in rigs if r.amp_model)
    authors = Counter(r.author or "(none)" for r in rigs)
    return LibraryReport(
        total_rigs=len(rigs),
        di_count=di,
        studio_count=len(rigs) - di,
        gain_min=min(gains) if gains else None,
        gain_max=max(gains) if gains else None,
        gain_mean=sum(gains) / len(gains) if gains else None,
        gain_bands=dict(sorted(bands.items())),
        amp_models=models.most_common(),
        authors=authors.most_common(),
        performance_count=len(backup.performances),
    )
