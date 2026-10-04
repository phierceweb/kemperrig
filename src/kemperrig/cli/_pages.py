"""``pages`` — the raw parameter-block dump, for one rig or as a library census."""

from __future__ import annotations

from .. import _json, _views
from ..model import Backup
from ..services.filter import find_rig
from ..services.pages import census, rig_pages


def cmd_pages(args) -> int:
    backup = Backup.open(args.backup)
    if args.all:
        doc = census(backup.rigs)
        if args.json:
            _json.dump(_json.page_census_doc(doc))
        else:
            print(_views.render_page_census(doc))
        return 0
    rig = find_rig(backup.rigs, args.name, folder=args.folder, payload=args.payload)
    found, other = rig_pages(rig)
    if args.json:
        _json.dump(_json.pages_doc(rig, found, other))
    else:
        print(_views.render_pages(rig, found, other))
    return 0


def _split_operands(args, pg) -> None:
    """`[backup] RIG` or `[backup] --all`: one operand is the rig, unless --all takes it."""
    ops = args.operands
    if args.all:
        if len(ops) > 1:
            pg.error("--all takes no rig name")
        if args.folder is not None or args.payload is not None:
            pg.error("--all takes no --folder or --payload")
        args.backup, args.name = (ops[0] if ops else None), None
        return
    if not ops or len(ops) > 2:
        pg.error("a rig name or --all is required")
    args.backup, args.name = (None, ops[0]) if len(ops) == 1 else (ops[0], ops[1])


def register_pages(sub) -> None:
    pg = sub.add_parser(
        "pages", help="dump a rig's raw parameter blocks, or census them (--all)",
        usage="%(prog)s [SOURCE] (RIG [--folder F] [--payload DIGEST] | --all) [--json]")
    pg.add_argument("operands", nargs="*", metavar="[SOURCE] RIG",
                    help="the library (default: KEMPERRIG_LIBRARY) and a rig name")
    pg.add_argument("--all", action="store_true",
                    help="census every rig: which pages occur, in how many rigs")
    pg.add_argument("--folder", default=None,
                    help="library-folder substring, when one name is used more than once")
    pg.add_argument("--payload", default=None, metavar="DIGEST",
                    help="payload-digest prefix, when one name is used more than once in "
                         "one folder or in a source without folders")
    pg.add_argument("--json", action="store_true", help="machine-readable output")
    pg.set_defaults(func=cmd_pages, prepare=lambda args: _split_operands(args, pg))
