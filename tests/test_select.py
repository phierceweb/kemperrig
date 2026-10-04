"""Selecting rigs by what their payloads decode to: `--effect` and `--ir`, on top of the
metadata filters, with every rig the decode cannot judge reported rather than dropped."""

import os
import tempfile
import unittest
from pathlib import Path

from _fixture import build_rmbackup
from _payloads import amp_msg, f08_msg, make_blob, module_msg, rig_track, string_msg

from kemperrig import _enums
from kemperrig.model import Backup
from kemperrig.services.select import select_rigs

_XML = """<?xml version="1.0" encoding="iso-8859-1"?>
<logic><domain id="d"><group id="Effects"><group id="StompEffects">
  <list id="Types"><entry value="0">- empty -</entry><entry value="33">Green Scream</entry>
    <entry value="164">Quad Delay</entry><entry value="178">Natural Reverb</entry></list>
  <list id="CategoryList"><entry value="0">-</entry><entry value="33">Distortion</entry>
    <entry value="164">Delay</entry><entry value="178">Reverb</entry></list>
</group></group></domain></logic>
"""


def _blob(name, *extra, broken=False):
    blob = make_blob([rig_track(name) + [amp_msg(5.0), *extra]])
    return blob[:-4] if broken else blob


_RIGS = [
    ("Scream", "Recto", "6.0", (module_msg(0x32, [33, 0, 0, 1]),)),
    ("Echo", "Plexi", "5.0", (module_msg(0x3c, [164, 0, 0, 1]),)),
    ("Echo Off", "Recto", "7.0", (module_msg(0x3c, [164, 0, 0, 0]),)),
    ("Hall", "Recto", "4.0", (module_msg(0x3d, [178, 0, 0, 1]), string_msg("Cab 4x12 V30.wav", 5))),
    ("Old Room", "Recto", "6.5", (f08_msg(0x4b), string_msg("Greenback 2x12.wav", 5))),
    ("Plain", "Plexi", "3.0", ()),
]


class SelectRigsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        d = cls._tmp.name
        rigs = [{"name": n, "amp_model": amp, "gain": g, "blob": _blob(n, *extra)}
                for n, amp, g, extra in _RIGS]
        rigs.append({"name": "Broken", "amp_model": "Recto", "gain": "6.0",
                     "blob": _blob("Broken", module_msg(0x3c, [164, 0, 0, 1]), broken=True)})
        cls.rigs = Backup.open(build_rmbackup(os.path.join(d, "l.rmbackup"), rigs=rigs)).rigs
        xml = Path(d) / "Stomps.xml"
        xml.write_text(_XML, encoding="iso-8859-1")
        cls.xml = str(xml)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        _enums.install(self.xml)

    def tearDown(self):
        _enums.install(None)

    def _names(self, rigs):
        return sorted(r.name for r in rigs)

    def test_an_effect_matches_by_category(self):
        self.assertEqual(self._names(select_rigs(self.rigs, effect="distortion").rigs), ["Scream"])

    def test_an_effect_matches_by_type_name(self):
        self.assertEqual(self._names(select_rigs(self.rigs, effect="scream").rigs), ["Scream"])

    def test_the_effect_match_ignores_case_and_on_off(self):
        self.assertEqual(self._names(select_rigs(self.rigs, effect="DELAY").rigs),
                         ["Echo", "Echo Off"])

    def test_an_ir_matches_a_substring_of_the_cab_ir(self):
        self.assertEqual(self._names(select_rigs(self.rigs, ir="v30").rigs), ["Hall"])

    def test_decode_filters_combine_with_metadata_filters(self):
        picked = select_rigs(self.rigs, effect="delay", amp_model="recto", gain_min=6.5)
        self.assertEqual(self._names(picked.rigs), ["Echo Off"])

    def test_both_decode_filters_must_match(self):
        self.assertEqual(select_rigs(self.rigs, effect="reverb", ir="greenback").rigs, [])
        self.assertEqual(self._names(select_rigs(self.rigs, effect="reverb", ir="v30").rigs),
                         ["Hall"])

    def test_a_payload_that_does_not_parse_is_unparsed_not_selected(self):
        for kw in ({"effect": "delay"}, {"ir": "wav"}):
            with self.subTest(**kw):
                picked = select_rigs(self.rigs, **kw)
                self.assertNotIn("Broken", self._names(picked.rigs))
                self.assertEqual(self._names(picked.unparsed), ["Broken"])

    def test_an_undecoded_slot_cannot_rule_an_effect_out(self):
        picked = select_rigs(self.rigs, effect="reverb")
        self.assertEqual(self._names(picked.rigs), ["Hall"])
        self.assertEqual(self._names(picked.undecoded), ["Old Room"])

    def test_an_ir_filter_alone_leaves_undecoded_empty(self):
        picked = select_rigs(self.rigs, ir="greenback")
        self.assertEqual(self._names(picked.rigs), ["Old Room"])
        self.assertEqual(picked.undecoded, [])

    def test_an_undecoded_rig_failing_the_ir_filter_is_not_listed(self):
        self.assertEqual(select_rigs(self.rigs, effect="reverb", ir="v30").undecoded, [])

    def test_without_a_decode_filter_nothing_is_parsed(self):
        picked = select_rigs(self.rigs, amp_model="recto")
        self.assertFalse(picked.decoded)
        self.assertIn("Broken", self._names(picked.rigs))
        self.assertEqual((picked.unparsed, picked.undecoded), ([], []))

    def test_with_a_decode_filter_the_selection_says_it_decoded(self):
        self.assertTrue(select_rigs(self.rigs, ir="x").decoded)

    def test_details_line_up_with_the_selected_rigs(self):
        for kw in ({}, {"effect": "delay"}):
            with self.subTest(**kw):
                picked = select_rigs(self.rigs, decode=True, **kw)
                self.assertEqual(len(picked.details), len(picked.rigs))
                for rig, detail in zip(picked.rigs, picked.details, strict=True):
                    self.assertIs(detail is None, rig.name == "Broken")
                    self.assertTrue(detail is None or detail.rig is rig)

    def test_no_details_unless_asked(self):
        self.assertIsNone(select_rigs(self.rigs, effect="delay").details)


if __name__ == "__main__":
    unittest.main()
