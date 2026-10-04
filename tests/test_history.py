"""history: a library across dated snapshots, one file open at a time."""

import os
import tempfile
import unittest
from pathlib import Path

from _fixture import build_rmbackup, build_snapshot

from kemperrig.model import Backup
from kemperrig.services.diff import diff_performances, diff_presets, diff_rigs, digest
from kemperrig.services.history import collect, describe, history

A = {"name": "A", "gain": "5.0", "amp_model": "Plexi", "blob": b"KThd-a1"}
B = {"name": "B", "gain": "7.0", "amp_model": "Rectifier", "blob": b"KThd-b1"}
PERF = {"name": "Set", "slots": [{"name": "Verse", "rig_name": "A"}]}


def _snap(d: str, device: str, stamp: str, rigs, **kw) -> str:
    return build_snapshot(os.path.join(d, f"{device} - {stamp}R2.db"), rigs=rigs, **kw)


class TimelineTest(unittest.TestCase):
    def test_each_file_is_counted_against_the_one_before(self):
        with tempfile.TemporaryDirectory() as d:
            _snap(d, "DEV", "2024-01-01 10-00-00", [A])
            _snap(d, "DEV", "2024-01-02 10-00-00", [A, B], performances=[PERF])
            _snap(d, "DEV", "2024-01-03 10-00-00", [{**A, "gain": "6.0"}, B],
                  performances=[PERF])
            h = history([d])
            first, second, third = h.entries
            self.assertIsNone(first.step)
            self.assertEqual(first.totals, {"rigs": 1, "performances": 0, "presets": 0})
            self.assertEqual(second.step.counts["rigs"].added, 1)
            self.assertEqual(second.step.counts["performances"].added, 1)
            self.assertEqual(third.step.counts["rigs"].changed, 1)
            self.assertEqual(third.step.since, second.source)

    def test_counts_are_what_diff_reports_for_the_same_pair(self):
        dup = {"name": "Same", "gain": "3.0", "blob": b"KThd-s1"}
        dup2 = {"name": "Same", "gain": "8.0", "blob": b"KThd-s2"}
        with tempfile.TemporaryDirectory() as d:
            files = [
                _snap(d, "DEV", "2024-01-01 10-00-00", [A, dup, dup2],
                      presets=[{"name": "Room", "preset_class": "3"}]),
                _snap(d, "DEV", "2024-01-02 10-00-00", [{**A, "blob": b"KThd-a2"}, dup2, B],
                      performances=[PERF], presets=[{"name": "Hall", "preset_class": "3"}]),
            ]
            step = history(files).entries[1].step
            a, b = Backup.open(files[0]), Backup.open(files[1])
            for kind, fn in (("rigs", diff_rigs), ("performances", diff_performances),
                             ("presets", diff_presets)):
                want = fn(a, b)
                got = step.counts[kind]
                self.assertEqual((got.added, got.removed, got.changed),
                                 (len(want.added), len(want.removed), len(want.changed)), kind)

    def test_a_device_is_only_compared_with_itself(self):
        with tempfile.TemporaryDirectory() as d:
            one = _snap(d, "DEVA", "2024-01-01 10-00-00", [A])
            two = _snap(d, "DEVB", "2024-01-02 10-00-00", [B])
            three = _snap(d, "DEVA", "2024-01-03 10-00-00", [A, B])
            for n, path in enumerate((one, two, three)):
                os.utime(path, (1_700_000_000 + n, 1_700_000_000 + n))
            h = history([d], order="mtime")
            self.assertEqual([e.source.path for e in h.entries], [one, two, three])
            self.assertIsNone(h.entries[1].step)
            self.assertEqual(h.entries[2].step.since.path, one)
            self.assertEqual(h.entries[2].step.counts["rigs"].added, 1)

    def test_name_order_groups_each_device(self):
        with tempfile.TemporaryDirectory() as d:
            _snap(d, "DEVB", "2024-01-01 10-00-00", [A])
            _snap(d, "DEVA", "2024-01-02 10-00-00", [A])
            _snap(d, "DEVA", "2024-01-01 09-00-00", [A])
            labels = [(e.source.device, e.source.label) for e in history([d]).entries]
            self.assertEqual(labels, [("DEVA", "2024-01-01 09:00:00"),
                                      ("DEVA", "2024-01-02 10:00:00"),
                                      ("DEVB", "2024-01-01 10:00:00")])

    def test_backups_and_snapshots_mix(self):
        with tempfile.TemporaryDirectory() as d:
            _snap(d, "DEV", "2024-01-01 10-00-00", [A])
            build_rmbackup(os.path.join(d, "2024-01-02 10-00-00 - User.rmbackup"), rigs=[A])
            build_rmbackup(os.path.join(d, "2024-01-03 10-00-00 - User.rmbackup"), rigs=[A, B])
            h = history([d])
            self.assertEqual(len(h.entries), 3)
            backups = [e for e in h.entries if e.source.device is None]
            snapshot, = [e for e in h.entries if e.source.device == "DEV"]
            self.assertIsNone(snapshot.step)
            self.assertEqual(backups[1].step.since, backups[0].source)
            self.assertEqual(backups[1].step.counts["rigs"].added, 1)


class UnreadableFileTest(unittest.TestCase):
    def test_zero_byte_and_corrupt_files_are_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            first = _snap(d, "DEV", "2024-01-01 10-00-00", [A])
            zero = os.path.join(d, "DEV - 2024-01-02 10-00-00R2.db")
            Path(zero).write_bytes(b"")
            bad = _snap(d, "DEV", "2024-01-03 10-00-00", [A])
            Path(bad).write_bytes(Path(bad).read_bytes()[:200])
            _snap(d, "DEV", "2024-01-04 10-00-00", [A, B])
            h = history([d])
            self.assertEqual([p for p, _ in h.skipped], [zero, bad])
            self.assertIn("empty file", h.skipped[0][1])
            self.assertNotIn(zero, h.skipped[0][1])
            self.assertEqual(len(h.entries), 2)
            self.assertEqual(h.entries[1].step.since.path, first)


    def test_a_snapshot_with_no_rows_is_marked_empty_and_skipped_as_a_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            first = _snap(d, "DEV", "2024-01-01 10-00-00", [A, B])
            _snap(d, "DEV", "2024-01-02 10-00-00", [])
            _snap(d, "DEV", "2024-01-03 10-00-00", [A, B])
            h = history([d])
            _, empty, third = h.entries
            self.assertTrue(empty.empty)
            self.assertIsNone(empty.step)
            self.assertEqual(third.step.since.path, first)
            self.assertEqual(third.step.counts["rigs"].added, 0)


class SourcesTest(unittest.TestCase):
    def test_a_directory_expands_to_its_snapshots_and_backups(self):
        with tempfile.TemporaryDirectory() as d:
            snap = _snap(d, "DEV", "2024-01-01 10-00-00", [A])
            backup = build_rmbackup(os.path.join(d, "lib.rmbackup"), rigs=[A])
            Path(d, "notes.txt").write_text("x")
            Path(d, "._DEV - 2024-01-01 10-00-00R2.db").write_bytes(b"")
            os.mkdir(os.path.join(d, "Sub R2.db"))
            self.assertEqual(sorted(collect([d])), sorted([snap, backup]))

    def test_a_directory_without_any_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                collect([d])

    def test_a_missing_path_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            collect([os.path.join(tempfile.gettempdir(), "no-such-snapshot R2.db")])

    def test_a_blank_source_is_an_error(self):
        with self.assertRaises(ValueError):
            collect([" "])

    def test_a_file_named_twice_is_read_once(self):
        with tempfile.TemporaryDirectory() as d:
            snap = _snap(d, "DEV", "2024-01-01 10-00-00", [A])
            self.assertEqual(collect([d, snap, d]), [snap])

    def test_an_impossible_date_in_a_name_is_no_date(self):
        self.assertIsNone(describe("DEV - 2024-13-45 99-99-99R2.db").stamp)

    def test_labels(self):
        cases = {
            "DEV - 2024-01-02 03-04-05R2.db": ("2024-01-02 03:04:05", "DEV"),
            "2026-06-03 22-52-19 - User.rmbackup": ("2026-06-03 22:52:19", None),
            "lib.rmbackup": ("lib.rmbackup", None),
        }
        for name, want in cases.items():
            src = describe(os.path.join("somewhere", name))
            self.assertEqual((src.label, src.device), want, name)


class RigHistoryTest(unittest.TestCase):
    def test_versions_first_last_and_where_it_changed(self):
        with tempfile.TemporaryDirectory() as d:
            files = [_snap(d, "DEV", f"2024-01-0{n} 10-00-00", rigs)
                     for n, rigs in ((1, [A]), (2, [B]), (3, [A]), (4, [{**A, "blob": b"KThd-a2"}]),
                                     (5, [{**A, "blob": b"KThd-a2"}]))]
            rig = history([d], rig="A").rig
            self.assertEqual([s.source.path for s in rig.sightings],
                             [files[0], files[2], files[3], files[4]])
            self.assertEqual([s.versions for s in rig.sightings], [[1], [1], [2], [2]])
            self.assertEqual([s.changed for s in rig.sightings], [False, False, True, False])
            v1, v2 = rig.versions
            self.assertEqual(v1.digest, digest(b"KThd-a1"))
            self.assertEqual((v1.first.path, v1.last.path, v1.count), (files[0], files[2], 2))
            self.assertEqual((v2.first.path, v2.last.path, v2.count), (files[3], files[4], 2))

    def test_first_and_last_seen_follow_the_date_times_not_the_listing(self):
        with tempfile.TemporaryDirectory() as d:
            late = _snap(d, "DEVA", "2024-01-05 10-00-00", [{**A, "blob": b"KThd-a2"}])
            mid = _snap(d, "DEVA", "2024-01-03 10-00-00", [A])
            early = _snap(d, "DEVB", "2024-01-01 10-00-00", [A])
            rig = history([d], rig="A").rig
            self.assertEqual([s.source.path for s in rig.sightings], [mid, late, early])
            self.assertEqual((rig.first.path, rig.last.path), (early, late))
            v1, v2 = rig.versions
            self.assertEqual((v1.first.path, v1.last.path), (early, mid))
            self.assertEqual((v2.first.path, v2.last.path), (late, late))

    def test_versions_are_numbered_in_time_order(self):
        with tempfile.TemporaryDirectory() as d:
            newer = _snap(d, "DEVA", "2024-01-05 10-00-00", [{**A, "blob": b"KThd-a2"}])
            older = _snap(d, "DEVB", "2024-01-01 10-00-00", [A])
            rig = history([d], rig="A").rig
            self.assertEqual([s.source.path for s in rig.sightings], [newer, older])
            self.assertEqual([s.versions for s in rig.sightings], [[2], [1]])
            self.assertEqual(rig.versions[0].digest, digest(b"KThd-a1"))

    def test_without_date_times_first_and_last_follow_the_listing(self):
        with tempfile.TemporaryDirectory() as d:
            one = build_rmbackup(os.path.join(d, "b.rmbackup"), rigs=[A])
            two = build_rmbackup(os.path.join(d, "a.rmbackup"), rigs=[A])
            rig = history([d], rig="A").rig
            self.assertEqual((rig.first.path, rig.last.path), (two, one))

    def test_a_rig_in_no_file_has_no_sightings(self):
        with tempfile.TemporaryDirectory() as d:
            _snap(d, "DEV", "2024-01-01 10-00-00", [A])
            rig = history([d], rig="Nowhere").rig
            self.assertEqual((rig.sightings, rig.versions), ([], []))

    def test_without_rig_there_is_no_rig_history(self):
        with tempfile.TemporaryDirectory() as d:
            _snap(d, "DEV", "2024-01-01 10-00-00", [A])
            self.assertIsNone(history([d]).rig)


if __name__ == "__main__":
    unittest.main()
