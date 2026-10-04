"""``doctor`` — referential integrity of a library."""

from __future__ import annotations

from .. import _json, _views
from ..model import Backup
from ..services.doctor import checkup
from ._library import add_source


def cmd_doctor(args) -> int:
    """With --strict, exit 1 on a definite finding only, so it can gate a script."""
    backup = Backup.open(args.backup)
    device = Backup.open(args.device_backup) if args.device_backup else None
    found = checkup(backup, device=device)
    if args.json:
        _json.dump(_json.doctor_doc(found))
    else:
        print(_views.render_doctor(found))
    return 1 if args.strict and found.defective else 0


def register_doctor(sub) -> None:
    dr = sub.add_parser(
        "doctor", help="referential integrity: dangling slots, broken payloads, unused IRs",
        description="Check what a library's records point at. Definite findings — dangling "
                    "or ambiguous slots, broken payloads — fail --strict; the rest are "
                    "informational.")
    add_source(dr)
    dr.add_argument("--json", action="store_true", help="machine-readable output")
    dr.add_argument("--strict", action="store_true",
                    help="exit 1 when there is a definite finding")
    dr.add_argument("--device-backup", dest="device_backup", metavar="SOURCE", default=None,
                    help="a backup or snapshot of the device; a dangling slot whose rig it "
                         "holds is reported as on the device only")
    dr.set_defaults(func=cmd_doctor)
