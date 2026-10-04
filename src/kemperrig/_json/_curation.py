"""The `analyze` document."""

from __future__ import annotations

from dataclasses import asdict

from kemperrig.services.analyze import Analysis


def analyze_doc(a: Analysis) -> dict:
    return {
        "orphaned_rigs": [r.path for r in a.orphans],
        "amp_coverage": [{"amp": amp, **asdict(cov)} for amp, cov in sorted(a.coverage.items())],
        "similar_groups": [[r.path for r in g] for g in a.similar],
        "identical_amp_groups": [[r.path for r in g] for g in a.identical_amps],
        "identical_profiles": [[r.path for r in g] for g in a.identical_profiles],
        "drive": a.drive,
        "effect_categories": [{"category": c, "slots": n} for c, n in a.effect_categories],
        "ir_inventory": [{"name": n, "count": c} for n, c in a.ir_inventory],
        "non_monotonic_performances": [{"name": p.name, "gain_ladder": ladder}
                                       for p, ladder in a.misordered],
        "unparsed": {"rigs": [r.path for r in a.unparsed.rigs],
                     "performances": [p.name for p in a.unparsed.performances]},
    }
