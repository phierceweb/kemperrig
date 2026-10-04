"""--json emits valid, parseable documents on every command that offers it."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from _fixture import build_rmbackup

from kemperrig import _json
from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services.performance import rig_gain_index

_CRITERIA = os.path.join(os.path.dirname(__file__), "..", "config", "example-shortlist.json")

RIGS = [
    {"name": "Recto-hi", "gain": "8.0", "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
    {"name": "Clean", "gain": "2.0", "amp_model": "AC30TBR", "cabinet_name": "Cab"},
]


def _lib(d: str) -> str:
    return build_rmbackup(os.path.join(d, "Lib.rmbackup"), rigs=RIGS,
                          performances=[{"name": "P1"}])


def _run_json(argv) -> dict:
    buf = StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    assert rc in (0, 1), rc
    return json.loads(buf.getvalue())


class JsonOutputTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = _lib(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_summary(self):
        doc = _run_json(["summary", self.path, "--json"])
        self.assertEqual(doc["rigs"], 2)
        self.assertEqual(doc["gain"]["max"], 8.0)
        self.assertIn("amp_models", doc)

    def test_rigs_carries_derived_flags(self):
        doc = _run_json(["rigs", self.path, "--json"])
        self.assertEqual(doc["count"], 2)
        by_name = {r["name"]: r for r in doc["rigs"]}
        self.assertIs(by_name["Recto-hi"]["is_di"], True)     # cabinet "N/A" = direct
        self.assertIs(by_name["Clean"]["is_di"], False)
        self.assertNotIn("blob", by_name["Clean"], "raw payload must not be serialized")

    def test_rigs_carries_raw_profile_columns(self):
        rig = _run_json(["rigs", self.path, "--json"])["rigs"][0]
        for key in ("profile_type", "profile_revision", "cabinet_type",
                    "cabinet_configuration"):
            self.assertIn(key, rig)

    def test_rigs_honours_filters(self):
        doc = _run_json(["rigs", self.path, "--json", "--gain-min", "5"])
        self.assertEqual([r["name"] for r in doc["rigs"]], ["Recto-hi"])

    def test_analyze(self):
        doc = _run_json(["analyze", self.path, "--json"])
        for key in ("orphaned_rigs", "amp_coverage", "similar_groups", "drive",
                    "ir_inventory", "non_monotonic_performances"):
            self.assertIn(key, doc)

    def test_presets(self):
        doc = _run_json(["presets", self.path, "--json"])
        self.assertIn("presets", doc)
        self.assertEqual(doc["count"], len(doc["presets"]))

    def test_performances(self):
        doc = _run_json(["performances", self.path, "--json"])
        self.assertEqual(doc["count"], 1)
        self.assertIn("gain_ladder", doc["performances"][0])

    def test_shortlist(self):
        doc = _run_json(["shortlist", self.path, "--criteria", _CRITERIA, "--json"])
        self.assertEqual([r["name"] for r in doc["rigs"]], ["Recto-hi"])


class AnalyzeExitCodeTest(unittest.TestCase):
    def test_strict_exits_one_when_there_are_findings(self):
        with tempfile.TemporaryDirectory() as d:
            path = _lib(d)  # no performance references these rigs -> both orphaned
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["analyze", path]), 0, "plain analyze always reports 0")
                self.assertEqual(main(["analyze", path, "--strict"]), 1)


if __name__ == "__main__":
    unittest.main()


class RendererParityTest(unittest.TestCase):
    def test_performances_json_carries_the_locked_ratio_the_text_view_shows(self):
        with tempfile.TemporaryDirectory() as d:
            p = build_rmbackup(
                os.path.join(d, "L.rmbackup"),
                rigs=[{"name": "A", "gain": "5.0"}],
                performances=[{"name": "P", "slots": [{"rig_name": "A"}]}])
            b = Backup.open(p)
            doc = _json.performances_doc(b.performances, rig_gain_index(b.rigs))
            self.assertIn("locked_ratio", doc["performances"][0])
