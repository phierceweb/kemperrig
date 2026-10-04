"""`summary --write-golden` — the census file, and every refusal as a one-line exit 2 that
writes nothing and leaves the source byte-identical."""

import io
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _fixture import build_rmbackup
from _payloads import amp_msg, make_blob, rig_track

from kemperrig import _json
from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services import census

RIGS = [{"name": n, "folder": "Amps/Plexi", "gain": g, "amp_model": "Plexi",
         "blob": make_blob([rig_track(n) + [amp_msg(float(g))]])}
        for n, g in (("Clean", "2.0"), ("Lead", "7.0"))]


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


class _Case(unittest.TestCase):
    def setUp(self):
        self.d = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.lib = build_rmbackup(str(self.d / "lib.rmbackup"), rigs=RIGS)
        self.before = Path(self.lib).read_bytes()
        self.golden = self.d / "golden.json"

    def tearDown(self):
        self.assertEqual(Path(self.lib).read_bytes(), self.before, "source was modified")

    def _refused(self, argv, fragment: str) -> None:
        code, out, err = _run(argv)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("kemperrig: "), err)
        self.assertEqual(err.count("\n"), 1, err)
        self.assertIn(fragment, err)


class WriteGoldenTest(_Case):
    def test_writes_the_census_and_says_where(self):
        code, out, err = _run(["summary", self.lib, "--write-golden", str(self.golden)])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out, f"wrote census to {self.golden}\n")
        want = _json.census_text(census.take(Backup.open(self.lib)))
        self.assertEqual(self.golden.read_text(encoding="utf-8"), want)

    def test_a_rewrite_is_byte_identical(self):
        _run(["summary", self.lib, "--write-golden", str(self.golden)])
        first = self.golden.read_bytes()
        code, _, _ = _run(["summary", self.lib, "--write-golden", str(self.golden), "--force"])
        self.assertEqual(code, 0)
        self.assertEqual(self.golden.read_bytes(), first)

    def test_missing_folders_are_created(self):
        target = self.d / "new" / "deeper" / "golden.json"
        code, _, _ = _run(["summary", self.lib, "--write-golden", str(target)])
        self.assertEqual(code, 0)
        self.assertTrue(target.is_file())

    def test_the_library_comes_from_the_environment(self):
        with mock.patch.dict(os.environ, {"KEMPERRIG_LIBRARY": self.lib}):
            with redirect_stdout(io.StringIO()):
                code = main(["summary", "--write-golden", str(self.golden)])
        self.assertEqual(code, 0)
        self.assertTrue(self.golden.is_file())

    def test_the_summary_itself_is_unchanged_without_the_flag(self):
        code, out, _ = _run(["summary", self.lib])
        self.assertEqual(code, 0)
        self.assertIn("rigs: 2", out)
        self.assertFalse(self.golden.exists())


class RefusalTest(_Case):
    def test_an_existing_file_needs_force(self):
        self.golden.write_text("keep me", encoding="utf-8")
        self._refused(["summary", self.lib, "--write-golden", str(self.golden)], "--force")
        self.assertEqual(self.golden.read_text(encoding="utf-8"), "keep me")
        code, _, _ = _run(["summary", self.lib, "--write-golden", str(self.golden), "--force"])
        self.assertEqual(code, 0)
        self.assertNotEqual(self.golden.read_text(encoding="utf-8"), "keep me")

    def test_never_the_source_even_with_force(self):
        self._refused(["summary", self.lib, "--write-golden", self.lib, "--force"],
                      "overwrite the source")

    def test_never_the_source_through_a_symlink(self):
        link = self.d / "link.json"
        link.symlink_to(self.lib)
        self._refused(["summary", self.lib, "--write-golden", str(link), "--force"],
                      "overwrite the source")
        self.assertTrue(link.is_symlink())

    def test_never_through_a_symlink_loop(self):
        (self.d / "a").symlink_to(self.d / "b")
        (self.d / "b").symlink_to(self.d / "a")
        self._refused(["summary", self.lib, "--write-golden", str(self.d / "a" / "g.json")],
                      "cannot resolve")

    def test_never_inside_a_live_source(self):
        live = self.d / "live"
        with zipfile.ZipFile(self.lib) as zf:
            zf.extractall(live)
        before = sorted(p.relative_to(live) for p in live.rglob("*"))
        self._refused(["summary", str(live), "--write-golden", str(live / "golden.json"),
                       "--force"], "inside the source")
        self._refused(["summary", str(live), "--write-golden",
                       str(live / "sub" / ".." / "x.json")], "inside the source")
        self.assertEqual(sorted(p.relative_to(live) for p in live.rglob("*")), before)

    def test_never_inside_any_rig_manager_library(self):
        other = self.d / "other"
        (other / "Local Library" / "Amps").mkdir(parents=True)
        target = other / "Local Library" / "golden.json"
        self._refused(["summary", self.lib, "--write-golden", str(target), "--force"],
                      "Rig Manager library")
        self.assertFalse(target.exists())

    def test_a_folder_is_not_a_file(self):
        self._refused(["summary", self.lib, "--write-golden", str(self.d), "--force"],
                      "is a folder")

    def test_an_empty_path_names_nothing(self):
        self._refused(["summary", self.lib, "--write-golden", " "], "no census file")

    def test_force_alone_is_an_error(self):
        self._refused(["summary", self.lib, "--force"], "--write-golden")

    def test_json_and_write_golden_are_exclusive(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            main(["summary", self.lib, "--json", "--write-golden", str(self.golden)])
        self.assertEqual(cm.exception.code, 2)
        self.assertFalse(self.golden.exists())

    def test_the_writer_guards_a_direct_caller(self):
        with self.assertRaises(ValueError):
            census.write("{}\n", self.lib, source=self.lib, force=True)


if __name__ == "__main__":
    unittest.main()
