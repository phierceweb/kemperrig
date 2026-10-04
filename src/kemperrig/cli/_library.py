"""Read commands over one library: ``summary``, ``rigs``, ``presets``, ``rig``, ``performances``."""

from __future__ import annotations

import argparse
import math
import sys

from .. import _json, _views
from ..model import Backup
from ..services import census
from ..services.decode import rig_detail
from ..services.filter import find_rig
from ..services.performance import rig_gain_index
from ..services.report import build_report
from ..services.select import select_rigs


def _write_golden(args) -> int:
    """A refused census path exits 2, like a refused extract: nothing was attempted."""
    why = census.refusal(args.write_golden, source=args.backup, force=args.force)
    if why:
        print(f"kemperrig: {_views.terminal_safe(why)}", file=sys.stderr)
        return 2
    text = _json.census_text(census.take(Backup.open(args.backup)))
    census.write(text, args.write_golden, source=args.backup, force=args.force)
    print(f"wrote census to {args.write_golden}")
    return 0


def cmd_summary(args) -> int:
    if args.write_golden is not None:
        return _write_golden(args)
    if args.force:
        print("kemperrig: --force only applies with --write-golden", file=sys.stderr)
        return 2
    backup = Backup.open(args.backup)
    report = build_report(backup)
    if args.json:
        _json.dump(_json.summary_doc(report, info_user=backup.info.user))
    else:
        print(_views.render_summary(report, info_user=backup.info.user))
    return 0


def filter_kwargs(args) -> dict:
    """The `select_rigs` keywords the flags `add_filter_args` defines ask for."""
    return {"names": args.name, "amp_model": args.amp, "author": args.author,
            "folder": args.folder, "source": args.source, "channel": args.channel,
            "comment": args.comment, "gain_min": args.gain_min, "gain_max": args.gain_max,
            "di": True if args.di else (False if args.studio else None),
            "boosted": True if args.boosted else (False if args.unboosted else None),
            "effect": args.effect, "ir": args.ir}


def finite_float(text: str) -> float:
    """An argparse type: a float that is neither NaN nor infinite, which would disable a
    comparison rather than make one."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"not a finite number: {text!r}")
    return value


SOURCE_HELP = ("a .rmbackup, live Rig Manager directory, dated snapshot or pack "
               "(default: KEMPERRIG_LIBRARY)")


def add_source(p, *, help: str = SOURCE_HELP) -> None:
    """The optional library positional every read command takes."""
    p.add_argument("backup", nargs="?", default=None, metavar="SOURCE", help=help)


def add_filter_args(r) -> None:
    """The rig-selection flags `rigs` and `extract` share."""
    r.add_argument("--name", action="append", metavar="NAME",
                   help="exact rig name; repeat for more than one")
    r.add_argument("--amp", dest="amp", help="amp-model substring")
    r.add_argument("--author", help="author substring")
    r.add_argument("--folder", help="library-folder substring")
    r.add_argument("--source", metavar="MAKER", help="manufacturer substring (e.g. 'mesa')")
    r.add_argument("--channel", help="amp-channel substring (e.g. 'lead')")
    r.add_argument("--comment", help="amp-comment substring (e.g. '808')")
    r.add_argument("--gain-min", dest="gain_min", type=finite_float)
    r.add_argument("--gain-max", dest="gain_max", type=finite_float)
    g = r.add_mutually_exclusive_group()
    g.add_argument("--di", action="store_true", help="DI/direct profiles only")
    g.add_argument("--studio", action="store_true", help="studio (cab-baked) profiles only")
    bg = r.add_mutually_exclusive_group()
    bg.add_argument("--boosted", action="store_true", help="boosted/overdriven rigs only")
    bg.add_argument("--unboosted", action="store_true", help="unboosted rigs only")
    r.add_argument("--effect", metavar="TEXT",
                   help="a decoded effect's type-name or category substring (e.g. 'delay')")
    r.add_argument("--ir", metavar="TEXT", help="cab-IR file-name substring")


def cmd_rigs(args) -> int:
    picked = select_rigs(Backup.open(args.backup).rigs, decode=args.decode,
                         **filter_kwargs(args))
    if args.json:
        _json.dump(_json.rigs_doc(picked.rigs, selection=picked))
    else:
        print(_views.render_rigs(picked.rigs, selection=picked))
    return 0


def cmd_presets(args) -> int:
    presets = Backup.open(args.backup).presets
    if args.json:
        _json.dump(_json.presets_doc(presets))
    else:
        print(_views.render_presets(presets))
    return 0


def cmd_rig(args) -> int:
    rig = find_rig(Backup.open(args.backup).rigs, args.name, folder=args.folder,
                   payload=args.payload)
    detail = rig_detail(rig)
    if args.json:
        _json.dump(_json.rig_doc(detail))
    else:
        print(_views.render_rig(detail))
    return 0


def cmd_performances(args) -> int:
    backup = Backup.open(args.backup)
    index = rig_gain_index(backup.rigs)
    if args.json:
        _json.dump(_json.performances_doc(backup.performances, index))
    else:
        print(_views.render_performances(backup.performances, index))
    return 0


def register_summary(sub) -> None:
    s = sub.add_parser("summary", help="library overview (counts, gain, amps, authors)")
    add_source(s)
    out = s.add_mutually_exclusive_group()
    out.add_argument("--json", action="store_true", help="machine-readable output")
    out.add_argument("--write-golden", dest="write_golden", metavar="PATH",
                     help="write the library census to PATH instead (see docs/census.md)")
    s.add_argument("--force", action="store_true",
                   help="with --write-golden: replace an existing file")
    s.set_defaults(func=cmd_summary)


def register_rigs(sub) -> None:
    r = sub.add_parser("rigs", help="list/filter rigs")
    add_source(r)
    add_filter_args(r)
    r.add_argument("--decode", action="store_true",
                   help="add each rig's decoded amp gain, effects, cab IR and strings")
    r.add_argument("--json", action="store_true", help="machine-readable output")
    r.set_defaults(func=cmd_rigs)


def register_presets(sub) -> None:
    pr = sub.add_parser("presets", help="inventory effect + cab-IR presets")
    add_source(pr)
    pr.add_argument("--json", action="store_true", help="machine-readable output")
    pr.set_defaults(func=cmd_presets)


def register_rig(sub) -> None:
    rg = sub.add_parser("rig", help="one rig's metadata and decoded payload")
    add_source(rg)
    rg.add_argument("name")
    rg.add_argument("--folder", default=None,
                    help="library-folder substring, when one name is used more than once")
    rg.add_argument("--payload", default=None, metavar="DIGEST",
                    help="payload-digest prefix, when one name is used more than once in "
                         "one folder or in a source without folders")
    rg.add_argument("--json", action="store_true", help="machine-readable output")
    rg.set_defaults(func=cmd_rig)


def register_performances(sub) -> None:
    p = sub.add_parser("performances", help="list performances and their slot ladders")
    add_source(p)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_performances)
