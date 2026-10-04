"""``pack`` — a rig or preset pack's contents, placed against a library on request."""

from __future__ import annotations

import sys

from .. import _json, _views
from ..model import Backup, read_pack
from ..services.pack import placements


def cmd_pack(args) -> int:
    if not args.pack.strip():
        print("kemperrig: PACKFILE is blank", file=sys.stderr)
        return 2
    pack = read_pack(args.pack)
    against = getattr(args, "backup", None)
    placed = placements(pack, Backup.open(against)) if against else None
    if args.json:
        _json.dump(_json.pack_doc(pack, placed, against=against))
    else:
        print(_views.render_pack(pack, placed, against=against))
    return 0


def _library_when_against(args, pk) -> None:
    """`--against` alone: main() resolves KEMPERRIG_LIBRARY into `backup`. Without the flag
    no library is read at all."""
    if args.against is not None:
        if args.against and not args.against.strip():
            pk.error("--against LIBRARY is blank")
        args.backup = args.against or None


def register_pack(sub) -> None:
    pk = sub.add_parser(
        "pack", help="list a rig or preset pack; --against: which items a library already has",
        description="List a Rig Manager pack (.rigpack / .presetpack). With --against, say "
                    "for each rig or preset whether the library holds the same payload, "
                    "holds a different one under its name, or neither. --against with no "
                    "LIBRARY uses KEMPERRIG_LIBRARY.")
    pk.add_argument("pack", metavar="PACKFILE", help="a .rigpack or .presetpack")
    pk.add_argument("--against", nargs="?", const="", default=None, metavar="LIBRARY",
                    help="a backup, live directory or snapshot to compare with "
                         "(default when given bare: KEMPERRIG_LIBRARY)")
    pk.add_argument("--json", action="store_true", help="machine-readable output")
    pk.set_defaults(func=cmd_pack, prepare=lambda args: _library_when_against(args, pk))
