"""`kemperrig history` — sources, the library default, output and exit codes."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _fixture import build_snapshot, sample_library

from kemperrig.cli import main

A = {"name": "A", "gain": "5.0", "blob": b"KThd-a1"}
B = {"name": "B", "gain": "7.0", "blob": b"KThd-b1"}


def _snaps(d: str) -> list[str]:
    return [build_snapshot(os.path.join(d, f"DEV - 2024-01-0{n} 10-00-00R2.db"), rigs=rigs)
            for n, rigs in ((1, [A]), (2, [A, B]), (3, [{**A, "blob": b"KThd-a2"}, B]))]


def _run(argv, env: dict | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env or {}, clear=False):
        if env is None or "KEMPERRIG_LIBRARY" not in env:
            os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


class HistoryCliTest(unittest.TestCase):
    def test_timeline_text(self):
        with tempfile.TemporaryDirectory() as d:
            _snaps(d)
            code, out, err = _run(["history", d])
            self.assertEqual((code, err), (0, ""))
            self.assertIn("2024-01-01 10:00:00", out)
            self.assertIn("rigs +1", out)
            self.assertIn("rigs ~1", out)
            self.assertNotIn("\ndevice ", out)

    def test_timeline_json(self):
        with tempfile.TemporaryDirectory() as d:
            files = _snaps(d)
            code, out, _ = _run(["history", *files, "--json"])
            self.assertEqual(code, 0)
            doc = json.loads(out)
            self.assertEqual(doc["order"], "name")
            self.assertEqual([t["label"] for t in doc["timeline"]],
                             ["2024-01-01 10:00:00", "2024-01-02 10:00:00",
                              "2024-01-03 10:00:00"])
            self.assertIsNone(doc["timeline"][0]["since"])
            since = doc["timeline"][2]["since"]
            self.assertEqual(since["path"], files[1])
            self.assertEqual(since["rigs"], {"added": 0, "removed": 0, "changed": 1})
            self.assertEqual(doc["timeline"][2]["rigs"], 2)

    def test_rig_text_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            _snaps(d)
            code, out, _ = _run(["history", d, "--rig", "A"])
            self.assertEqual(code, 0)
            self.assertIn("2 versions", out)
            self.assertIn("changed", out)
            doc = json.loads(_run(["history", d, "--rig", "A", "--json"])[1])
            self.assertEqual(doc["rig"]["name"], "A")
            self.assertEqual([v["files"] for v in doc["rig"]["versions"]], [2, 1])
            self.assertEqual([s["changed"] for s in doc["rig"]["sightings"]],
                             [False, False, True])

    def test_rig_nowhere_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            _snaps(d)
            code, out, _ = _run(["history", d, "--rig", "Nowhere"])
            self.assertEqual(code, 0)
            self.assertIn("in none of 3", out)

    def test_devices_get_headings_when_more_than_one(self):
        with tempfile.TemporaryDirectory() as d:
            build_snapshot(os.path.join(d, "DEVA - 2024-01-01 10-00-00R2.db"), rigs=[A])
            build_snapshot(os.path.join(d, "DEVB - 2024-01-01 10-00-00R2.db"), rigs=[B])
            out = _run(["history", d])[1]
            self.assertIn("device DEVA", out)
            self.assertIn("device DEVB", out)

    def test_skipped_file_is_one_stderr_line_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as d:
            _snaps(d)
            Path(d, "DEV - 2024-01-04 10-00-00R2.db").write_bytes(b"")
            code, out, err = _run(["history", d])
            self.assertEqual(code, 0)
            self.assertEqual(err.count("\n"), 1)
            self.assertTrue(err.startswith("kemperrig: skipped DEV - 2024-01-04"), err)
            self.assertIn("1 skipped", out)

    def test_order_flag(self):
        with tempfile.TemporaryDirectory() as d:
            _snaps(d)
            self.assertEqual(_run(["history", d, "--order", "mtime"])[0], 0)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
                main(["history", d, "--order", "size"])
            self.assertEqual(cm.exception.code, 2)


class HistoryDefaultSourceTest(unittest.TestCase):
    def test_defaults_to_the_library_backups_folder(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "Backups"))
            _snaps(os.path.join(d, "Backups"))
            code, out, err = _run(["history"], {"KEMPERRIG_LIBRARY": d})
            self.assertEqual((code, err), (0, ""))
            self.assertIn("3 files", out)

    def test_a_library_without_backups_is_a_one_line_error(self):
        with tempfile.TemporaryDirectory() as d:
            lib = sample_library(d)
            code, _, err = _run(["history"], {"KEMPERRIG_LIBRARY": lib})
            self.assertEqual(code, 1)
            self.assertEqual(err.count("\n"), 1)
            self.assertIn("Backups", err)

    def test_no_source_and_no_library_is_a_usage_error(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            _run(["history"])
        self.assertEqual(cm.exception.code, 2)

    def test_a_missing_source_is_a_one_line_error(self):
        code, _, err = _run(["history", os.path.join(tempfile.gettempdir(), "nope R2.db")])
        self.assertEqual(code, 1)
        self.assertEqual(err.count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
