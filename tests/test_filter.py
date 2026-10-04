"""Rig filtering predicates."""

import os
import tempfile
import unittest

from _fixture import build_rmbackup

from kemperrig import Backup
from kemperrig.services.filter import filter_rigs


class FilterTest(unittest.TestCase):
    def setUp(self):
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "t.rmbackup"),
            rigs=[
                {"name": "D01", "author": "Profile Co", "gain": "3.2",
                 "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
                {"name": "D02", "author": "Profile Co", "gain": "5.0", "amp_comment": "TS808 boost",
                 "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
                {"name": "Lead", "author": "Second Author", "gain": "7.5",
                 "folder": "Guitar/Soldano/SLO", "amp_model": "SLO 100",
                 "cabinet_name": "Marshall 1960"},
            ],
        )
        self.rigs = Backup.open(path).rigs

    def test_by_folder_substring(self):
        got = filter_rigs(self.rigs, folder="Soldano")
        self.assertEqual({r.name for r in got}, {"Lead"})
        self.assertEqual(filter_rigs(self.rigs, folder="nope"), [])

    def test_by_comment_substring(self):
        got = filter_rigs(self.rigs, comment="808")
        self.assertEqual({r.name for r in got}, {"D02"})
        self.assertEqual(filter_rigs(self.rigs, comment="nope"), [])

    def test_by_gain_max(self):
        got = filter_rigs(self.rigs, gain_max=5.0)
        self.assertEqual({r.name for r in got}, {"D01", "D02"})

    def test_gain_min_and_max_together_bracket(self):
        got = filter_rigs(self.rigs, gain_min=4.0, gain_max=6.0)
        self.assertEqual({r.name for r in got}, {"D02"})

    def test_by_amp_model_substring_ci(self):
        got = filter_rigs(self.rigs, amp_model="dual")
        self.assertEqual({r.name for r in got}, {"D01", "D02"})

    def test_by_gain_min(self):
        got = filter_rigs(self.rigs, gain_min=5.0)
        self.assertEqual({r.name for r in got}, {"D02", "Lead"})

    def test_by_di_only(self):
        got = filter_rigs(self.rigs, di=True)
        self.assertEqual({r.name for r in got}, {"D01", "D02"})

    def test_by_studio_only(self):
        got = filter_rigs(self.rigs, di=False)
        self.assertEqual({r.name for r in got}, {"Lead"})

    def test_by_author(self):
        got = filter_rigs(self.rigs, author="second")
        self.assertEqual({r.name for r in got}, {"Lead"})

    def test_combined(self):
        got = filter_rigs(self.rigs, amp_model="dual", gain_min=4.0)
        self.assertEqual({r.name for r in got}, {"D02"})

    def test_source_channel_boost_filters(self):
        import os
        import tempfile
        rigs = Backup.open(build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "f2.rmbackup"),
            rigs=[
                {"name": "m1", "source_amp": "Mesa Boogie", "amp_channel": "Lead",
                 "amp_comment": "Maxon 808"},
                {"name": "m2", "source_amp": "Marshall", "amp_channel": "Clean",
                 "amp_comment": "Unboosted"},
            ],
        )).rigs
        self.assertEqual({r.name for r in filter_rigs(rigs, source="mesa")}, {"m1"})
        self.assertEqual({r.name for r in filter_rigs(rigs, channel="clean")}, {"m2"})
        self.assertEqual({r.name for r in filter_rigs(rigs, boosted=True)}, {"m1"})
        self.assertEqual({r.name for r in filter_rigs(rigs, boosted=False)}, {"m2"})


if __name__ == "__main__":
    unittest.main()
