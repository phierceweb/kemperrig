"""Diff between two backups: added, removed, changed fields, and changed payloads."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from _fixture import build_rmbackup

from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services.diff import compare, diff_performances, diff_rigs, fingerprints

RIG_A = {"name": "A", "gain": "5.0", "amp_model": "Dual Rectifier", "cabinet_name": "N/A"}
RIG_B = {"name": "B", "gain": "7.0", "amp_model": "SLO 100", "cabinet_name": "N/A"}


def _backup(d: str, name: str, rigs, **kw) -> str:
    return build_rmbackup(os.path.join(d, name), rigs=rigs, **kw)


class DiffRigsTest(unittest.TestCase):
    def test_identical_backups_are_empty(self):
        with tempfile.TemporaryDirectory() as d:
            a = Backup.open(_backup(d, "a.rmbackup", [RIG_A, RIG_B]))
            b = Backup.open(_backup(d, "b.rmbackup", [RIG_A, RIG_B]))
            self.assertTrue(diff_rigs(a, b).empty)

    def test_added_and_removed(self):
        with tempfile.TemporaryDirectory() as d:
            a = Backup.open(_backup(d, "a.rmbackup", [RIG_A]))
            b = Backup.open(_backup(d, "b.rmbackup", [RIG_B]))
            got = diff_rigs(a, b)
            self.assertEqual([k.rsplit("/", 1)[-1] for k in got.added], ["B"])
            self.assertEqual([k.rsplit("/", 1)[-1] for k in got.removed], ["A"])
            self.assertEqual(got.changed, [])

    def test_changed_field_is_reported_with_before_and_after(self):
        with tempfile.TemporaryDirectory() as d:
            a = Backup.open(_backup(d, "a.rmbackup", [RIG_A]))
            b = Backup.open(_backup(d, "b.rmbackup", [{**RIG_A, "gain": "9.5"}]))
            got = diff_rigs(a, b)
            self.assertEqual(got.added, [])
            self.assertEqual(got.removed, [])
            self.assertEqual(len(got.changed), 1)
            change = got.changed[0].changes[0]
            self.assertEqual((change.field, change.before, change.after), ("gain", 5.0, 9.5))

    def test_a_reprofiled_rig_shows_as_a_payload_change(self):
        """Same name and metadata, different blob — the case a name-only diff would miss."""
        with tempfile.TemporaryDirectory() as d:
            a = Backup.open(_backup(d, "a.rmbackup", [{**RIG_A, "blob": b"KThd-one"}]))
            b = Backup.open(_backup(d, "b.rmbackup", [{**RIG_A, "blob": b"KThd-two"}]))
            got = diff_rigs(a, b)
            self.assertEqual([c.field for c in got.changed[0].changes], ["payload"])

    def test_performances_diff_independently(self):
        with tempfile.TemporaryDirectory() as d:
            a = Backup.open(_backup(d, "a.rmbackup", [RIG_A],
                                    performances=[{"name": "P1"}]))
            b = Backup.open(_backup(d, "b.rmbackup", [RIG_A],
                                    performances=[{"name": "P1"}, {"name": "P2"}]))
            self.assertTrue(diff_rigs(a, b).empty)
            self.assertEqual(diff_performances(a, b).added, ["P2"])


class SlotDiffTest(unittest.TestCase):
    """A slot re-pointed at another rig is a change even when the payload is the same."""

    def test_a_slot_column_change_is_reported_by_slot(self):
        perf = {"name": "Set", "blob": b"KThd-same",
                "slots": [{"rig_name": "A"}, {"rig_name": "B"}]}
        with tempfile.TemporaryDirectory() as d:
            before = Backup.open(_backup(d, "a.rmbackup", [], performances=[perf]))
            after = Backup.open(_backup(d, "b.rmbackup", [], performances=[
                {**perf, "slots": [{"rig_name": "A"}, {"rig_name": "C"}]}]))
            diff = diff_performances(before, after)
        self.assertEqual([(c.field, c.before, c.after) for c in diff.changed[0].changes],
                         [("slot 2", "B", "C")])


class DiffCliTest(unittest.TestCase):
    def test_a_blank_path_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            lib = _backup(d, "a.rmbackup", [{"name": "A"}])
            err = StringIO()
            with redirect_stderr(err):
                self.assertEqual(main(["diff", "", lib]), 2)
            self.assertIn("blank", err.getvalue())

    def test_exit_zero_when_identical_and_one_when_different(self):
        with tempfile.TemporaryDirectory() as d:
            a = _backup(d, "a.rmbackup", [RIG_A])
            b = _backup(d, "b.rmbackup", [RIG_B])
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["diff", a, a]), 0)
                self.assertEqual(main(["diff", a, b]), 1)

    def test_json_output_is_valid_and_flags_identical(self):
        with tempfile.TemporaryDirectory() as d:
            a = _backup(d, "a.rmbackup", [RIG_A])
            buf = StringIO()
            with redirect_stdout(buf):
                main(["diff", a, a, "--json"])
            doc = json.loads(buf.getvalue())
            self.assertTrue(doc["identical"])
            self.assertEqual(doc["rigs"], {"added": [], "removed": [], "changed": []})


class DuplicateKeyDiffTest(unittest.TestCase):
    """Rigs sharing folder/name are real. Keyed on folder/name alone, all but the last would
    vanish, and a deletion would read as a change."""

    F = "Local Library/Shared"
    ONE = {"name": "Same", "folder": F, "gain": "3.0", "amp_model": "AmpOne"}
    TWO = {"name": "Same", "folder": F, "gain": "8.0", "amp_model": "AmpTwo"}

    def _d(self, d: str, before, after):
        return diff_rigs(Backup.open(_backup(d, "a.rmbackup", before)),
                         Backup.open(_backup(d, "b.rmbackup", after)))

    def test_deleting_one_of_two_reports_a_removal_not_a_change(self):
        with tempfile.TemporaryDirectory() as d:
            diff = self._d(d, [self.ONE, self.TWO], [self.ONE])
            self.assertEqual(len(diff.removed), 1, f"expected one removal, got {diff}")
            self.assertEqual(diff.changed, [], "the survivor did not change")

    def test_adding_a_second_rig_of_the_same_name_reports_an_addition(self):
        with tempfile.TemporaryDirectory() as d:
            diff = self._d(d, [self.ONE], [self.ONE, self.TWO])
            self.assertEqual(len(diff.added), 1)
            self.assertEqual(diff.changed, [])

    def test_same_payload_duplicates_pair_on_their_fields_whatever_the_order(self):
        low = {**self.ONE, "blob": b"KThd-same"}
        high = {**self.ONE, "gain": "9.9", "blob": b"KThd-same"}
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self._d(d, [low, high], [high, low]).empty)

    def test_an_unchanged_pair_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(self._d(d, [self.ONE, self.TWO], [self.ONE, self.TWO]).empty)

    def test_editing_one_of_a_pair_is_still_reported_as_a_change(self):
        with tempfile.TemporaryDirectory() as d:
            edited = {**self.TWO, "gain": "9.0"}
            diff = self._d(d, [self.ONE, self.TWO], [self.ONE, edited])
            self.assertEqual((diff.added, diff.removed), ([], []))
            self.assertEqual(len(diff.changed), 1)
            self.assertEqual([c.field for c in diff.changed[0].changes], ["gain"])

    def test_a_single_rig_still_diffs_by_field(self):
        with tempfile.TemporaryDirectory() as d:
            diff = self._d(d, [RIG_A], [{**RIG_A, "gain": "6.0"}])
            self.assertEqual(len(diff.changed), 1)
            self.assertEqual([c.field for c in diff.changed[0].changes], ["gain"])

    def test_a_changed_duplicate_is_numbered_by_its_place_in_the_newer_backup(self):
        with tempfile.TemporaryDirectory() as d:
            one, two = {**self.ONE, "blob": b"one"}, {**self.TWO, "blob": b"two"}
            three = {**self.ONE, "amp_model": "AmpThree", "blob": b"three"}
            diff = self._d(d, [one, two], [three, one, {**two, "gain": "9.0"}])
            self.assertEqual([c.key for c in diff.changed], [f"{self.F}/Same #3"])
            self.assertEqual(diff.added, [f"{self.F}/Same #1"])

    def test_two_identical_rigs_removed_are_two_distinct_lines(self):
        with tempfile.TemporaryDirectory() as d:
            diff = self._d(d, [self.ONE, self.ONE], [RIG_A])
            self.assertEqual(diff.removed, [f"{self.F}/Same #1", f"{self.F}/Same #2"])


class FingerprintTest(unittest.TestCase):
    """`compare` over fingerprints is what diff runs; history keeps only the fingerprints."""

    def test_fingerprints_carry_no_blob_and_compare_like_the_backups(self):
        with tempfile.TemporaryDirectory() as d:
            a = Backup.open(_backup(d, "a.rmbackup", [{**RIG_A, "blob": b"KThd-one"}, RIG_B]))
            b = Backup.open(_backup(d, "b.rmbackup", [{**RIG_A, "blob": b"KThd-two"}]))
            before, after = fingerprints(a, "rigs"), fingerprints(b, "rigs")
            self.assertFalse(any(isinstance(v, bytes) for fps in before.values()
                                 for fp in fps for v in (*fp.values, fp.payload)))
            self.assertEqual(compare("rigs", before, after), diff_rigs(a, b))


if __name__ == "__main__":
    unittest.main()
