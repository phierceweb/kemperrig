"""The ``kemperrig`` command line: the parser, ``KEMPERRIG_*`` settings and the exception
boundary. This package is the only place that reads the environment, prints, or catches
exceptions; each ``_<group>`` module registers its commands."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET
import zipfile

from pf_core.utils.env import resolve_str

from .. import __version__, _enums, _views
from . import _compare, _curation, _doctor, _library, _packs, _pages, _write

# Registration order is the order `--help` lists the commands in.
_COMMANDS = (
    _library.register_summary,
    _library.register_rigs,
    _curation.register_analyze,
    _doctor.register_doctor,
    _library.register_presets,
    _library.register_rig,
    _pages.register_pages,
    _curation.register_shortlist,
    _library.register_performances,
    _packs.register_pack,
    _compare.register_diff,
    _compare.register_history,
    _write.register_rename,
    _write.register_extract,
)


_EPILOG = """environment:
  KEMPERRIG_LIBRARY     the SOURCE when a command is given none
  KEMPERRIG_CRITERIA    the criteria file shortlist uses without --criteria
  KEMPERRIG_RACK_FOLDER the library folder analyze exempts from the orphan sweep
  KEMPERRIG_STOMPS_XML  Rig Manager's Stomps.xml, when not in the standard place
  KEMPERRIG_GOLDEN      a census for the opt-in golden test (see docs/census.md)
"""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="kemperrig",   # argv[0] is the module path under `python -m kemperrig.cli`
        description="Read a Kemper Rig Manager library — a .rmbackup, the live directory, a "
                    "dated snapshot or a pack. The writers never touch their source.",
        epilog=_EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"kemperrig {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for register in _COMMANDS:
        register(sub)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not hasattr(args, "json"):
        args.json = False
    if hasattr(args, "prepare"):   # a command whose positionals argparse cannot split alone
        args.prepare(args)

    # Effect names are Kemper's, so they are read from the user's own Rig Manager rather
    # than vendored. Absent, decoding falls back to the verified subset.
    _enums.install(resolve_str(None, "KEMPERRIG_STOMPS_XML", default=_enums.DEFAULT_PATH))

    if hasattr(args, "backup"):
        if args.backup is not None and not args.backup.strip():
            ap.error("SOURCE is blank")
        args.backup = resolve_str(args.backup, "KEMPERRIG_LIBRARY", default=None)
        if args.backup is None or not args.backup.strip():
            ap.error("no backup given and KEMPERRIG_LIBRARY is not set")
    if getattr(args, "criteria", None) is None and args.cmd == "shortlist":
        args.criteria = resolve_str(None, "KEMPERRIG_CRITERIA", default=None)
        if args.criteria is None:
            ap.error("shortlist needs --criteria or KEMPERRIG_CRITERIA")

    try:
        return args.func(args)
    except BrokenPipeError:  # piped into head/less — not an error
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except (OSError, ValueError, KeyError, IndexError,
            zipfile.BadZipFile, sqlite3.DatabaseError, ET.ParseError) as e:
        print(f"kemperrig: {_views.terminal_safe(str(e))}", file=sys.stderr)
        return 1
