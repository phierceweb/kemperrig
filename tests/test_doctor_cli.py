"""`kemperrig doctor` — output, --json, --strict exit codes and --device-backup."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _fixture import build_rmbackup, build_snapshot
from _payloads import amp_msg, make_blob, performance_blob, rig_track

from kemperrig.cli import main


def _rig(name: str, *, gain: str = "5.0", payload_name: str | None = None) -> dict:
    return {"name": name, "folder": "Amps", "gain": gain,
            "blob": make_blob([rig_track(payload_name or name) + [amp_msg(5.0)]])}


def _perf(name: str, *rigs: str) -> dict:
    return {"name": name, "slots": [{"name": r, "rig_name": r} for r in rigs],
            "blob": performance_blob(*(rig_track(r) for r in rigs))}


def _run(argv, env: dict | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env or {}, clear=False):
        if env is None:
            os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


class DoctorCliTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _lib(self, **kw) -> str:
        return build_rmbackup(os.path.join(self.d, "lib.rmbackup"), **kw)

    def test_a_clean_library_passes_strict(self):
        lib = self._lib(rigs=[_rig("A")], performances=[_perf("Set", "A")])
        code, out, err = _run(["doctor", lib, "--strict"])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("dangling slots: 0", out)

    def test_a_dangling_slot_fails_only_strict(self):
        lib = self._lib(rigs=[_rig("A")], performances=[_perf("Set", "A", "Gone")])
        code, out, _ = _run(["doctor", lib])
        self.assertEqual(code, 0)
        self.assertIn("Set · slot 2 · 'Gone'", out)
        self.assertEqual(_run(["doctor", lib, "--strict"])[0], 1)

    def test_informational_findings_do_not_fail_strict(self):
        lib = self._lib(rigs=[_rig("A", gain="8.0", payload_name="Z")],
                        performances=[_perf("Set", "A")])
        code, out, _ = _run(["doctor", lib, "--strict"])
        self.assertEqual(code, 0)
        self.assertIn("the payload says 'Z'", out)
        self.assertIn("stored 8.0, decoded 5.0", out)

    def test_a_broken_payload_is_reported_not_raised(self):
        whole = make_blob([rig_track("Cut") + [amp_msg(5.0)]])
        lib = self._lib(rigs=[{"name": "Cut", "folder": "Amps", "blob": whole[:-6]}])
        code, out, err = _run(["doctor", lib, "--strict"])
        self.assertEqual((code, err), (1, ""))
        self.assertIn("rig Amps/Cut — truncated blob", out)

    def test_json(self):
        lib = self._lib(rigs=[_rig("A")], performances=[_perf("Set", "A", "Gone")])
        code, out, _ = _run(["doctor", lib, "--json"])
        doc = json.loads(out)
        self.assertEqual(code, 0)
        self.assertTrue(doc["defective"])
        self.assertEqual(doc["definite"]["dangling_slots"],
                         [{"performance": "Set", "slot": 2, "rig_name": "Gone"}])
        self.assertIsNone(doc["informational"]["device_only_slots"])
        self.assertEqual(set(doc["informational"]),
                         {"device_only_slots", "unread_payloads", "gain_mismatches",
                          "name_mismatches", "unused_cab_irs"})

    def test_device_backup_moves_a_slot_to_the_device_and_passes_strict(self):
        lib = self._lib(rigs=[_rig("A")], performances=[_perf("Set", "A", "Pulled")])
        snap = build_snapshot(os.path.join(self.d, "DEV - 2024-01-01 10-00-00R2.db"),
                              rigs=[_rig("Pulled")])
        code, out, _ = _run(["doctor", lib, "--device-backup", snap, "--strict"])
        self.assertEqual(code, 0)
        self.assertIn("on the device only: 1", out)
        doc = json.loads(_run(["doctor", lib, "--device-backup", snap, "--json"])[1])
        self.assertEqual(doc["informational"]["device_only_slots"],
                         [{"performance": "Set", "slot": 2, "rig_name": "Pulled"}])

    def test_a_missing_device_backup_is_one_line_and_exit_1(self):
        lib = self._lib(rigs=[_rig("A")])
        code, out, err = _run(["doctor", lib, "--device-backup",
                               os.path.join(self.d, "missing.db")])
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("kemperrig: ") and err.count("\n") == 1, err)

    def test_the_library_comes_from_the_environment(self):
        lib = self._lib(rigs=[_rig("A")], performances=[_perf("Set", "A")])
        code, out, _ = _run(["doctor"], env={"KEMPERRIG_LIBRARY": lib})
        self.assertEqual(code, 0)
        self.assertIn("1 rigs", out)


if __name__ == "__main__":
    unittest.main()
