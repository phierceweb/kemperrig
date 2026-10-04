"""Comparing libraries: ``diff`` for two, ``history`` across dated snapshots."""

from __future__ import annotations

import os
import sys

from .. import _json, _views
from ..model import Backup, snapshot_dir
from ..services.diff import diff_performances, diff_presets, diff_rigs
from ..services.history import ORDERS, history


def cmd_diff(args) -> int:
    """Exit 1 when the two backups differ, so it can gate a script."""
    if not (args.before.strip() and args.after.strip()):
        print("kemperrig: a backup path is blank", file=sys.stderr)
        return 2
    before, after = Backup.open(args.before), Backup.open(args.after)
    rigs = diff_rigs(before, after)
    perfs = diff_performances(before, after)
    presets = diff_presets(before, after)
    if args.json:
        _json.dump(_json.diff_doc(rigs, perfs, presets))
    else:
        print(_views.render_diff(rigs, perfs, presets))
    return 0 if (rigs.empty and perfs.empty and presets.empty) else 1


def register_diff(sub) -> None:
    df = sub.add_parser("diff", help="what changed between two backups")
    df.add_argument("before")
    df.add_argument("after")
    df.add_argument("--json", action="store_true", help="machine-readable output")
    df.set_defaults(func=cmd_diff)


def cmd_history(args) -> int:
    """Exit 0 whenever it runs: a changed library is the expected answer, and unreadable files
    are reported on stderr. A source that cannot be listed raises, so exits 1."""
    sources = args.sources or [str(snapshot_dir(args.backup))]
    found = history(sources, order=args.order, rig=args.rig)
    for path, reason in found.skipped:
        print(_views.terminal_safe(f"kemperrig: skipped {os.path.basename(path)}: {reason}"),
              file=sys.stderr)
    if args.json:
        _json.dump(_json.history_doc(found))
    else:
        print(_views.render_history(found))
    return 0


def _library_when_bare(args) -> None:
    """No SOURCE: main() resolves KEMPERRIG_LIBRARY into `backup`, whose Backups/ is used."""
    if not args.sources:
        args.backup = None


def register_history(sub) -> None:
    hs = sub.add_parser(
        "history", help="how a library changed across dated snapshots and backups",
        description="Count what changed from each snapshot or backup to the previous one "
                    "from the same device. With no SOURCE, reads the Backups/ folder of "
                    "the live directory KEMPERRIG_LIBRARY names.")
    hs.add_argument("sources", nargs="*", metavar="SOURCE",
                    help="snapshot (*R2.db) or .rmbackup files, or folders of them")
    hs.add_argument("--rig", metavar="NAME", default=None,
                    help="follow one rig: every file holding it and each version of its "
                         "payload")
    hs.add_argument("--order", choices=ORDERS, default="name",
                    help="name (default): by file name, which keeps each device's snapshots "
                         "together in time order; mtime: by modification time")
    hs.add_argument("--json", action="store_true", help="machine-readable output")
    hs.set_defaults(func=cmd_history, prepare=_library_when_bare)
