"""A dated snapshot — one bare SQLite db under `Backups/` — opens like any other library."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _fixture import build_rmbackup, build_snapshot
from _payloads import make_blob, string_msg

from kemperrig.cli import main
from kemperrig.model import Backup

RIG = {"name": "Crunch", "gain": "6.0", "amp_model": "Plexi", "cabinet_name": "4x12",
       "blob": make_blob([[string_msg("Crunch")]])}
PERF = {"name": "Set", "slots": [{"name": "Verse", "rig_name": "Crunch"}]}
PRESET = {"name": "Room", "preset_class": "3", "preset_type": "Spring"}
FACTORY = {"name": "Factory Hall", "preset_class": "3", "preset_type": "Hall"}


def _snap(d: str, name: str = "DEVICE - 2024-01-02 03-04-05R2.db", **kw) -> str:
    kw.setdefault("rigs", [RIG])
    kw.setdefault("performances", [PERF])
    kw.setdefault("presets", [PRESET])
    kw.setdefault("rom_presets", [FACTORY])
    return build_snapshot(os.path.join(d, name), **kw)


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class OpenSnapshotTest(unittest.TestCase):
    def test_rigs_performances_and_presets_come_from_one_db(self):
        with tempfile.TemporaryDirectory() as d:
            b = Backup.open(_snap(d))
            self.assertEqual([r.name for r in b.rigs], ["Crunch"])
            self.assertEqual(b.rigs[0].gain, 6.0)
            self.assertEqual(b.rigs[0].blob, RIG["blob"])
            self.assertEqual([p.name for p in b.performances], ["Set"])
            self.assertEqual([s.rig_name for s in b.performances[0].slots], ["Crunch"])
            self.assertEqual([p.name for p in b.presets], ["Room"])

    def test_snapshot_rigs_have_no_folder(self):
        with tempfile.TemporaryDirectory() as d:
            b = Backup.open(_snap(d))
            self.assertEqual({r.folder for r in b.rigs} | {p.folder for p in b.presets}, {""})

    def test_factory_rom_presets_are_not_presets(self):
        with tempfile.TemporaryDirectory() as d:
            b = Backup.open(_snap(d))
            self.assertNotIn("Factory Hall", [p.name for p in b.presets])

    def test_profile_columns_absent_from_a_snapshot_read_as_none(self):
        with tempfile.TemporaryDirectory() as d:
            rig = Backup.open(_snap(d)).rigs[0]
            self.assertIsNone(rig.profile_type)
            self.assertIsNone(rig.profile_revision)
            self.assertEqual(rig.cabinet_type, "0")

    def test_detected_by_content_not_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(len(Backup.open(_snap(d, name="copy.bin")).rigs), 1)

    def test_an_empty_snapshot_opens_empty(self):
        with tempfile.TemporaryDirectory() as d:
            b = Backup.open(_snap(d, rigs=[], performances=[], presets=[], rom_presets=[]))
            self.assertEqual((b.rigs, b.performances, b.presets), ([], [], []))


class NotASnapshotTest(unittest.TestCase):
    def test_sqlite_without_the_snapshot_tables_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = _snap(d, omit_tables=("Performances", "Presets"))
            with self.assertRaises(ValueError) as cm:
                Backup.open(p)
            self.assertIn("not a Rig Manager snapshot", str(cm.exception))
            self.assertIn("Performances", str(cm.exception))

    def test_zero_byte_file_is_a_one_line_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "DEVICE - 2024-01-02 03-04-05R2.db")
            Path(p).write_bytes(b"")
            code, out, err = _run(["summary", p])
            self.assertEqual(code, 1)
            self.assertEqual(err.count("\n"), 1)
            self.assertIn("empty file", err)

    def test_truncated_snapshot_is_a_one_line_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = _snap(d)
            Path(p).write_bytes(Path(p).read_bytes()[:200])
            code, _, err = _run(["summary", p])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("kemperrig: "), err)
            self.assertIn(os.path.basename(p), err)
            self.assertEqual(err.count("\n"), 1)


class SnapshotCommandsTest(unittest.TestCase):
    def test_read_commands_take_a_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            p = _snap(d)
            for argv in (["summary", p], ["rigs", p], ["performances", p], ["presets", p],
                         ["rig", p, "Crunch"], ["analyze", p]):
                code, _, err = _run(argv)
                self.assertEqual((code, err), (0, ""), argv)

    def test_diff_between_two_snapshots(self):
        with tempfile.TemporaryDirectory() as d:
            a = _snap(d, name="DEVICE - 2024-01-02 03-04-05R2.db")
            b = _snap(d, name="DEVICE - 2024-01-03 03-04-05R2.db",
                      rigs=[{**RIG, "gain": "7.5"}])
            self.assertEqual(_run(["diff", a, a])[0], 0)
            code, out, _ = _run(["diff", a, b])
            self.assertEqual(code, 1)
            self.assertIn("gain: 6.0 -> 7.5", out)

    def test_diff_between_a_snapshot_and_a_backup(self):
        with tempfile.TemporaryDirectory() as d:
            snap = _snap(d)
            backup = build_rmbackup(os.path.join(d, "lib.rmbackup"), rigs=[RIG],
                                    performances=[PERF])
            code, out, err = _run(["diff", snap, backup])
            self.assertEqual((code, err), (1, ""))
            self.assertNotIn("performances", out)

    def test_a_folderless_rig_is_keyed_by_its_bare_name_everywhere(self):
        with tempfile.TemporaryDirectory() as d:
            p = _snap(d, rigs=[RIG, {"name": "Cut", "blob": RIG["blob"][:-3]}],
                      performances=[])
            docs = {cmd: json.loads(_run([cmd, p, "--json", *extra])[1])
                    for cmd, extra in (("analyze", []), ("pages", ["--all"]))}
            self.assertEqual(docs["analyze"]["unparsed"]["rigs"], ["Cut"])
            self.assertEqual(docs["pages"]["unparsed"], ["Cut"])
            self.assertEqual(sorted(docs["analyze"]["orphaned_rigs"]), ["Crunch", "Cut"])
            later = _snap(d, name="DEVICE - 2024-01-03 03-04-05R2.db", rigs=[], performances=[])
            self.assertEqual(json.loads(_run(["diff", p, later, "--json"])[1])["rigs"]["removed"],
                             ["Crunch", "Cut"])


if __name__ == "__main__":
    unittest.main()
