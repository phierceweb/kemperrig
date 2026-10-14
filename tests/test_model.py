"""Kemper model: parsing a synthetic .rmbackup into Backup/Rig/Performance."""

import os
import sqlite3
import tempfile
import time
import unittest

from _fixture import build_rmbackup

from kemperrig import Backup, _tables
from kemperrig.model import preset_folder, rig_folder
from kemperrig.records import Rig


class BackupOpenTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = build_rmbackup(
            os.path.join(self.dir, "test.rmbackup"),
            version="1.6.0", user="Test User",
            rigs=[
                {"name": "PC_MesaDR_D01", "author": "Profile Co", "gain": "3.2",
                 "amp_model": "Dual Rectifier", "cabinet_name": "N/A",
                 "folder": "Guitar/Mesa-Boogie/Dual Rectifier"},
                {"name": "Studio Lead", "author": "Second Author", "gain": "7.5",
                 "amp_model": "SLO 100", "cabinet_name": "Marshall 1960",
                 "folder": "Amps/Soldano/Lead"},
            ],
            performances=[
                {"name": "Test Perf", "tempo": "7680", "slots": [
                    {"name": "Clean", "rig_name": "PC_MesaDR_D22", "amp_name": "Dual Rectifier"},
                    {"name": "Crunch", "rig_name": "PC_MesaDR_D30", "amp_name": "Dual Rectifier"},
                ]},
            ],
        )

    def test_info(self):
        b = Backup.open(self.path)
        self.assertEqual(b.info.version, "1.6.0")
        self.assertEqual(b.info.user, "Test User")

    def test_rigs_parsed(self):
        b = Backup.open(self.path)
        self.assertEqual(len(b.rigs), 2)
        by_name = {r.name: r for r in b.rigs}
        pc = by_name["PC_MesaDR_D01"]
        self.assertEqual(pc.author, "Profile Co")
        self.assertEqual(pc.gain, 3.2)
        self.assertEqual(pc.amp_model, "Dual Rectifier")
        self.assertEqual(pc.folder, "Guitar/Mesa-Boogie/Dual Rectifier")

    def test_performances_parsed(self):
        b = Backup.open(self.path)
        self.assertEqual(len(b.performances), 1)
        perf = b.performances[0]
        self.assertEqual(perf.name, "Test Perf")
        self.assertEqual(len(perf.slots), 2)
        self.assertEqual(perf.slots[0].rig_name, "PC_MesaDR_D22")

    def test_amp_detail_columns_loaded(self):
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "d.rmbackup"),
            rigs=[{"name": "X", "amp_model": "Dual Rectifier", "amp_comment": "Maxon 808",
                   "amp_channel": "Red (Modern)", "source_amp": "Mesa Boogie",
                   "amp_pickup": "Humbucker"}],
        )
        r = Backup.open(path).rigs[0]
        self.assertEqual(r.amp_comment, "Maxon 808")
        self.assertEqual(r.amp_channel, "Red (Modern)")
        self.assertEqual(r.source_amp, "Mesa Boogie")
        self.assertEqual(r.amp_pickup, "Humbucker")

    def test_is_boosted_heuristic(self):
        def rig(comment):
            p = build_rmbackup(os.path.join(tempfile.mkdtemp(), "b.rmbackup"),
                               rigs=[{"name": "X", "amp_comment": comment}])
            return Backup.open(p).rigs[0]
        self.assertTrue(rig("Maxon 808").is_boosted)
        self.assertTrue(rig("KEELEY TS808").is_boosted)
        self.assertFalse(rig("Unboosted").is_boosted)
        self.assertFalse(rig("Non Boosted").is_boosted)
        self.assertIsNone(rig("JJ 6L6").is_boosted)   # tube spec, no drive info
        self.assertIsNone(rig("").is_boosted)

    def test_short_boost_cues_match_only_as_words(self):
        for comment in ("Boss OD-3", "Fulltone OD", "Pro Co Rat", "Rat, gain 3"):
            with self.subTest(comment):
                self.assertTrue(Rig(name="r", folder="", amp_comment=comment).is_boosted)
        for comment in ("Good tubes, stock", "Mod EL34 power section", "Strat neck",
                        "Wood cab", "Odd mic placement"):
            with self.subTest(comment):
                self.assertIsNone(Rig(name="r", folder="", amp_comment=comment).is_boosted)
        for comment in ("Clean, no OD", "No OD, stock tubes"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)

    def test_a_negation_covers_the_cues_after_it_in_its_clause(self):
        for comment in ("not boosted", "Non-boosted", "nonboosted", "without a boost",
                        "w/o boost", "no overdrive", "No 808", "no TS9 in front",
                        "no boost or OD", "No OD/boost"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)
        for comment in ("Klon in front, no OD channel", "TS9 boost; no OD on the amp",
                        "No boost but a TS9 in front", "808, not a Klon"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)
        for comment in ("not a Marshall", "No. 2 input"):
            with self.subTest(comment):
                self.assertIsNone(Rig(name="r", folder="", amp_comment=comment).is_boosted)

    def test_a_cue_switched_off_right_after_it_is_not_a_boost(self):
        for comment in ("TS9 off", "Klon bypassed", "boost disengaged", "Ch1 Boost Off Tone Off",
                        "Lead channel, boost off", "Booster off"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)
        for comment in ("TS9 on", "TS9 off, OD on", "TS9 off into a Klon", "Overdrive attack off",
                        "Boost off axis", "Boost off-axis SM57"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)

    def test_a_pedal_named_by_two_cues_is_switched_off_after_the_last(self):
        for comment in ("Maxon 808 off", "Keeley Klon off", "Keeley TS808 off",
                        "TS9 overdrive off", "Klon boost off", "Maxon 808 bypassed", "TS9 Boost Off"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)
        for comment in ("Maxon 808", "Keeley TS808 into the amp", "Keeley Klon, attack off"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)

    def test_an_off_word_after_punctuation_or_verbs_switches_the_cue_off(self):
        for comment in ("Boost: off", "TS9 (off)", "TS9 - off", "TS9 = off", "Boost: none",
                        "Overdrive: n/a", "Boost: no", "TS9 is off", "TS9 turned off",
                        "TS9 was switched off", "TS9 is set to off", "TS9 disabled",
                        "TS9 not engaged", "TS9 isn't on", "Boost: TS9 off", "Boost (TS9) off",
                        "Boost (Maxon 808) off", "OD = Klon off", "Boost: no!",
                        "Boost not needed"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)
        for comment in ("Boost: on", "Boost: TS9", "Boost: 10", "TS9 is the boost",
                        "TS9 set at noon", "Amp's own boost (no pedal)", "TS9 no mods",
                        "TS9 - no gain", "Boost level off", "TS9 not on the input"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)

    def test_only_a_colon_or_a_bracket_gloss_hands_the_state_back(self):
        for comment in ("Klon (TS9 off)", "TS9 - Klon off", "Klon - TS9 bypassed",
                        "Klon (TS9) on"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)

    def test_any_space_but_a_line_break_sits_between_words(self):
        for comment in ("TS9\xa0off", "Maxon\xa0808 off", "TS9 \u2009off", "TS9\toff"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)
        self.assertIs(Rig(name="r", folder="", amp_comment="TS9\noff").is_boosted, True)

    def test_a_value_ends_where_the_next_label_begins(self):
        for comment in ("Drive: TS9 / Boost: none", "OD: Klon / Boost: off",
                        "Drive: TS9 Boost: none", "Boost: TS9 Klon: off"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)
        for comment in ("Maxon 808: off", "TS9 & Klon: off", "Boost: Maxon 808 off"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)

    def test_a_long_gap_between_cues_reads_in_linear_time(self):
        start = time.perf_counter()
        for comment in ("TS9" + "x" * 100_000 + " y Klon", "TS9" + "-" * 100_000 + ". Klon"):
            self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)
        self.assertLess(time.perf_counter() - start, 2.0)

    def test_pedals_named_together_are_switched_off_together(self):
        for comment in ("TS9 and Klon off", "TS9 & Klon off", "TS9/Klon off",
                        "TS9 and Klon are off", "TS9 Klon off", "Klon-style boost off"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, False)
        for comment in ("TS9 and Klon", "TS9 into Klon off", "TS9 on and Klon off"):
            with self.subTest(comment):
                self.assertIs(Rig(name="r", folder="", amp_comment=comment).is_boosted, True)

    def test_a_toggle_leaves_the_state_open_unless_another_cue_is_on(self):
        for comment in ("TS9 on/off", "TS9 off/on", "Boost: on or off", "TS9 (on/off)",
                        "TS9 on/off, no Klon", "TS9 off, Klon on/off"):
            with self.subTest(comment):
                self.assertIsNone(Rig(name="r", folder="", amp_comment=comment).is_boosted)
        self.assertIs(Rig(name="r", folder="", amp_comment="TS9 on/off, Klon on").is_boosted, True)

    def test_rig_blob_available(self):
        blob = b"KThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0KTrk\x00\x00\x00\x00"
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "b.rmbackup"),
            rigs=[{"name": "WithBlob", "amp_model": "Dual Rectifier", "blob": blob}],
        )
        b = Backup.open(path)
        self.assertEqual(b.rigs[0].blob, blob)


class EntryFolderTest(unittest.TestCase):
    def test_a_db_where_the_layout_expects_one_names_its_folder(self):
        self.assertEqual(rig_folder("Local Library/Guitar/Mesa/repositoryR2.db"), "Guitar/Mesa")
        self.assertEqual(rig_folder("Local Library/repositoryR2.db"), "")
        self.assertEqual(preset_folder("Prst/Local Library/repositoryR2.db"), "Local Library")
        for entry in ("Prf/Local Library/repositoryR2.db", "Prst/Local Library/repositoryR2.db",
                      "RigManager/Local Library/X/repositoryR2.db", "Local Library/X/other.db"):
            with self.subTest(entry):
                self.assertIsNone(rig_folder(entry))
        self.assertIsNone(preset_folder("Prf/Local Library/repositoryR2.db"))


class RawMetadataTest(unittest.TestCase):
    def _open(self, **kw):
        path = build_rmbackup(os.path.join(tempfile.mkdtemp(), "m.rmbackup"), **kw)
        return Backup.open(path).rigs[0]

    def test_profile_and_cabinet_columns_read_raw(self):
        r = self._open(rigs=[{"name": "X", "profile_type": "20", "profile_revision": "1",
                              "cabinet_type": "2", "cabinet_configuration": "4x12"}])
        self.assertEqual((r.profile_type, r.profile_revision, r.cabinet_type,
                          r.cabinet_configuration), ("20", "1", "2", "4x12"))

    def test_cabinet_type_does_not_decide_is_di(self):
        r = self._open(rigs=[{"name": "X", "cabinet_type": "0", "cabinet_name": "Real Cab"}])
        self.assertFalse(r.is_di)

    def test_older_db_without_the_columns_reads_none(self):
        missing = ("Profile Type", "Profile Revision", "Cabinet Type", "Cabinet Configuration")
        r = self._open(rigs=[{"name": "X"}], omit_rig_columns=missing)
        self.assertEqual(r.name, "X")
        self.assertIsNone(r.profile_type)
        self.assertIsNone(r.profile_revision)
        self.assertIsNone(r.cabinet_type)
        self.assertIsNone(r.cabinet_configuration)


class DefensiveDbTest(unittest.TestCase):
    def test_every_database_opens_in_defensive_mode(self):
        src = sqlite3.connect(":memory:")
        src.execute("CREATE TABLE t (x)")
        con = _tables._load_db(src.serialize(), "t.db")
        self.assertTrue(con.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE))


if __name__ == "__main__":
    unittest.main()
