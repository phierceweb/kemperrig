"""Referential integrity: slots, payloads and cab IRs checked against the library."""

import os
import tempfile
import unittest
from unittest import mock

from _fixture import build_rmbackup
from _payloads import amp_msg, make_blob, performance_blob, rig_track, string_msg

from kemperrig import Backup, _sysex
from kemperrig.services import doctor
from kemperrig.services.edit import rename_rig


def _backup(**kw) -> Backup:
    d = tempfile.mkdtemp()
    return Backup.open(build_rmbackup(os.path.join(d, "t.rmbackup"), **kw))


def _rig(name: str, *, folder: str = "Amps", gain: str = "5.0", amp: float = 5.0,
         cab: str | None = None, payload_name: str | None = None) -> dict:
    blob = make_blob([rig_track(payload_name or name, cab=cab) + [amp_msg(amp)]])
    return {"name": name, "folder": folder, "gain": gain, "blob": blob}


def _perf(name: str, *rigs: str, cabs: dict | None = None) -> dict:
    cabs = cabs or {}
    return {"name": name,
            "slots": [{"name": r, "rig_name": r, "cab_name": cabs.get(r)} for r in rigs],
            "blob": performance_blob(*(rig_track(r, cab=cabs.get(r)) for r in rigs))}


def _cab(name: str, *, folder: str = "Cabs") -> dict:
    return {"name": name, "folder": folder, "preset_class": "6",
            "blob": make_blob([[string_msg(name, 0x20), string_msg(f"{name}.wav", 0x27)]])}


class DanglingSlotTest(unittest.TestCase):
    def test_a_slot_naming_no_library_rig_is_dangling(self):
        b = _backup(rigs=[_rig("Kept")], performances=[_perf("Set", "Kept", "Gone")])
        self.assertEqual(doctor.dangling_slots(b), [doctor.SlotRef("Set", 2, "Gone")])

    def test_slots_naming_library_rigs_are_not(self):
        b = _backup(rigs=[_rig("A"), _rig("B")], performances=[_perf("Set", "A", "B")])
        self.assertEqual(doctor.dangling_slots(b), [])


class AmbiguousSlotTest(unittest.TestCase):
    def test_a_name_held_by_rigs_with_different_payloads_is_ambiguous(self):
        b = _backup(rigs=[_rig("Twin", folder="X", amp=4.0), _rig("Twin", folder="Y", amp=6.0)],
                    performances=[_perf("Set", "Twin")])
        [found] = doctor.ambiguous_slots(b)
        self.assertEqual(found.slot, doctor.SlotRef("Set", 1, "Twin"))
        self.assertEqual(sorted(r.folder for r in found.rigs), ["X", "Y"])

    def test_the_same_gain_does_not_hide_different_payloads(self):
        b = _backup(rigs=[_rig("Twin", folder="X", cab="C1"), _rig("Twin", folder="Y", cab="C2")],
                    performances=[_perf("Set", "Twin")])
        self.assertEqual(len(doctor.ambiguous_slots(b)), 1)

    def test_identical_copies_are_not_ambiguous(self):
        b = _backup(rigs=[_rig("Twin", folder="X"), _rig("Twin", folder="Y")],
                    performances=[_perf("Set", "Twin")])
        self.assertEqual(doctor.ambiguous_slots(b), [])


class BrokenPayloadTest(unittest.TestCase):
    def test_empty_unparseable_and_sysex_free_payloads_are_broken(self):
        whole = make_blob([rig_track("Cut") + [amp_msg(5.0)]])
        b = _backup(
            rigs=[_rig("Fine"), {"name": "Empty", "blob": b""},
                  {"name": "Cut", "folder": "Amps", "blob": whole[:-6]},
                  {"name": "Noise", "blob": make_blob([[]])}],
            performances=[{"name": "Hollow", "slots": [], "blob": b""}],
            presets=[{"name": "Blank", "preset_class": "3", "blob": b""}])
        found = {(p.kind, p.name): p.problem for p in doctor.payload_findings(b)[0]}
        self.assertEqual(set(found), {("rig", "Empty"), ("rig", "Cut"), ("rig", "Noise"),
                                      ("performance", "Hollow"), ("preset", "Blank")})
        self.assertEqual(found[("rig", "Empty")], "empty payload")
        self.assertIn("truncated", found[("rig", "Cut")])
        self.assertEqual(found[("rig", "Noise")], "no Kemper SysEx")

    def test_one_walk_per_payload_finds_both_broken_and_unread(self):
        whole = make_blob([rig_track("Cut") + [amp_msg(5.0)]])
        track = make_blob([rig_track("Odd")])
        track = track[track.index(b"KTrk") + 8:]
        odd = _sysex.krig(track + b"\x00\xff\x2f\x00")   # an end-of-track meta event
        b = _backup(rigs=[_rig("Fine"), {"name": "Cut", "blob": whole[:-6]},
                          {"name": "Odd", "blob": odd}],
                    performances=[_perf("Set", "Fine")], presets=[_cab("Ir")])
        with mock.patch.object(_sysex, "_chunks", wraps=_sysex._chunks) as walks:
            broken, unread = doctor.payload_findings(b)
        self.assertEqual(walks.call_count, 5)
        self.assertEqual([p.name for p in broken], ["Cut"])
        self.assertEqual([(u.name, u.tracks) for u in unread], [("Odd", [(0, 4, len(track) + 4)])])

    def test_a_rig_carries_its_folder(self):
        b = _backup(rigs=[{"name": "Empty", "folder": "Amps/Old", "blob": b""}])
        [found] = doctor.payload_findings(b)[0]
        self.assertEqual(found.folder, "Amps/Old")


class GainMismatchTest(unittest.TestCase):
    def test_a_decoded_gain_off_by_more_than_display_rounding_is_reported(self):
        b = _backup(rigs=[_rig("Off", gain="6.0", amp=5.0), _rig("On", gain="5.0", amp=5.0)])
        [found] = doctor.gain_mismatches(b)
        self.assertEqual(found.rig.name, "Off")
        self.assertAlmostEqual(found.decoded, 5.0, places=2)

    def test_one_decimal_rounding_at_the_boundary_agrees(self):
        b = _backup(rigs=[_rig("Edge", gain="3.0", amp=2.9498)])
        self.assertEqual(doctor.gain_mismatches(b), [])

    def test_just_past_the_rounding_is_reported(self):
        b = _backup(rigs=[_rig("Past", gain="3.0", amp=3.06)])
        self.assertEqual([m.rig.name for m in doctor.gain_mismatches(b)], ["Past"])

    def test_no_amp_block_or_no_stored_gain_is_not_compared(self):
        b = _backup(rigs=[{"name": "Bare", "gain": "5.0", "blob": make_blob([rig_track("Bare")])},
                          {"name": "NoGain", "blob": make_blob([[amp_msg(5.0)]])}])
        self.assertEqual(doctor.gain_mismatches(b), [])


class NameMismatchTest(unittest.TestCase):
    def test_a_rig_whose_payload_carries_another_name(self):
        b = _backup(rigs=[_rig("Listed", payload_name="Played"), _rig("Same")])
        [found] = doctor.name_mismatches(b)
        self.assertEqual((found.rig.name, found.payload, found.slot), ("Listed", "Played", None))

    def test_a_slot_whose_track_carries_another_name(self):
        perf = _perf("Set", "Old")
        perf["slots"][0]["rig_name"] = "New"
        b = _backup(rigs=[_rig("New")], performances=[perf])
        [found] = doctor.name_mismatches(b)
        self.assertEqual((found.slot, found.payload), (doctor.SlotRef("Set", 1, "New"), "Old"))

    def test_surrounding_whitespace_is_not_a_mismatch(self):
        b = _backup(rigs=[_rig("Name ", payload_name="Name")])
        self.assertEqual(doctor.name_mismatches(b), [])

    def test_rename_leaves_no_name_behind(self):
        with tempfile.TemporaryDirectory() as d:
            src = build_rmbackup(os.path.join(d, "a.rmbackup"), rigs=[_rig("Old")],
                                 performances=[_perf("Set", "Old")])
            out = os.path.join(d, "b.rmbackup")
            rename_rig(src, out, "Old", "New")
            self.assertEqual(doctor.name_mismatches(Backup.open(out)), [])


class UnusedCabIrTest(unittest.TestCase):
    def test_a_cab_ir_no_rig_or_slot_loads_is_unused(self):
        b = _backup(rigs=[_rig("R", cab="InRig")],
                    performances=[_perf("Set", "R", cabs={"R": "InSlot"})],
                    presets=[_cab("InRig"), _cab("InSlot"), _cab("Idle"),
                             {"name": "Fx", "preset_class": "3",
                              "blob": make_blob([[string_msg("Fx", 0x20)]])}])
        self.assertEqual([p.name for p in doctor.unused_cab_irs(b)], ["Idle"])

    def test_a_cab_ir_whose_own_name_is_unreadable_is_not_claimed_unused(self):
        b = _backup(rigs=[_rig("R")],
                    presets=[{"name": "Nameless", "preset_class": "6",
                              "blob": make_blob([[string_msg("x.wav", 0x27)]])}])
        self.assertEqual(doctor.unused_cab_irs(b), [])


class CheckupTest(unittest.TestCase):
    def test_definite_findings_make_it_defective(self):
        b = _backup(rigs=[_rig("A")], performances=[_perf("Set", "A", "Gone")])
        found = doctor.checkup(b)
        self.assertTrue(found.defective)
        self.assertEqual(found.dangling, [doctor.SlotRef("Set", 2, "Gone")])
        self.assertEqual((found.rigs, found.performances, found.slots), (1, 1, 2))
        self.assertIsNone(found.device_only)

    def test_informational_findings_alone_do_not(self):
        b = _backup(rigs=[_rig("A", gain="7.0", payload_name="Z")],
                    performances=[_perf("Set", "A")], presets=[_cab("Idle")])
        found = doctor.checkup(b)
        self.assertFalse(found.defective)
        self.assertEqual((len(found.gain_mismatches), len(found.name_mismatches),
                          len(found.unused_cab_irs), found.cab_irs), (1, 1, 1, 1))

    def test_a_broken_rig_is_reported_and_the_other_checks_still_run(self):
        whole = make_blob([rig_track("Cut") + [amp_msg(5.0)]])
        b = _backup(rigs=[{"name": "Cut", "gain": "9.0", "blob": whole[:-6]}, _rig("A")],
                    performances=[_perf("Set", "A", "Gone")])
        found = doctor.checkup(b)
        self.assertEqual([p.name for p in found.broken], ["Cut"])
        self.assertEqual(len(found.dangling), 1)
        self.assertEqual(found.gain_mismatches, [])

    def test_a_dangling_slot_found_in_the_device_backup_is_on_the_device_only(self):
        b = _backup(rigs=[_rig("A")], performances=[_perf("Set", "A", "Pulled", "Gone")])
        device = _backup(rigs=[_rig("Pulled")])
        found = doctor.checkup(b, device=device)
        self.assertEqual(found.device_only, [doctor.SlotRef("Set", 2, "Pulled")])
        self.assertEqual(found.dangling, [doctor.SlotRef("Set", 3, "Gone")])

    def test_only_on_the_device_is_not_a_defect(self):
        b = _backup(rigs=[_rig("A")], performances=[_perf("Set", "A", "Pulled")])
        found = doctor.checkup(b, device=_backup(rigs=[_rig("Pulled")]))
        self.assertFalse(found.defective)


if __name__ == "__main__":
    unittest.main()
