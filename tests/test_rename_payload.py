"""`rename` rewrites the name inside the rig's payload and the slots that load it."""

import io
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

from _fixture import build_rmbackup
from _payloads import amp_msg, make_blob, performance_blob, rig_track

from kemperrig import _sysex
from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services import doctor
from kemperrig.services.edit import rename_rig

NAME = b"\x00\x00\x01"


def _rig(name: str, payload_name: str | None = None) -> dict:
    return {"name": name, "folder": "Amps", "gain": "5.0",
            "blob": make_blob([rig_track(payload_name or name) + [amp_msg(5.0)]])}


def _perf(name: str, *rigs: str) -> dict:
    return {"name": name, "slots": [{"name": r, "rig_name": r} for r in rigs],
            "blob": performance_blob(*(rig_track(r) for r in rigs))}


def _payload_names(blob: bytes) -> list[str | None]:
    return [_sysex.addressed_strings(t).get(NAME) for t in _sysex.tracks(blob)]


def _blobs(path: str) -> dict[str, bytes]:
    b = Backup.open(path)
    return {**{f"rig:{r.name}": r.blob for r in b.rigs},
            **{f"perf:{p.name}": p.blob for p in b.performances}}


class RenamePayloadTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = build_rmbackup(os.path.join(self.d, "a.rmbackup"),
                                  rigs=[_rig("Old"), _rig("Other")],
                                  performances=[_perf("Set", "Old", "Other", "Old")])
        self.out = os.path.join(self.d, "b.rmbackup")

    def test_the_rig_payload_and_its_slots_carry_the_new_name(self):
        result = rename_rig(self.src, self.out, "Old", "New")
        self.assertEqual(tuple(result), (1, 2, 1, 2))
        after = Backup.open(self.out)
        rig = next(r for r in after.rigs if r.name == "New")
        self.assertEqual(_payload_names(rig.blob), ["New"])
        self.assertEqual(_payload_names(after.performances[0].blob),
                         [None, "New", "Other", "New", None, None])
        self.assertEqual(doctor.name_mismatches(after), [])

    def test_renaming_back_restores_every_payload_byte(self):
        back = os.path.join(self.d, "c.rmbackup")
        rename_rig(self.src, self.out, "Old", "New")
        rename_rig(self.out, back, "New", "Old")
        self.assertEqual(_blobs(back), _blobs(self.src))

    def test_a_payload_whose_own_name_differs_is_left_alone(self):
        src = build_rmbackup(os.path.join(self.d, "m.rmbackup"),
                             rigs=[_rig("Old", payload_name="Something Else")])
        result = rename_rig(src, self.out, "Old", "New")
        self.assertEqual((result.rigs, result.rig_payloads), (1, 0))
        rig, = Backup.open(self.out).rigs
        self.assertEqual(_payload_names(rig.blob), ["Something Else"])

    def test_an_unparseable_payload_is_renamed_in_metadata_only(self):
        src = build_rmbackup(os.path.join(self.d, "t.rmbackup"),
                             rigs=[{**_rig("Old"), "blob": _rig("Old")["blob"][:-4]}])
        result = rename_rig(src, self.out, "Old", "New")
        self.assertEqual((result.rigs, result.rig_payloads), (1, 0))

    def test_names_the_payload_cannot_hold_are_refused(self):
        for bad in ("Naïve", "x" * 33, " padded", "padded ", "", "tab\there"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    rename_rig(self.src, self.out, "Old", bad)
                self.assertFalse(os.path.exists(self.out))
        rename_rig(self.src, self.out, "Old", "x" * 32)

    def test_untouched_entries_stay_byte_identical(self):
        rename_rig(self.src, self.out, "Other", "Renamed")
        with zipfile.ZipFile(self.src) as a, zipfile.ZipFile(self.out) as b:
            self.assertEqual(a.read("info.xml"), b.read("info.xml"))


class RenamePayloadCliTest(unittest.TestCase):
    def _run(self, argv) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_reports_what_it_rewrote_and_what_it_left(self):
        d = tempfile.mkdtemp()
        src = build_rmbackup(os.path.join(d, "a.rmbackup"),
                             rigs=[_rig("Old"), _rig("Old", payload_name="Elsewhere")],
                             performances=[_perf("Set", "Old")])
        code, out, _ = self._run(["rename", src, "Old", "New", "-o", os.path.join(d, "b.rmbackup")])
        self.assertEqual(code, 0)
        self.assertIn("rewrote the name inside 1 rig payload(s) and 1 slot(s)", out)
        self.assertIn("left 1 payload(s)", out)

    def test_a_bad_name_is_one_line_exit_2(self):
        d = tempfile.mkdtemp()
        src = build_rmbackup(os.path.join(d, "a.rmbackup"), rigs=[_rig("Old")])
        code, out, err = self._run(["rename", src, "Old", "Café", "-o",
                                    os.path.join(d, "b.rmbackup")])
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err.count("\n"), 1)
        self.assertIn("ASCII", err)


class RenameLeavesUnparsedPerformancesTest(unittest.TestCase):
    def test_a_performance_payload_missing_a_track_keeps_its_bytes(self):
        d = tempfile.mkdtemp()
        whole = performance_blob(rig_track("Old"))
        short = whole[:whole.rfind(b"KTrk")]
        src = build_rmbackup(os.path.join(d, "src.rmbackup"), rigs=[_rig("Old")],
                             performances=[{"name": "P", "slots": [{"rig_name": "Old"}],
                                            "blob": short}])
        result = rename_rig(src, os.path.join(d, "out.rmbackup"), "Old", "New")
        after = Backup.open(os.path.join(d, "out.rmbackup")).performances[0]
        self.assertEqual((result.slots, result.slot_payloads), (1, 0))
        self.assertEqual(after.slots[0].rig_name, "New")
        self.assertEqual(after.blob, short)


if __name__ == "__main__":
    unittest.main()
