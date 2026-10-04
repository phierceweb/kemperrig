"""The library census: the `summary` numbers plus the decode anchors, and its JSON document."""

import json
import os
import tempfile
import unittest

from _fixture import build_rmbackup, build_snapshot
from _payloads import (
    amp_msg,
    f08_msg,
    make_blob,
    module_msg,
    performance_blob,
    rig_track,
    string_msg,
)

from kemperrig import _json
from kemperrig.model import Backup
from kemperrig.services import census
from kemperrig.services.report import build_report


def _rig_blob(name: str, gain: float, *, cab: str | None = None, extra: tuple = (),
              func: int = 0x02, length: int = 40) -> bytes:
    return make_blob([rig_track(name, cab=cab)
                      + [string_msg("Maker", 0x02), amp_msg(gain, func=func, length=length),
                         *extra]])


STOMP = module_msg(0x32, [17, 0, 0, 1])
REVERB = module_msg(0x3d, [5, 0, 0, 1])

RIGS = [
    {"name": "Bravo", "folder": "Amps/B", "gain": "5.0", "amp_model": "Rectifier",
     "author": "Maker", "blob": _rig_blob("Bravo", 5.0, extra=(STOMP,))},
    {"name": "Alpha", "folder": "Amps/Z", "gain": "3.0", "amp_model": "Plexi",
     "author": "Maker", "cabinet_name": "Plexi 4x12", "blob": _rig_blob("Alpha", 3.0, cab="Cab Z")},
    {"name": "Alpha", "folder": "Amps/A", "gain": "4.0", "amp_model": "Plexi",
     "author": "Other", "blob": _rig_blob("Alpha", 4.0, extra=(STOMP, REVERB))},
    {"name": "Odd", "folder": "Packs/Odd", "gain": "6.0", "amp_model": "SLO",
     "profile_type": "20",
     "blob": _rig_blob("Odd", 6.0, func=0x08, length=94, extra=(f08_msg(0x4b),))},
    {"name": "Aardvark", "folder": "Amps/A", "gain": "2.0", "blob": b""},
    {"name": "Abacus", "folder": "Amps/B", "gain": "7.0", "blob": _rig_blob("Abacus", 7.0)[:-5]},
]

_SLOTS = [("Clean", "Alpha", 3.0), ("Crunch", "Bravo", 5.0), ("Lead", "Odd", 6.0),
          ("Solo", "Bravo", 5.0), ("Ghost", "Gone", 8.0)]
PERFORMANCES = [
    {"name": "Zulu", "slots": [{"name": "Clean", "rig_name": "Bravo"}],
     "blob": performance_blob(rig_track("Bravo"))},
    {"name": "Midway",
     "slots": [{"name": s, "rig_name": r} for s, r, _ in _SLOTS],
     "blob": performance_blob(*[rig_track(r, cab="Cab Z")
                                + [STOMP, amp_msg(g), string_msg("Z Cab.wav", 0x21)]
                                for _, r, g in _SLOTS])},
]

PRESETS = [
    {"name": "Cab Z", "preset_class": "6", "blob": make_blob([[string_msg("Cab Z", 0x20)]])},
    {"name": "Spare Cab", "preset_class": "6",
     "blob": make_blob([[string_msg("Spare Cab", 0x20)]])},
    {"name": "Green", "preset_class": "3", "preset_type": "Green Scream",
     "blob": make_blob([[STOMP]])},
]


def _library(d: str, *, reverse: bool = False, name: str = "lib.rmbackup") -> str:
    order = (lambda xs: list(reversed(xs))) if reverse else list
    return build_rmbackup(os.path.join(d, name), rigs=order(RIGS),
                          performances=order(PERFORMANCES), presets=order(PRESETS))


class _Case(unittest.TestCase):
    def setUp(self):
        self.d = self.enterContext(tempfile.TemporaryDirectory())
        self.backup = Backup.open(_library(self.d))
        self.census = census.take(self.backup)
        self.doc = _json.census_doc(self.census)


class CensusTotalsTest(_Case):
    def test_totals_are_the_summary_numbers(self):
        summary = _json.summary_doc(build_report(self.backup), info_user="Test User")
        totals = self.doc["totals"]
        for key in ("rigs", "di", "studio", "performances"):
            self.assertEqual(totals[key], summary[key], key)
        self.assertEqual(totals["amp_models"], len(summary["amp_models"]))
        self.assertEqual(totals["authors"], len(summary["authors"]))
        self.assertEqual(self.doc["user"], "Test User")

    def test_totals_add_slots_presets_and_cab_irs(self):
        self.assertEqual(self.doc["totals"], {
            "rigs": 6, "di": 5, "studio": 1, "performances": 2, "slots": 6,
            "presets": 3, "cab_irs": 2, "amp_models": 3, "authors": 3})

    def test_gain_block_keeps_summary_stats_and_counts_the_decode(self):
        gain = self.doc["gain"]
        self.assertEqual((gain["min"], gain["max"]), (2.0, 7.0))
        self.assertEqual(gain["mean"], round((5 + 3 + 4 + 6 + 2 + 7) / 6, 4))
        self.assertEqual(gain["bands"], {"2": 1, "3": 1, "4": 1, "5": 1, "6": 1, "7": 1})
        # an empty and a truncated payload decode nothing
        self.assertEqual((gain["decoded"], gain["undecoded"]), (4, 2))

    def test_profile_types_count_rigs_and_decodes_and_file_the_rarer_ones(self):
        self.assertEqual(self.doc["profile_types"], {
            "1": {"rigs": 5, "gain_decoded": 3},
            "20": {"rigs": 1, "gain_decoded": 1, "folders": ["Packs/Odd"]}})

    def test_effects_count_rigs_per_module_slot(self):
        self.assertEqual(self.doc["effects"], {"A": 2, "REV": 1})

    def test_undecoded_slots_are_counted_on_their_own(self):
        self.assertEqual(self.doc["effects_undecoded"], {"REV": 1})

    def test_an_undecoded_slot_is_not_counted_as_loaded(self):
        odd = next(r for r in self.backup.rigs if r.name == "Odd")
        self.assertIn(b"\x00\x00\x08\x00\x4b", odd.blob)
        self.assertEqual(self.doc["effects"]["REV"], 1)

    def test_doctor_counts_come_from_the_checkup(self):
        self.assertEqual(self.doc["doctor"], {
            "dangling_slots": 1, "ambiguous_slots": 1, "broken_payloads": 2,
            "unread_payloads": 0, "gain_mismatches": 0, "name_mismatches": 0,
            "unused_cab_irs": 1})


class CensusSamplesTest(_Case):
    def test_sample_rig_is_first_by_name_then_folder_with_a_parsing_payload(self):
        self.assertEqual(self.doc["rig"], {
            "name": "Alpha", "folder": "Amps/A", "gain": 4.0, "amp_gain": 4.0002,
            "first_strings": ["Alpha", "Maker"], "effects": {"A": 17, "REV": 5}})

    def test_sample_performance_is_first_by_name(self):
        self.assertEqual(self.doc["performance"], {
            "name": "Midway", "slots": 5, "tracks": 6,
            "effects_locked": [3, 5], "effects_locked_ratio": 0.6,
            "cab_ir": "Z Cab.wav", "gain_ladder": [None, 5.0, 6.0, 5.0, None]})

    def test_nothing_depends_on_storage_order(self):
        other = census.take(Backup.open(_library(self.d, reverse=True, name="rev.rmbackup")))
        self.assertEqual(_json.census_text(other), _json.census_text(self.census))


class CensusDocumentTest(_Case):
    def test_text_is_sorted_indented_json_with_a_trailing_newline(self):
        text = _json.census_text(self.census)
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(json.loads(text), self.doc)
        self.assertEqual(text, json.dumps(self.doc, indent=2, sort_keys=True,
                                          ensure_ascii=False) + "\n")

    def test_it_says_what_it_is_and_which_test_reads_it(self):
        self.assertEqual(self.doc["census"], _json.CENSUS_FORMAT)
        self.assertEqual(_json.CENSUS_FORMAT, 1)
        self.assertIn("tests/test_golden.py", self.doc["_comment"])

    def test_floats_are_rounded(self):
        self.assertEqual(self.doc["rig"]["amp_gain"], round(self.census.rig.amp_gain, 4))


class EmptyCensusTest(unittest.TestCase):
    def test_a_library_with_no_rows_has_no_samples(self):
        with tempfile.TemporaryDirectory() as d:
            doc = _json.census_doc(census.take(Backup.open(build_snapshot(
                os.path.join(d, "snap R2.db")))))
        self.assertIsNone(doc["rig"])
        self.assertIsNone(doc["performance"])
        self.assertEqual(doc["profile_types"], {})
        self.assertEqual(doc["totals"]["rigs"], 0)
        self.assertEqual((doc["gain"]["min"], doc["gain"]["mean"]), (None, None))

    def test_rigs_without_a_profile_type_column_count_as_none(self):
        with tempfile.TemporaryDirectory() as d:
            doc = _json.census_doc(census.take(Backup.open(build_snapshot(
                os.path.join(d, "snap R2.db"), rigs=RIGS[:2]))))
        self.assertEqual(doc["profile_types"], {"none": {"rigs": 2, "gain_decoded": 2}})


if __name__ == "__main__":
    unittest.main()
