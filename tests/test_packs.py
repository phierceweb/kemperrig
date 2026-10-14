"""A Rig Manager pack — one bare SQLite db — opens as a `Pack`, and wherever a library does."""

import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _fixture import build_rmbackup, build_snapshot
from _payloads import _track_body, f08_msg, module_msg, string_msg
from _pack_fixture import build_pack, krig, pack_rig, rig_body

from kemperrig import _sysex
from kemperrig.cli import main
from kemperrig.model import Backup, read_pack

AMP_STRINGS = {0x04: "Rig comment", 0x10: "Plexi Head", 0x15: "Marshall", 0x16: "Unboosted",
               0x18: "JMP", 0x19: "Lead", 0x20: "4x12 Green", 0x26: "SM57"}


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class ReadPackTest(unittest.TestCase):
    def setUp(self):
        self.d = self.enterContext(tempfile.TemporaryDirectory())

    def _pack(self, **kw) -> str:
        kw.setdefault("rigs", [pack_rig("Crunch", strings=AMP_STRINGS, gain=6.24)])
        return build_pack(os.path.join(self.d, "a.rigpack"), **kw)

    def test_the_pack_row_names_the_pack_and_its_vendor(self):
        pack = read_pack(self._pack(name="Some Pack", author="Some Vendor"))
        self.assertEqual((pack.name, pack.author, pack.released, pack.content),
                         ("Some Pack", "Some Vendor", "20200102030405", "rigs"))

    def test_a_payload_is_the_stored_track_wrapped_as_a_standalone_rig(self):
        body = rig_body("Crunch")
        rig = read_pack(self._pack(rigs=[pack_rig("Crunch", body=body)])).rigs[0]
        self.assertEqual(rig.blob, krig(body))

    def test_amp_and_cab_come_from_the_payload_strings(self):
        rig = read_pack(self._pack()).rigs[0]
        self.assertEqual((rig.amp_model, rig.amp_name, rig.source_amp, rig.amp_channel),
                         ("JMP", "Plexi Head", "Marshall", "Lead"))
        self.assertEqual((rig.cabinet_name, rig.mic_type), ("4x12 Green", "SM57"))
        self.assertFalse(rig.is_di)
        self.assertIs(rig.is_boosted, False)

    def test_the_comment_is_the_payload_comment_not_the_pack_category(self):
        rig = read_pack(self._pack()).rigs[0]
        self.assertEqual(rig.comment, "Rig comment")

    def test_the_pack_category_is_the_instrument(self):
        rigs = read_pack(self._pack(rigs=[pack_rig("G"), pack_rig("B", category="Bass")])).rigs
        self.assertEqual([r.instrument for r in rigs], ["Guitar", "Bass"])

    def test_a_pack_without_a_comment_column_still_reads(self):
        path = self._pack(rigs=[pack_rig("A"), pack_rig("B")])
        con = sqlite3.connect(path)
        con.execute("ALTER TABLE rigs DROP COLUMN comment")
        con.commit()
        con.close()
        rigs = read_pack(path).rigs
        self.assertEqual([(r.name, r.instrument) for r in rigs], [("A", None), ("B", None)])

    def test_library_rigs_have_no_instrument(self):
        lib = build_rmbackup(os.path.join(self.d, "l.rmbackup"), rigs=[{"name": "A"}])
        self.assertIsNone(Backup.open(lib).rigs[0].instrument)

    def test_the_pack_view_shows_the_instrument(self):
        code, out, _ = _run(["pack", self._pack(rigs=[pack_rig("Low", category="Bass")])])
        self.assertEqual(code, 0)
        self.assertIn("[Bass]", out)

    def test_name_author_and_date_come_from_the_row(self):
        rig = read_pack(self._pack()).rigs[0]
        self.assertEqual((rig.name, rig.author, rig.date, rig.folder),
                         ("Crunch", "Vendor", "2020-01-02 03:04:05", ""))

    def test_gain_is_the_decoded_amp_gain_to_one_decimal_as_the_column_stores_it(self):
        rig = read_pack(self._pack()).rigs[0]
        self.assertEqual(rig.gain, 6.2)

    def test_a_rig_without_an_amp_block_or_cab_has_no_gain_and_is_di(self):
        rig = read_pack(self._pack(rigs=[pack_rig("Bare", gain=None)])).rigs[0]
        self.assertIsNone(rig.gain)
        self.assertIsNone(rig.amp_model)
        self.assertTrue(rig.is_di)

    def test_profile_columns_a_pack_lacks_read_as_none(self):
        rig = read_pack(self._pack()).rigs[0]
        self.assertEqual((rig.profile_type, rig.cabinet_type, rig.filename), (None, None, None))

    def test_a_row_without_a_payload_has_an_empty_blob(self):
        rig = read_pack(self._pack(rigs=[{**pack_rig("Lost"), "orphan_row": True}])).rigs[0]
        self.assertEqual(rig.blob, b"")
        self.assertIsNone(rig.amp_model)

    def test_a_preset_pack_holds_presets(self):
        body = _track_body([string_msg("Spring", 0x00)])
        p = self._pack(content="Presets", rigs=[pack_rig("Spring", body=body)])
        pack = read_pack(p)
        self.assertEqual((pack.content, pack.rigs), ("presets", []))
        self.assertEqual([(x.name, x.folder, x.blob) for x in pack.presets],
                         [("Spring", "", krig(body))])

    def test_a_preset_pack_preset_gets_its_class_from_the_pages_it_holds(self):
        cases = [("Cab", [string_msg("Cab", 0x20), module_msg(0x0c, [1, 2])], "6"),
                 ("Stomp", [module_msg(0x32, [33, 0, 0, 1])], "3"),
                 ("Old Stomp", [f08_msg(0x32)], "3"),
                 ("Amp", [module_msg(0x0a, [1]), module_msg(0x0b, [1])], "4"),
                 ("Stack", [module_msg(p, [1]) for p in (0x0a, 0x0b, 0x0c)], "8"),
                 ("Late Cab", [module_msg(0x0a, [1]), module_msg(0x0b, [1]),
                               f08_msg(0x0c, start=1)], "8"),
                 ("Mod", [module_msg(0x3a, [1, 0, 0, 1])], None),
                 ("Text", [string_msg("Text", 0x00)], None)]
        rigs = [pack_rig(n, body=_track_body(payloads)) for n, payloads, _ in cases]
        presets = read_pack(self._pack(content="Presets", rigs=rigs)).presets
        self.assertEqual([(x.name, x.preset_class) for x in presets],
                         [(n, c) for n, _, c in cases])
        self.assertTrue(presets[0].is_cab_ir)

    def test_the_pack_view_tags_each_preset_with_its_class(self):
        rigs = [pack_rig("Cab", body=_track_body([module_msg(0x0c, [1, 2])])),
                pack_rig("Stomp", body=_track_body([module_msg(0x32, [33, 0, 0, 1])])),
                pack_rig("Amp", body=_track_body([module_msg(0x0a, [1])])),
                pack_rig("Odd", body=_track_body([module_msg(0x3a, [1])]))]
        code, out, _ = _run(["pack", self._pack(content="Presets", rigs=rigs)])
        self.assertEqual(code, 0)
        lines = {line.split()[0]: line for line in out.splitlines()[1:]}
        self.assertIn("[cab IR]", lines["Cab"])
        self.assertIn("[effect]", lines["Stomp"])
        self.assertIn("[class 4]", lines["Amp"])
        self.assertNotIn("[", lines["Odd"])

    def test_presets_counts_a_pack_effect_whose_type_is_not_decoded(self):
        rigs = [pack_rig("Stomp", body=_track_body([module_msg(0x32, [33, 0, 0, 1])]))]
        code, out, _ = _run(["presets", self._pack(content="Presets", rigs=rigs)])
        self.assertEqual(code, 0)
        self.assertIn("effects 1 · other 0", out)
        self.assertIn("(type not decoded)", out)


class NotAPackTest(unittest.TestCase):
    def setUp(self):
        self.d = self.enterContext(tempfile.TemporaryDirectory())

    def _refused(self, path: str, needle: str) -> None:
        with self.assertRaises(ValueError) as cm:
            read_pack(path)
        self.assertIn(needle, str(cm.exception))
        self.assertIn(os.path.basename(path), str(cm.exception))

    def test_unknown_content_is_refused(self):
        self._refused(build_pack(os.path.join(self.d, "a.rigpack"), content="Performances"),
                      "Performances")

    def test_missing_content_is_refused(self):
        self._refused(build_pack(os.path.join(self.d, "a.rigpack"), content=None), "Content")

    def test_more_than_one_pack_row_is_refused(self):
        self._refused(build_pack(os.path.join(self.d, "a.rigpack"), extra_packs=1),
                      "2 packs")

    def test_a_snapshot_is_not_a_pack(self):
        self._refused(build_snapshot(os.path.join(self.d, "s.db")), "not a Rig Manager")

    def test_a_backup_is_not_a_pack(self):
        self._refused(build_rmbackup(os.path.join(self.d, "b.rmbackup"), rigs=[{"name": "A"}]),
                      "not a Rig Manager")

    def test_a_truncated_pack_file_is_a_one_line_error(self):
        p = build_pack(os.path.join(self.d, "a.rigpack"), rigs=[pack_rig("A")])
        Path(p).write_bytes(Path(p).read_bytes()[:200])
        code, _, err = _run(["rigs", p])
        self.assertEqual(code, 1)
        self.assertIn("a.rigpack", err)
        self.assertEqual(err.count("\n"), 1)

    def test_a_truncated_payload_keeps_the_rig_undecoded(self):
        body = rig_body("Cut")[:-5]
        p = build_pack(os.path.join(self.d, "a.rigpack"), rigs=[pack_rig("Cut", body=body)])
        rig, = Backup.open(p).rigs
        self.assertEqual((rig.name, rig.gain, rig.amp_model), ("Cut", None, None))
        self.assertTrue(rig.blob)


class PackAsLibraryTest(unittest.TestCase):
    def setUp(self):
        self.d = self.enterContext(tempfile.TemporaryDirectory())
        self.pack = build_pack(os.path.join(self.d, "a.rigpack"),
                               rigs=[pack_rig("Crunch", strings=AMP_STRINGS)])

    def test_backup_open_reads_a_pack_by_content(self):
        b = Backup.open(self.pack)
        self.assertEqual([r.name for r in b.rigs], ["Crunch"])
        self.assertEqual((b.performances, b.presets), ([], []))

    def test_read_commands_take_a_pack(self):
        for argv in (["summary", self.pack], ["rigs", self.pack], ["rig", self.pack, "Crunch"],
                     ["doctor", self.pack], ["pages", self.pack, "Crunch"]):
            code, _, err = _run(argv)
            self.assertEqual((code, err), (0, ""), argv)

    def test_a_pack_rig_decodes_like_a_library_rig(self):
        rig = Backup.open(self.pack).rigs[0]
        self.assertEqual(_sysex.rig_name(_sysex.iter_messages(rig.blob)), "Crunch")

    def test_other_sqlite_is_still_refused(self):
        p = build_snapshot(os.path.join(self.d, "x.db"), omit_tables=("Performances",))
        with self.assertRaises(ValueError) as cm:
            Backup.open(p)
        self.assertIn("not a Rig Manager snapshot or pack", str(cm.exception))


class KrigTest(unittest.TestCase):
    def test_wraps_a_track_body_in_the_standalone_header(self):
        body = rig_body("A")
        self.assertEqual(_sysex.krig(body), krig(body))

    def test_the_wrapped_track_parses_to_its_messages(self):
        body = _track_body([string_msg("A", 0x01), string_msg("Me", 0x02)])
        msgs = _sysex.iter_messages(_sysex.krig(body))
        self.assertEqual(_sysex.addressed_strings(msgs),
                         {b"\x00\x00\x01": "A", b"\x00\x00\x02": "Me"})


if __name__ == "__main__":
    unittest.main()
