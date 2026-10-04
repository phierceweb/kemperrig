"""Curation commands: ``analyze`` and ``shortlist``."""

from __future__ import annotations

from pf_core.utils.env import resolve_str

from .. import _json, _views
from ..model import Backup
from ..services.analyze import analysis
from ..services.shortlist import load_criteria, shortlist
from ._library import add_source, finite_float


def cmd_analyze(args) -> int:
    """With --strict, exit 1 when there is something to act on, so it can gate a script."""
    rack = resolve_str(args.rack_folder, "KEMPERRIG_RACK_FOLDER", default=None)
    found = analysis(Backup.open(args.backup), rack_folder=rack)
    if args.json:
        _json.dump(_json.analyze_doc(found))
    else:
        print(_views.render_analysis(found))
    return 1 if args.strict and found.actionable else 0


def cmd_shortlist(args) -> int:
    backup = Backup.open(args.backup)
    crit = load_criteria(args.criteria)
    gain_min = args.gain_min if args.gain_min is not None else crit.get("gain_min", 5.0)
    picked = shortlist(backup.rigs, crit["amp_patterns"], gain_min=gain_min,
                       di_only=not args.include_studio)
    if args.json:
        _json.dump(_json.rigs_doc(picked))
    else:
        print(_views.render_shortlist(picked, label=crit.get("label", "shortlist"),
                                      context=crit.get("context")))
    return 0


def register_analyze(sub) -> None:
    an = sub.add_parser("analyze", help="orphans, gain coverage, duplicates, effect and cab-IR use")
    add_source(an)
    an.add_argument("--json", action="store_true", help="machine-readable output")
    an.add_argument("--strict", action="store_true",
                    help="exit 1 on orphans, duplicates, a bad gain ladder or a payload "
                         "that does not parse")
    an.add_argument("--rack-folder", dest="rack_folder", default=None,
                    help="your library folder for rigs pulled off the Profiler; exempt it "
                         "from the orphan sweep (or set KEMPERRIG_RACK_FOLDER)")
    an.set_defaults(func=cmd_analyze)


def register_shortlist(sub) -> None:
    sl = sub.add_parser("shortlist", help="shortlist rigs matching a criteria file")
    add_source(sl)
    sl.add_argument("--gain-min", dest="gain_min", type=finite_float, default=None)
    sl.add_argument("--criteria", default=None,
                    help="criteria JSON (or set KEMPERRIG_CRITERIA); "
                         "start from config/example-shortlist.json")
    sl.add_argument("--include-studio", dest="include_studio", action="store_true",
                    help="also consider studio (cab-baked) profiles, not just DI")
    sl.add_argument("--json", action="store_true", help="machine-readable output")
    sl.set_defaults(func=cmd_shortlist)
