"""Library report aggregation (the `summary` view)."""

import os
import tempfile
import unittest

from _fixture import build_rmbackup

from kemperrig import Backup
from kemperrig.services.report import build_report


class ReportTest(unittest.TestCase):
    def setUp(self):
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "t.rmbackup"),
            rigs=[
                {"name": "D01", "author": "Profile Co", "gain": "3.2",
                 "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
                {"name": "D02", "author": "Profile Co", "gain": "5.0",
                 "amp_model": "Dual Rectifier", "cabinet_name": "DIRECT"},
                {"name": "Lead", "author": "Second Author", "gain": "7.5",
                 "amp_model": "SLO 100", "cabinet_name": "Marshall 1960"},
            ],
            performances=[{"name": "P1", "slots": [
                {"name": "Clean", "rig_name": "D01"}]}],
        )
        self.report = build_report(Backup.open(path))

    def test_counts(self):
        self.assertEqual(self.report.total_rigs, 3)
        self.assertEqual(self.report.di_count, 2)
        self.assertEqual(self.report.studio_count, 1)
        self.assertEqual(self.report.performance_count, 1)

    def test_gain_stats(self):
        self.assertAlmostEqual(self.report.gain_mean, (3.2 + 5.0 + 7.5) / 3, places=3)
        self.assertEqual(self.report.gain_bands[3], 1)
        self.assertEqual(self.report.gain_bands[5], 1)
        self.assertEqual(self.report.gain_bands[7], 1)

    def test_top_models_and_authors(self):
        self.assertEqual(self.report.amp_models[0], ("Dual Rectifier", 2))
        self.assertEqual(self.report.authors[0], ("Profile Co", 2))


if __name__ == "__main__":
    unittest.main()
