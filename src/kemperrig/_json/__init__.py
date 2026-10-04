"""JSON documents for the CLI's `--json` — the machine-readable twin of `_views`."""

from __future__ import annotations

import json

from ._census import CENSUS_FORMAT, census_doc, census_text
from ._compare import diff_doc, history_doc
from ._curation import analyze_doc
from ._doctor import doctor_doc
from ._extract import extract_doc
from ._library import (
    decode_doc,
    performances_doc,
    presets_doc,
    rig_doc,
    rigs_doc,
    summary_doc,
)
from ._packs import pack_doc
from ._pages import page_census_doc, pages_doc

__all__ = [
    "CENSUS_FORMAT", "analyze_doc", "census_doc", "census_text", "decode_doc", "diff_doc",
    "doctor_doc",
    "dump", "extract_doc", "history_doc", "pack_doc", "page_census_doc", "pages_doc",
    "performances_doc", "presets_doc", "rig_doc", "rigs_doc", "summary_doc",
]


def dump(doc: dict) -> None:
    """Print `doc`; a NaN or infinity raises ValueError rather than print what is not JSON."""
    print(json.dumps(doc, indent=2, allow_nan=False))
