"""Rename a rig and repack the .rmbackup — round-trip, byte-faithfulness, and the
performance slots that point at the renamed rig by name."""

import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from _fixture import build_rmbackup

from kemperrig import Backup, _tables
from kemperrig.cli import main
from kemperrig.services.analyze import orphaned_rigs
from kemperrig.services.edit import rename_rig


def _entry(path: str, name: str) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name)


class RenameTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = build_rmbackup(
            os.path.join(self.d, "src.rmbackup"), user="Test User",
            rigs=[
                {"name": "A", "amp_model": "Dual Rectifier", "gain": "3.0",
                 "folder": "Guitar/Mesa-Boogie/Dual Rectifier"},
                {"name": "B", "amp_model": "Dual Rectifier", "gain": "5.0",
                 "folder": "Guitar/Mesa-Boogie/Dual Rectifier"},
                {"name": "C", "amp_model": "SLO 100", "gain": "7.0",
                 "folder": "Amps/Soldano/Lead"},
            ],
            performances=[{"name": "Bank", "slots": [{"name": "s", "rig_name": "A"}]}],
        )
        self.dst = os.path.join(self.d, "out.rmbackup")

    def test_rename_changes_only_target(self):
        self.assertEqual(rename_rig(self.src, self.dst, "A", "A2").rigs, 1)
        names = {r.name for r in Backup.open(self.dst).rigs}
        self.assertIn("A2", names)
        self.assertNotIn("A", names)
        self.assertEqual({"A2", "B", "C"}, names)

    def test_untouched_parts_are_byte_identical(self):
        rename_rig(self.src, self.dst, "A", "A2")
        # the rig lives in the Mesa folder db; the SLO db and info.xml have no stake in it
        for name in ("Local Library/Amps/Soldano/Lead/repositoryR2.db", "info.xml"):
            self.assertEqual(_entry(self.src, name), _entry(self.dst, name), name)

    def test_the_performance_db_changes_only_when_a_slot_referenced_the_rig(self):
        perf = "Prf/Local Library/repositoryR2.db"
        rename_rig(self.src, self.dst, "A", "A2")       # slot 1 of "Bank" points at A
        self.assertNotEqual(_entry(self.src, perf), _entry(self.dst, perf))

        other = os.path.join(self.d, "other.rmbackup")
        rename_rig(self.src, other, "C", "C2")          # no slot points at C
        self.assertEqual(_entry(self.src, perf), _entry(other, perf))

    def test_other_metadata_preserved(self):
        rename_rig(self.src, self.dst, "A", "A2")
        b = Backup.open(self.dst)
        self.assertEqual(b.info.user, "Test User")
        self.assertEqual(len(b.performances), 1)
        a2 = next(r for r in b.rigs if r.name == "A2")
        self.assertEqual(a2.gain, 3.0)            # all other columns intact
        self.assertEqual(a2.amp_model, "Dual Rectifier")

    def test_a_name_no_rig_has_is_refused_and_nothing_is_written(self):
        with self.assertRaisesRegex(ValueError, "no rig named 'Nonexistent'"):
            rename_rig(self.src, self.dst, "Nonexistent", "X")
        self.assertFalse(os.path.exists(self.dst))

    def test_a_name_another_rig_has_is_refused(self):
        with self.assertRaisesRegex(ValueError, "a rig named 'B' is already in"):
            rename_rig(self.src, self.dst, "A", "B")
        with self.assertRaisesRegex(ValueError, "already that rig's name"):
            rename_rig(self.src, self.dst, "A", "A")
        self.assertFalse(os.path.exists(self.dst))

    def test_damage_in_an_entry_rename_only_copies_does_not_stop_it(self):
        damaged = os.path.join(self.d, "damaged.rmbackup")
        with zipfile.ZipFile(self.src) as zin, zipfile.ZipFile(damaged, "w") as zout:
            for info in zin.infolist():
                zout.writestr(info, b"<info" if info.filename == "info.xml"
                              else zin.read(info.filename))
            zout.writestr("Prst/Local Library/repositoryR2.db", b"")
        self.assertEqual(rename_rig(damaged, self.dst, "A", "A2").rigs, 1)
        self.assertEqual(_entry(self.dst, "Prst/Local Library/repositoryR2.db"), b"")
        self.assertEqual(_entry(self.dst, "info.xml"), b"<info")

    def test_the_name_check_reads_names_not_rigs(self):
        with mock.patch.object(_tables, "_rigs", wraps=_tables._rigs) as rigs, \
                mock.patch.object(_tables, "_performances", wraps=_tables._performances) as perfs:
            self.assertEqual(main(["rename", self.src, "A", "A2", "-o", self.dst]), 0)
        self.assertEqual((rigs.call_count, perfs.call_count), (0, 0))

    def test_a_library_db_with_only_the_columns_rename_uses_renames(self):
        con = sqlite3.connect(":memory:")
        con.executescript('CREATE TABLE Rigs (id INTEGER PRIMARY KEY, "Name" TEXT);'
                          "CREATE TABLE Rigs_blobs (id INTEGER PRIMARY KEY, data BLOB);"
                          "INSERT INTO Rigs VALUES (1, 'A');"
                          "INSERT INTO Rigs_blobs VALUES (1, NULL);")
        bare = os.path.join(self.d, "bare.rmbackup")
        with zipfile.ZipFile(bare, "w") as zf:
            zf.writestr("Local Library/X/repositoryR2.db", con.serialize())
        self.assertEqual(rename_rig(bare, self.dst, "A", "A2").rigs, 1)

    def test_cli_rename(self):
        rc = main(["rename", self.src, "A", "A2", "-o", self.dst])
        self.assertEqual(rc, 0)
        self.assertIn("A2", {r.name for r in Backup.open(self.dst).rigs})

    def test_cli_refuses_to_overwrite_source(self):
        rc = main(["rename", self.src, "A", "A2", "-o", self.src])
        self.assertNotEqual(rc, 0)
        # source untouched
        self.assertEqual({r.name for r in Backup.open(self.src).rigs}, {"A", "B", "C"})


if __name__ == "__main__":
    unittest.main()


class RenameRepointsPerformancesTest(unittest.TestCase):
    """A performance slot stores a rig *name*. Leaving it behind orphaned the renamed rig:
    `analyze` counted it as a prune candidate and the slot's gain went unknown."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.src = build_rmbackup(
            os.path.join(self.d, "src.rmbackup"),
            rigs=[{"name": "A", "gain": "3.0", "folder": "Guitar/X"},
                  {"name": "B", "gain": "8.0", "folder": "Guitar/X"},
                  {"name": "Unused", "gain": "5.0", "folder": "Guitar/X"}],
            performances=[{"name": "Set1", "slots": [{"rig_name": "A"}, {"rig_name": "B"}]},
                          {"name": "Set2", "slots": [{"rig_name": "A"}]}])
        self.dst = os.path.join(self.d, "out.rmbackup")

    def test_slots_follow_the_rename(self):
        r = rename_rig(self.src, self.dst, "A", "A2")
        self.assertEqual((r.rigs, r.slots), (1, 2))
        after = Backup.open(self.dst)
        named = {p.name: [s.rig_name for s in p.slots] for p in after.performances}
        self.assertEqual(named["Set1"], ["A2", "B"])
        self.assertEqual(named["Set2"], ["A2"])

    def test_the_renamed_rig_is_not_orphaned_afterwards(self):
        rename_rig(self.src, self.dst, "A", "A2")
        after = Backup.open(self.dst)
        self.assertNotIn("A2", [r.name for r in orphaned_rigs(after)])

    def test_untouched_slots_keep_their_rig(self):
        rename_rig(self.src, self.dst, "A", "A2")
        after = Backup.open(self.dst)
        self.assertIn("B", [s.rig_name for p in after.performances for s in p.slots])

    def test_a_rig_no_performance_uses_reports_zero_slots(self):
        r = rename_rig(self.src, self.dst, "Unused", "Unused2")
        self.assertEqual((r.rigs, r.slots), (1, 0))

    def test_source_is_untouched(self):
        before = Path(self.src).read_bytes()
        rename_rig(self.src, self.dst, "A", "A2")
        self.assertEqual(Path(self.src).read_bytes(), before)
