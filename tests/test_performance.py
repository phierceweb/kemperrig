"""Performance figures: the gain ladder from the rig library, and the locked share of the
slots in use."""

import os
import tempfile
import unittest

from _fixture import build_rmbackup
from _payloads import amp_msg, performance_blob, rig_track

from kemperrig import Backup
from kemperrig.services.performance import gain_ladder, locked_ratio, rig_gain_index


class GainLadderTest(unittest.TestCase):
    def setUp(self):
        self.backup = Backup.open(build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "t.rmbackup"),
            rigs=[
                {"name": "Clean1", "amp_model": "Dual Rectifier", "gain": "2.0"},
                {"name": "Hi1", "amp_model": "Dual Rectifier", "gain": "7.0"},
            ],
            performances=[{"name": "Bank", "slots": [
                {"name": "c", "rig_name": "Clean1"},
                {"name": "h", "rig_name": "Hi1"},
                {"name": "x", "rig_name": "NotInLibrary"},
            ]}],
        ))

    def test_ladder_resolves_slot_rig_gains(self):
        index = rig_gain_index(self.backup.rigs)
        ladder = gain_ladder(self.backup.performances[0], index)
        self.assertEqual(ladder, [2.0, 7.0, None])  # unknown slot rig -> None


class LockedRatioTest(unittest.TestCase):
    def _ratio(self, slots, *tracks):
        return locked_ratio(Backup.open(build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "t.rmbackup"), rigs=[],
            performances=[{"name": "P", "slots": slots, "blob": performance_blob(*tracks)}],
        )).performances[0])

    def test_only_the_slots_in_use_are_compared(self):
        same, other = rig_track("A") + [amp_msg(3.0)], rig_track("Z") + [amp_msg(9.0)]
        self.assertEqual(self._ratio([{"rig_name": "A"}, {"rig_name": None}, {"rig_name": "A"}],
                                     same, other, same), 1.0)

    def test_one_slot_in_use_has_no_share(self):
        self.assertIsNone(self._ratio([{"rig_name": "A"}], rig_track("A"), rig_track("A")))


if __name__ == "__main__":
    unittest.main()
