"""A Rig Manager pack — one bare SQLite db — opens as a `Pack`, and wherever a library does."""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _fixture import build_rmbackup, build_snapshot
from _payloads import _track_body, string_msg
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
