"""Kemper CLI smoke + filter behavior on a synthetic backup (hermetic)."""

import contextlib
import io
import os
import tempfile
import unittest

from _fixture import build_rmbackup
from _payloads import amp_msg, make_blob, param_msg, performance_blob, string_msg

from kemperrig.cli import main

_EXAMPLE_CRITERIA = os.path.join(
    os.path.dirname(__file__), "..", "config", "example-shortlist.json")


class CliTest(unittest.TestCase):
    def setUp(self):
        self.path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "t.rmbackup"),
            user="Test User",
            rigs=[
                {"name": "Recto1", "author": "Profile Co", "gain": "6.0",
                 "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
                {"name": "SLOlead", "author": "Second Author", "gain": "7.5",
                 "amp_model": "SLO 100", "cabinet_name": "Marshall 1960"},
            ],
            performances=[{"name": "Bank A", "slots": [
                {"name": "Clean", "rig_name": "Recto1", "amp_name": "Dual Rectifier"}]}],
        )

    def test_readonly_commands_exit_zero(self):
        for argv in (["summary", self.path], ["rigs", self.path],
                     ["shortlist", self.path, "--criteria", _EXAMPLE_CRITERIA],
                     ["performances", self.path]):
            with self.subTest(cmd=argv[0]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(argv), 0)

    def test_rigs_amp_filter(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["rigs", self.path, "--amp", "dual"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Recto1", out)
        self.assertNotIn("SLOlead", out)

    def test_summary_reports_total(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["summary", self.path])
        self.assertIn("2", buf.getvalue())  # 2 rigs

    def test_rig_detail_decodes_blob_strings(self):
        blob = make_blob([[
            string_msg("PC_X", 1), string_msg("Profile Co", 2),
            string_msg("Mesa Recto OS 414+906.wav", 5),
        ]])
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "d.rmbackup"),
            rigs=[{"name": "PC_X", "amp_model": "Dual Rectifier", "gain": "6.0", "blob": blob}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["rig", path, "PC_X"])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("PC_X", out)
        self.assertIn("Mesa Recto OS 414+906.wav", out)

    def test_performances_show_effects_locked_pct(self):
        shared = [param_msg(b"\x00\x04\x00", b"\x00\x40"),
                  param_msg(b"\x00\x04\x01", b"\x00\x20"),
                  param_msg(b"\x00\x05\x00", b"\x01\x00"),
                  param_msg(b"\x00\x06\x00", b"\x00\x10")]
        slot_a = shared + [param_msg(b"\x00\x0a\x00", b"\x00\x01")]
        slot_b = shared + [param_msg(b"\x00\x0a\x00", b"\x00\x02")]
        blob = performance_blob(slot_a, slot_b)
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "p.rmbackup"),
            rigs=[{"name": "R", "amp_model": "Dual Rectifier"}],
            performances=[{"name": "Bank", "blob": blob, "slots": [
                {"name": "s1", "rig_name": "R"}, {"name": "s2", "rig_name": "R"}]}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["performances", path])
        self.assertIn("80%", buf.getvalue())

    def test_analyze_reports_orphan(self):
        # SLOlead is studio and no performance uses it -> orphan
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["analyze", self.path])
        self.assertEqual(rc, 0)
        self.assertIn("SLOlead", buf.getvalue())

    def test_rigs_boosted_filter(self):
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "bf.rmbackup"),
            rigs=[{"name": "Boost1", "amp_model": "Recto", "amp_comment": "Maxon 808"},
                  {"name": "Clean1", "amp_model": "Recto", "amp_comment": "Unboosted"}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["rigs", path, "--boosted"])
        out = buf.getvalue()
        self.assertIn("Boost1", out)
        self.assertNotIn("Clean1", out)

    def test_rig_shows_decoded_gain(self):
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "g.rmbackup"),
            rigs=[{"name": "G", "amp_model": "Dual Rectifier", "blob": make_blob([[amp_msg(6.4)]])}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["rig", path, "G"])
        self.assertIn("6.4", buf.getvalue())

    def test_rig_shows_raw_profile_columns(self):
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "p.rmbackup"),
            rigs=[{"name": "P", "profile_type": "20", "profile_revision": "1",
                   "cabinet_type": "3", "cabinet_configuration": "2x12"}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["rig", path, "P"])
        self.assertIn("profile type 20 rev 1 · cabinet type 3 · cabinet config 2x12",
                      buf.getvalue())

    def test_performances_show_gain_ladder(self):
        # ladder resolves each slot's rig name to the rig library's gain
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "l.rmbackup"),
            rigs=[{"name": "Clean1", "amp_model": "Dual Rectifier", "gain": "2.0"},
                  {"name": "Hi1", "amp_model": "Dual Rectifier", "gain": "7.0"}],
            performances=[{"name": "Bank", "slots": [
                {"name": "s1", "rig_name": "Clean1"}, {"name": "s2", "rig_name": "Hi1"}]}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["performances", path])
        out = buf.getvalue()
        self.assertIn("2.0", out)
        self.assertIn("7.0", out)


if __name__ == "__main__":
    unittest.main()
