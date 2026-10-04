"""Documents for `pages`, one rig or the whole library."""

from __future__ import annotations

from kemperrig import _sysex_effects
from kemperrig.model import Rig
from kemperrig.services.pages import PageCensus


def _page(page: int) -> dict:
    return {"page": page, "page_hex": f"0x{page:02x}", "label": _sysex_effects.page_label(page)}

def pages_doc(rig: Rig, blocks: dict[tuple[int, int], list[int]],
              other: list[tuple[bytes, int]]) -> dict:
    return {"rig": rig.name, "folder": rig.folder,
            "blocks": [{**_page(page), "start": start, "count": len(values), "values": values}
                       for (page, start), values in blocks.items()],
            "other": [{"header": head.hex(" "), "bytes": length} for head, length in other]}

def page_census_doc(c: PageCensus) -> dict:
    return {"rigs": c.rigs,
            "pages": [{**_page(p.page), "rigs": p.rigs, "starts": p.starts,
                       "param_counts": p.param_counts} for p in c.pages],
            "other": [{"header": o.header.hex(" "), "rigs": o.rigs, "bytes": o.lengths}
                      for o in c.other],
            "unparsed": c.unparsed}
