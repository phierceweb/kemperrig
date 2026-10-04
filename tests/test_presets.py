"""Preset modeling: cab-IR presets (class 6) vs effect presets (class 3, named type)."""

import os
import tempfile
import unittest

from _fixture import build_rmbackup

from kemperrig import Backup


def _backup(**kw):
    return Backup.open(build_rmbackup(os.path.join(tempfile.mkdtemp(), "t.rmbackup"), **kw))


class PresetTest(unittest.TestCase):
    def test_presets_parsed_and_classified(self):
        b = _backup(
            rigs=[{"name": "R", "amp_model": "Recto"}],
            presets=[
                {"name": "EVH 4x12 57", "preset_class": "6"},
                {"name": "My Boost", "preset_class": "3", "preset_type": "Green Scream"},
            ],
        )
        self.assertEqual(len(b.presets), 2)
        cab = next(p for p in b.presets if p.name == "EVH 4x12 57")
        self.assertTrue(cab.is_cab_ir)
        fx = next(p for p in b.presets if p.name == "My Boost")
        self.assertFalse(fx.is_cab_ir)
        self.assertEqual(fx.preset_type, "Green Scream")

    def test_no_presets_is_empty(self):
        b = _backup(rigs=[{"name": "R", "amp_model": "Recto"}])
        self.assertEqual(b.presets, [])

    def test_cli_presets_inventory(self):
        import contextlib
        import io

        from kemperrig.cli import main
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "p.rmbackup"),
            rigs=[{"name": "R", "amp_model": "Recto"}],
            presets=[{"name": "cab1", "preset_class": "6"},
                     {"name": "boost", "preset_class": "3", "preset_type": "Green Scream"}],
        )
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["presets", path])
        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Green Scream", out)
        self.assertIn("cab-ir", out.lower())


if __name__ == "__main__":
    unittest.main()
