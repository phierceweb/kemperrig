"""`rig` and `pages` pick one rig: by name, then folder, then payload digest."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _fixture import build_rmbackup, build_snapshot
from _payloads import amp_msg, make_blob, rig_track

from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services.diff import digest
from kemperrig.services.filter import find_rig


def _blob(gain: float) -> bytes:
    return make_blob([rig_track("Dup") + [amp_msg(gain)]])


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


class FindRigTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.low, self.high = _blob(2.0), _blob(8.0)
        self.snap = build_snapshot(os.path.join(d, "S - 2020-01-01 00-00-00R2.db"),
                                   rigs=[{"name": "Dup", "blob": self.low},
                                         {"name": "Dup", "blob": self.high}])
        self.rigs = Backup.open(self.snap).rigs

    def test_without_folders_the_error_offers_the_payload_digests(self):
        with self.assertRaises(ValueError) as cm:
            find_rig(self.rigs, "Dup")
        self.assertIn("--payload", str(cm.exception))
        self.assertIn(digest(self.low), str(cm.exception))
        self.assertNotIn("(?)", str(cm.exception))

    def test_a_digest_prefix_picks_one(self):
        rig = find_rig(self.rigs, "Dup", payload=digest(self.high)[:6].upper())
        self.assertEqual(rig.blob, self.high)

    def test_distinct_folders_still_suggest_folder(self):
        d = tempfile.mkdtemp()
        lib = build_rmbackup(os.path.join(d, "l.rmbackup"),
                             rigs=[{"name": "Dup", "folder": "A", "blob": self.low},
                                   {"name": "Dup", "folder": "B", "blob": self.high}])
        with self.assertRaises(ValueError) as cm:
            find_rig(Backup.open(lib).rigs, "Dup")
        self.assertIn("--folder (A, B)", str(cm.exception))

    def test_identical_payloads_are_one_answer(self):
        d = tempfile.mkdtemp()
        snap = build_snapshot(os.path.join(d, "S - 2020-01-01 00-00-00R2.db"),
                              rigs=[{"name": "Dup", "blob": self.low},
                                    {"name": "Dup", "blob": self.low}])
        self.assertEqual(find_rig(Backup.open(snap).rigs, "Dup").blob, self.low)

    def test_rig_and_pages_take_payload(self):
        prefix = digest(self.low)[:8]
        for argv in (["rig", self.snap, "Dup", "--payload", prefix],
                     ["pages", self.snap, "Dup", "--payload", prefix]):
            with self.subTest(argv[0]):
                code, out, err = _run(argv)
                self.assertEqual(code, 0, err)
                self.assertTrue(out)


if __name__ == "__main__":
    unittest.main()
