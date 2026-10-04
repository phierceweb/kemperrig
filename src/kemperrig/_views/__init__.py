"""Plain-text rendering for the CLI, one module per command group. Pure formatting — no
I/O, returns strings. Every renderer exported here is `_safe`: names and strings come from
files other people wrote, so their control characters are shown escaped, never sent to the
terminal."""

from __future__ import annotations

import functools
import re
from collections.abc import Callable

from . import _compare, _curation, _doctor, _extract, _library, _packs, _pages, _rename

# C0 except tab and newline, DEL, and C1 — the bytes that start or end an escape sequence.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def terminal_safe(text: str) -> str:
    """`text` with each control character but tab and newline shown as `\\xNN`."""
    return _CONTROL.sub(lambda m: f"\\x{ord(m[0]):02x}", text)


def _safe(render: Callable[..., str]) -> Callable[..., str]:
    @functools.wraps(render)
    def safe(*args, **kwargs) -> str:
        return terminal_safe(render(*args, **kwargs))
    safe.terminal_safe = True   # type: ignore[attr-defined]
    return safe


render_diff = _safe(_compare.render_diff)
render_history = _safe(_compare.render_history)
render_analysis = _safe(_curation.render_analysis)
render_shortlist = _safe(_curation.render_shortlist)
render_doctor = _safe(_doctor.render_doctor)
render_extract = _safe(_extract.render_extract)
render_performances = _safe(_library.render_performances)
render_presets = _safe(_library.render_presets)
render_rig = _safe(_library.render_rig)
render_rigs = _safe(_library.render_rigs)
render_summary = _safe(_library.render_summary)
render_pack = _safe(_packs.render_pack)
render_page_census = _safe(_pages.render_page_census)
render_pages = _safe(_pages.render_pages)
render_rename = _safe(_rename.render_rename)

__all__ = [
    "render_analysis", "render_diff", "render_doctor", "render_extract", "render_history",
    "render_pack", "render_page_census", "render_pages", "render_performances", "render_rename",
    "render_presets", "render_rig", "render_rigs", "render_shortlist", "render_summary",
    "terminal_safe",
]
