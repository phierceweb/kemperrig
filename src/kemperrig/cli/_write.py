"""The writing commands, ``rename`` and ``extract``; their guards live in the services."""

from __future__ import annotations

import sys

from .. import _json, _views
from ..model import Backup
from ..services import edit, extract
from ..services.select import select_rigs
from ._library import add_filter_args, add_source, filter_kwargs


def cmd_rename(args) -> int:
    why = edit.refusal(args.out, source=args.backup, force=args.force, old_name=args.old,
                       new_name=args.new)
    if why:
        print(f"kemperrig: {_views.terminal_safe(why)}", file=sys.stderr)
        return 2
    r = edit.rename_rig(args.backup, args.out, args.old, args.new, force=args.force)
    print(_views.render_rename(r, old=args.old, new=args.new, out=args.out))
    return 0


def register_rename(sub) -> None:
    rn = sub.add_parser(
        "rename", help="rename a rig → write a NEW .rmbackup (source untouched)",
        description="Write a new .rmbackup with one rig renamed — its row, its payload and every "
                    "performance slot that loads it — and every other entry copied as it was. "
                    "The source is never touched. An archive rename writes is not confirmed "
                    "to restore into Rig Manager yet: keep the original.")
    add_source(rn, help="the .rmbackup to rename a rig in (default: KEMPERRIG_LIBRARY)")
    rn.add_argument("old", help="current rig name")
    rn.add_argument("new", help="new rig name")
    rn.add_argument("-o", "--out", required=True, help="output .rmbackup (must differ from source)")
    rn.add_argument("--force", action="store_true", help="overwrite an existing output file")
    rn.set_defaults(func=cmd_rename)


def _selection_error(args) -> str | None:
    chosen = any(v is not None and not (isinstance(v, str) and not v.strip())
                 for v in filter_kwargs(args).values())
    if args.all and chosen:
        return "--all takes no selection flags — use one or the other"
    if not args.all and not chosen:
        return ("choose the rigs to extract: --name, a rigs filter (--amp, --folder, …), "
                "or --all for every rig")
    return None


def cmd_extract(args) -> int:
    """A refused destination or selection exits 2, like a refused rename: nothing was
    attempted."""
    why = _selection_error(args)
    if why is None:
        picked = select_rigs(Backup.open(args.backup).rigs, **filter_kwargs(args))
        planned = extract.plan(picked.rigs)
        why = extract.refusal(args.out, source=args.backup, planned=planned, force=args.force)
    if why:
        print(f"kemperrig: {_views.terminal_safe(why)}", file=sys.stderr)
        return 2
    extract.write(planned, args.out, source=args.backup, force=args.force)
    if args.json:
        _json.dump(_json.extract_doc(planned, out=args.out, selection=picked))
    else:
        print(_views.render_extract(planned, out=args.out, selection=picked))
    return 0


def register_extract(sub) -> None:
    ex = sub.add_parser(
        "extract", help="write rigs out as standalone .krig files (source untouched)",
        description="Write each selected rig's payload, byte for byte, as a .krig file in "
                    "DIR. Selects with the same flags as `rigs`, or --all. Never writes inside "
                    "the source or any Rig Manager library, and replaces an existing file only "
                    "with --force.")
    add_source(ex)
    ex.add_argument("-o", "--out", required=True, metavar="DIR",
                    help="folder to write into; created if missing")
    ex.add_argument("--all", action="store_true", help="every rig in the source")
    add_filter_args(ex)
    ex.add_argument("--force", action="store_true", help="replace files already in DIR")
    ex.add_argument("--json", action="store_true", help="machine-readable output")
    ex.set_defaults(func=cmd_extract)
