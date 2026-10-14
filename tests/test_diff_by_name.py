"""Sources that file differently — a snapshot or a pack against a library — matched by path,
by name with `--by-name`, and the hint `diff` gives when only one side files anything."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from _fixture import build_rmbackup, build_snapshot
from _payloads import amp_msg, make_blob, rig_track

from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services.diff import diff_rigs, folders_on_one_side

RIG_A = {"name": "A", "gain": "5.0", "amp_model": "Dual Rectifier", "cabinet_name": "N/A"}
RIG_B = {"name": "B", "gain": "7.0", "amp_model": "SLO 100", "cabinet_name": "N/A"}


def _backup(d: str, name: str, rigs, **kw) -> str:
    return build_rmbackup(os.path.join(d, name), rigs=rigs, **kw)


class ByNameTest(unittest.TestCase):
    def _pair(self, d, lib_rigs, snap_rigs):
        lib = Backup.open(_backup(d, "lib.rmbackup", lib_rigs))
        snap = Backup.open(build_snapshot(os.path.join(d, "snap.db"), rigs=snap_rigs))
        return lib, snap

    def test_by_path_a_snapshot_never_meets_a_library(self):
        with tempfile.TemporaryDirectory() as d:
            lib, snap = self._pair(d, [RIG_A, RIG_B], [RIG_A, RIG_B])
            found = diff_rigs(lib, snap)
            self.assertEqual((len(found.removed), len(found.added)), (2, 2))

    def test_by_path_it_meets_the_rigs_at_a_librarys_top_level(self):
        with tempfile.TemporaryDirectory() as d:
            lib, snap = self._pair(d, [{**RIG_A, "folder": ""}, {**RIG_B, "folder": "X"}],
                                   [RIG_A, RIG_B])
            found = diff_rigs(lib, snap)
            self.assertEqual((found.removed, found.added, found.changed), (["X/B"], ["B"], []))

    def test_by_name_it_does_and_reports_real_changes(self):
        with tempfile.TemporaryDirectory() as d:
            lib, snap = self._pair(d, [RIG_A, RIG_B], [RIG_A, {**RIG_B, "gain": "8.0"}])
            found = diff_rigs(lib, snap, by_name=True)
            self.assertEqual((found.added, found.removed), ([], []))
            self.assertEqual([(c.key, [f.field for f in c.changes]) for c in found.changed],
                             [("B", ["gain"])])
            self.assertEqual(found.uncompared, ["profile_revision", "profile_type"])

    def test_one_name_two_payloads_pairs_by_payload(self):
        blob5, blob6 = (make_blob([rig_track("A") + [amp_msg(g)]]) for g in (5.0, 6.0))
        with tempfile.TemporaryDirectory() as d:
            lib, snap = self._pair(
                d, [{**RIG_A, "folder": "X", "blob": blob5}, {**RIG_A, "folder": "Y", "blob": blob6}],
                [{**RIG_A, "blob": blob6}, {**RIG_A, "blob": blob5}])
            self.assertTrue(diff_rigs(lib, snap, by_name=True).empty)


class FoldersOnOneSideTest(unittest.TestCase):
    def test_only_filed_records_against_a_side_that_files_none(self):
        with tempfile.TemporaryDirectory() as d:
            filed = Backup.open(_backup(d, "filed.rmbackup", [RIG_A]))
            top = Backup.open(_backup(d, "top.rmbackup", [{**RIG_A, "folder": ""}]))
            snap = Backup.open(build_snapshot(os.path.join(d, "snap.db"), rigs=[RIG_A]))
            empty = Backup.open(build_snapshot(os.path.join(d, "empty.db")))
            sources = {"filed": filed, "top": top, "snap": snap, "empty": empty}
            for pair, expected in ((("snap", "filed"), True), (("filed", "snap"), True),
                                   (("top", "filed"), True), (("snap", "top"), False),
                                   (("filed", "filed"), False), (("snap", "snap"), False),
                                   (("snap", "empty"), False), (("filed", "empty"), False)):
                with self.subTest(pair=pair):
                    self.assertIs(folders_on_one_side(*(sources[s] for s in pair)), expected)


class ByNameCliTest(unittest.TestCase):
    def test_hint_flag_and_json(self):
        with tempfile.TemporaryDirectory() as d:
            lib = _backup(d, "lib.rmbackup", [RIG_A])
            snap = build_snapshot(os.path.join(d, "snap.db"), rigs=[RIG_A])
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["diff", lib, snap]), 1)
            self.assertIn("--by-name", err.getvalue())
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["diff", lib, snap, "--by-name"]), 0)
            self.assertIn("not compared", out.getvalue())
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["diff", lib, snap, "--by-name", "--json"]), 0)
            doc = json.loads(out.getvalue())
            self.assertEqual((doc["matched_by"], doc["uncompared"]["rigs"]),
                             ("name", ["profile_revision", "profile_type"]))
            self.assertEqual(err.getvalue(), "")

    def test_no_hint_when_the_library_files_nothing_either(self):
        with tempfile.TemporaryDirectory() as d:
            top = _backup(d, "top.rmbackup", [{**RIG_A, "folder": ""}])
            snap = build_snapshot(os.path.join(d, "snap.db"), rigs=[RIG_A])
            err = StringIO()
            with redirect_stdout(StringIO()), redirect_stderr(err):
                self.assertEqual(main(["diff", top, snap]), 0)
            self.assertEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
