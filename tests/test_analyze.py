"""Relational intelligence: orphans, amp coverage, duplicates, drive split, IR inventory."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from _fixture import build_rmbackup
from _payloads import amp_msg, make_blob, module_msg, performance_blob, rig_track, string_msg

from kemperrig import Backup, _sysex
from kemperrig.cli import main
from kemperrig.services import analyze
from kemperrig.services.analyze import orphaned_rigs


def _backup(**kw):
    return Backup.open(build_rmbackup(os.path.join(tempfile.mkdtemp(), "t.rmbackup"), **kw))


class OrphanTest(unittest.TestCase):
    def _backup_with_rack(self):
        return _backup(
            rigs=[
                {"name": "Used", "folder": "Guitar/A/B"},
                {"name": "OnRack", "folder": "Rack"},
                {"name": "Dead", "folder": "Guitar/A/B"},
            ],
            performances=[{"name": "P", "slots": [{"name": "s", "rig_name": "Used"}]}],
        )

    def test_orphans_exclude_rigs_a_performance_uses(self):
        orphans = {r.name for r in analyze.orphaned_rigs(self._backup_with_rack())}
        self.assertEqual(orphans, {"OnRack", "Dead"})

    def test_a_named_rack_folder_is_also_excluded(self):
        orphans = {r.name for r in
                   analyze.orphaned_rigs(self._backup_with_rack(), rack_folder="Rack")}
        self.assertEqual(orphans, {"Dead"})


class CoverageTest(unittest.TestCase):
    def test_amp_coverage_flags_missing_bands(self):
        b = _backup(rigs=[
            {"name": "c", "amp_model": "Recto", "gain": "2.0"},
            {"name": "h", "amp_model": "Recto", "gain": "7.5"},
        ])
        cov = analyze.amp_coverage(b)["Recto"]
        self.assertEqual(cov.count, 2)
        self.assertTrue(cov.has_clean)
        self.assertTrue(cov.has_high)
        self.assertFalse(cov.has_mid)   # nothing in the 3.0–6.5 band


class DuplicateTest(unittest.TestCase):
    def test_near_dupes_grouped(self):
        b = _backup(rigs=[
            {"name": "d1", "author": "RZ", "amp_model": "Recto", "gain": "5.0"},
            {"name": "d2", "author": "RZ", "amp_model": "Recto", "gain": "5.0"},
            {"name": "u", "author": "RZ", "amp_model": "Recto", "gain": "8.0"},
        ])
        groups = analyze.similar_groups(b)
        self.assertEqual(len(groups), 1)
        self.assertEqual({r.name for r in groups[0]}, {"d1", "d2"})


class DriveTest(unittest.TestCase):
    def test_drive_breakdown(self):
        b = _backup(rigs=[
            {"name": "a", "amp_comment": "Maxon 808"},
            {"name": "b", "amp_comment": "Unboosted"},
            {"name": "c", "amp_comment": "JJ 6L6"},
        ])
        bd = analyze.drive_breakdown(b)
        self.assertEqual(bd["boosted"], 1)
        self.assertEqual(bd["unboosted"], 1)
        self.assertEqual(bd["unknown"], 1)


class IrInventoryTest(unittest.TestCase):
    def test_ir_inventory_counts_wavs(self):
        b = _backup(rigs=[
            {"name": "r1", "blob": make_blob([[string_msg("Mesa OS 4x12.wav", 1)]])},
            {"name": "r2", "blob": make_blob([[string_msg("Mesa OS 4x12.wav", 1)]])},
            {"name": "r3", "blob": make_blob([[string_msg("Marshall 1960.wav", 1)]])},
        ])
        inv = dict(analyze.ir_inventory(analyze.payloads(b)))
        self.assertEqual(inv["Mesa OS 4x12.wav"], 2)
        self.assertEqual(inv["Marshall 1960.wav"], 1)


class RackFolderTest(unittest.TestCase):
    """The on-device folder is a setting, not a constant baked to one library's name."""

    def _backup(self, folder: str) -> Backup:
        with tempfile.TemporaryDirectory() as d:
            p = build_rmbackup(
                os.path.join(d, "L.rmbackup"),
                rigs=[{"name": "OnRack", "folder": folder, "gain": "5.0"}],
                performances=[{"name": "P", "slots": [{"rig_name": "Other"}]}])
            return Backup.open(p)

    def test_no_folder_is_exempt_by_default(self):
        """The folder name is one person's convention, so there is nothing to guess."""
        for folder in ("Rack", "Device", "Off The Head"):
            self.assertEqual([r.name for r in orphaned_rigs(self._backup(folder))], ["OnRack"])

    def test_the_named_folder_is_exempt(self):
        for folder in ("Rack", "Device", "Off The Head"):
            self.assertEqual(orphaned_rigs(self._backup(folder), rack_folder=folder), [])

    def test_rack_folder_resolves_from_the_environment(self):
        with mock.patch.dict(os.environ, {"KEMPERRIG_RACK_FOLDER": "Device"}):
            with tempfile.TemporaryDirectory() as d:
                p = build_rmbackup(
                    os.path.join(d, "L.rmbackup"),
                    rigs=[{"name": "OnRack", "folder": "Device", "gain": "5.0"}],
                    performances=[{"name": "P", "slots": [{"rig_name": "Other"}]}])
                self.assertEqual(main(["analyze", "--strict", p]), 0)


class SimilarGroupTest(unittest.TestCase):
    """Rigs whose metadata did not parse are unknown, not similar to one another."""

    def test_rigs_with_no_amp_or_gain_are_not_grouped(self):
        b = _backup(rigs=[{"name": f"R{i}"} for i in range(4)])
        self.assertEqual(analyze.similar_groups(b), [])

    def test_genuine_matches_are_still_grouped(self):
        b = _backup(rigs=[
            {"name": "a", "author": "X", "amp_model": "Recto", "gain": "5.0"},
            {"name": "b", "author": "X", "amp_model": "Recto", "gain": "5.0"},
        ])
        groups = analyze.similar_groups(b)
        self.assertEqual([sorted(r.name for r in g) for g in groups], [["a", "b"]])

    def test_a_missing_gain_alone_is_not_enough_to_pair_them(self):
        b = _backup(rigs=[{"name": "a", "amp_model": "Recto"},
                          {"name": "b", "amp_model": "Recto"}])
        self.assertEqual(analyze.similar_groups(b), [])


class FingerprintTest(unittest.TestCase):
    """The metadata key cannot tell two different profiles apart. The blob can."""

    def _rig(self, name, gain, blob):
        return {"name": name, "author": "X", "amp_model": "Recto", "gain": gain, "blob": blob}

    def test_identical_amp_blocks_are_found(self):
        same = make_blob([[amp_msg(6.0), string_msg("a")]])
        other = make_blob([[amp_msg(6.0), string_msg("b")]])   # same amp, different strings
        b = _backup(rigs=[self._rig("one", "6.0", same), self._rig("two", "6.0", other)])
        groups = analyze.identical_amp_groups(analyze.payloads(b))
        self.assertEqual([sorted(r.name for r in g) for g in groups], [["one", "two"]])

    def test_a_different_amp_setting_is_not_a_match(self):
        b = _backup(rigs=[self._rig("one", "6.0", make_blob([[amp_msg(6.0)]])),
                          self._rig("two", "7.0", make_blob([[amp_msg(7.0)]]))])
        self.assertEqual(analyze.identical_amp_groups(analyze.payloads(b)), [])

    def test_later_amp_block_generations_are_fingerprinted_too(self):
        same = make_blob([[amp_msg(6.0, length=50), string_msg("a")]])
        other = make_blob([[amp_msg(6.0, length=50), string_msg("b")]])
        b = _backup(rigs=[self._rig("one", "6.0", same), self._rig("two", "6.0", other)])
        groups = analyze.identical_amp_groups(analyze.payloads(b))
        self.assertEqual([sorted(r.name for r in g) for g in groups], [["one", "two"]])

    def test_rigs_with_no_amp_block_are_not_grouped(self):
        b = _backup(rigs=[self._rig("one", "6.0", b""), self._rig("two", "6.0", b"")])
        self.assertEqual(analyze.identical_amp_groups(analyze.payloads(b)), [])

    def test_identical_profiles_needs_the_whole_blob_to_match(self):
        same = make_blob([[amp_msg(6.0), string_msg("a")]])
        b = _backup(rigs=[self._rig("one", "6.0", same), self._rig("two", "6.0", same),
                          self._rig("three", "6.0", make_blob([[amp_msg(6.0), string_msg("z")]]))])
        groups = analyze.identical_profiles(b)
        self.assertEqual([sorted(r.name for r in g) for g in groups], [["one", "two"]])

    def test_the_metadata_report_is_named_for_what_it_measures(self):
        """It groups on author+amp+gain+boost, which is similarity, not identity."""
        self.assertTrue(hasattr(analyze, "similar_groups"))
        self.assertFalse(hasattr(analyze, "duplicate_groups"),
                         "`duplicate_groups` would claim identity it cannot establish")


_STOMPS = """<lists>
  <list id="Types"><entry value="33">Green Scream</entry></list>
  <list id="CategoryList"><entry value="33">Distortion</entry></list>
</lists>"""


def _loaded(name: str) -> bytes:
    """A rig loading a cab IR and a Green Scream in slot A."""
    return make_blob([rig_track(name) + [string_msg("Room.wav", 0x21),
                                         module_msg(0x32, [33, 0, 0, 1]), amp_msg(5.0)]])


class AnalysisCliTest(unittest.TestCase):
    """The text view and `--strict`, both read from one `Analysis`."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.stomps = os.path.join(self.d, "Stomps.xml")
        with open(self.stomps, "w", encoding="iso-8859-1") as fh:
            fh.write(_STOMPS)

    def _run(self, *argv) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"KEMPERRIG_STOMPS_XML": self.stomps}), \
                redirect_stdout(out):
            code = main(["analyze", *argv])
        return code, out.getvalue()

    def _library(self, *extra: dict) -> str:
        rigs = [{"name": n, "amp_model": "Plexi", "gain": "5.0", "blob": _loaded(n)}
                for n in ("A", "B", "C")] + list(extra)
        return build_rmbackup(
            os.path.join(self.d, f"lib{len(extra)}.rmbackup"), rigs=rigs,
            performances=[{"name": "P", "slots": [{"rig_name": r["name"]} for r in rigs]}])

    def test_the_view_shows_gaps_categories_and_irs(self):
        code, out = self._run(self._library())
        self.assertEqual(code, 0)
        self.assertIn("amp coverage gaps (1 amps", out)
        self.assertRegex(out, r"Plexi\s+n=  3  gain 5.0-5.0  missing: clean, high")
        self.assertIn("effect slots by category: Distortion 3", out)
        self.assertIn("cab IRs in use: 1 distinct", out)
        self.assertRegex(out, r"\s+3  Room.wav")

    def test_strict_fails_on_a_payload_that_does_not_parse(self):
        self.assertEqual(self._run(self._library(), "--strict")[0], 0)
        cut = {"name": "Cut", "gain": "5.0", "blob": make_blob([rig_track("Cut")])[:-3]}
        code, out = self._run(self._library(cut), "--strict")
        self.assertEqual(code, 1)
        self.assertIn("rig Guitar/Test/Amp/Cut", out)


class ParseOnceTest(unittest.TestCase):
    def test_analysis_parses_each_payload_once(self):
        b = _backup(rigs=[{"name": n, "blob": make_blob([rig_track(n)])} for n in ("A", "B")],
                    performances=[{"name": "P", "slots": [{"rig_name": "A"}],
                                   "blob": performance_blob(rig_track("A"))}])
        with mock.patch.object(_sysex, "_chunks", wraps=_sysex._chunks) as walks:
            analyze.analysis(b)
        self.assertEqual(walks.call_count, 3)


if __name__ == "__main__":
    unittest.main()
