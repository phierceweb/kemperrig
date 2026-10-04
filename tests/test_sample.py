"""The synthetic sample library holds every source kind and each finding the smoke test needs."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _sample import DEVICE, RIG_NAMES, build_sample

from kemperrig import _sysex
from kemperrig.model import Backup

_SCRIPT = Path(__file__).with_name("_sample.py")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True)


class SampleContentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.paths = build_sample(Path(cls._tmp.name) / "sample")
        cls.backup = Backup.open(str(cls.paths.backup))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _rig(self, name, folder=None):
        return next(r for r in self.backup.rigs
                    if r.name == name and (folder is None or r.folder.endswith(folder)))

    def test_every_source_kind_opens(self):
        p = self.paths
        for source in (p.backup, p.live, *p.snapshots, p.rigpack, p.presetpack):
            with self.subTest(source=source.name):
                self.assertTrue(Backup.open(str(source)).rigs or Backup.open(str(source)).presets)

    def test_the_backup_and_the_live_tree_hold_the_same_rigs(self):
        live = Backup.open(str(self.paths.live))
        self.assertEqual(sorted(r.name for r in live.rigs), sorted(r.name for r in self.backup.rigs))
        self.assertEqual(sorted({r.name for r in self.backup.rigs}), RIG_NAMES)

    def test_snapshots_are_named_for_one_device(self):
        self.assertTrue(all(s.name.startswith(f"{DEVICE} - ") for s in self.paths.snapshots))

    def test_one_payload_does_not_parse(self):
        self.assertIsNone(_sysex.parse_tracks(self._rig("Broken Rig").blob))

    def test_one_rig_holds_a_reverb_only_in_function_08(self):
        self.assertIn(b"\x00\x20\x33\x00\x00\x08\x00\x4b", self._rig("Legacy Room").blob)

    def test_one_performance_slot_names_a_rig_the_library_lacks(self):
        names = {r.name for r in self.backup.rigs}
        slots = [s.rig_name for p in self.backup.performances for s in p.slots if s.rig_name]
        self.assertIn("Gone Rig", slots)
        self.assertNotIn("Gone Rig", names)

    def test_two_rigs_share_one_payload(self):
        self.assertEqual(self._rig("Plexi Crunch", "Plexi").blob,
                         self._rig("Plexi Crunch", "Imported").blob)


class SampleScriptTest(unittest.TestCase):
    def test_it_writes_into_an_empty_folder(self):
        with tempfile.TemporaryDirectory() as d:
            done = _run(str(Path(d) / "s"))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((Path(d) / "s" / "Library.rmbackup").is_file())

    def test_a_non_empty_folder_needs_force(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "keep.txt").write_text("x")
            done = _run(d)
            self.assertEqual(done.returncode, 2)
            self.assertEqual(len(done.stderr.strip().splitlines()), 1)
            self.assertIn("--force", done.stderr)
            self.assertEqual(_run(d, "--force").returncode, 0)
            self.assertEqual((Path(d) / "keep.txt").read_text(), "x")

    def test_a_folder_inside_a_rig_manager_library_is_refused_even_with_force(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Local Library").mkdir()
            done = _run(str(Path(d) / "inside"), "--force")
            self.assertEqual(done.returncode, 2)
            self.assertIn("Rig Manager library", done.stderr)
            self.assertFalse((Path(d) / "inside").exists())


if __name__ == "__main__":
    unittest.main()
