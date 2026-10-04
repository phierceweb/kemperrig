"""The raw parameter-block dump: `_sysex_effects.blocks`, `pages RIG` and the `pages --all`
census."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from _fixture import build_rmbackup
from _payloads import amp_msg, make_blob, module_msg, string_msg

from kemperrig import _sysex, _sysex_effects
from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services.pages import census

_UNNAMED = 0x77
_OTHER_FRAMING = b"\x00\x20\x33" + bytes([0x00, 0x00, 0x08, 0x00, 0x4b, 0x00]) + bytes(8)


def _messages(*payloads):
    return _sysex.iter_messages(make_blob([list(payloads)]))


def _blob():
    return make_blob([[string_msg("R"), module_msg(0x32, [33, 0, 0, 1]),
                       module_msg(0x04, [5, 6], start=71), module_msg(_UNNAMED, [300]),
                       amp_msg(5.0), _OTHER_FRAMING]])


class BlocksTest(unittest.TestCase):
    def test_keyed_by_page_and_start_with_14_bit_values(self):
        got = _sysex_effects.blocks(_messages(module_msg(0x32, [33, 0, 0, 1]),
                                              module_msg(0x04, [5, 16383], start=71)))
        self.assertEqual(got, {(0x32, 0): [33, 0, 0, 1], (0x04, 71): [5, 16383]})

    def test_strings_and_other_framings_are_not_blocks(self):
        got = _sysex_effects.blocks(_messages(string_msg("R"), _OTHER_FRAMING))
        self.assertEqual(got, {})

    def test_first_occurrence_of_a_key_wins(self):
        got = _sysex_effects.blocks(_messages(module_msg(0x32, [1]), module_msg(0x32, [2])))
        self.assertEqual(got, {(0x32, 0): [1]})

    def test_other_framings_are_listed_raw(self):
        got = _sysex_effects.other_messages(_messages(string_msg("R"), module_msg(0x32, [1]),
                                                      _OTHER_FRAMING))
        self.assertEqual(got, [(bytes([0, 0, 8, 0, 0x4b, 0]), 14)])

    def test_only_pages_the_decoder_reads_are_labelled(self):
        for page, label in ((0x32, "A"), (0x35, "D"), (0x38, "X"), (0x3a, "MOD"),
                            (0x3c, "DLY"), (0x3d, "REV"), (0x4b, "REV (legacy)"),
                            (0x0a, "amp"), (0x09, None), (_UNNAMED, None)):
            with self.subTest(page=hex(page)):
                self.assertEqual(_sysex_effects.page_label(page), label)


def _lib(d, rigs=None):
    return build_rmbackup(os.path.join(d, "P.rmbackup"), rigs=rigs or [
        {"name": "One", "blob": _blob()},
        {"name": "Two", "blob": make_blob([[module_msg(0x32, [9, 0, 0, 0, 7])]])},
        {"name": "Empty"}])


def _run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), mock.patch("sys.stderr", err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


class CensusTest(unittest.TestCase):
    def test_counts_rigs_per_page_and_distinct_lengths(self):
        with tempfile.TemporaryDirectory() as d:
            c = census(Backup.open(_lib(d)).rigs)
        self.assertEqual(c.rigs, 3)
        by_page = {p.page: p for p in c.pages}
        self.assertEqual(by_page[0x32].rigs, 2)
        self.assertEqual(by_page[0x32].param_counts, [4, 5])
        self.assertEqual(by_page[0x04].starts, [71])
        self.assertEqual(by_page[_UNNAMED].rigs, 1)
        self.assertEqual([(o.header, o.rigs, o.lengths) for o in c.other],
                         [(bytes([0, 0, 8, 0, 0x4b, 0]), 1, [14])])


class PagesCliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = _lib(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rig_dump_prints_each_block_raw(self):
        rc, out, _ = _run(["pages", self.path, "One"])
        self.assertEqual(rc, 0)
        self.assertIn("0x32 A", out)
        self.assertRegex(out, r"0x04\s+71\s+2\s+5 6")
        self.assertRegex(out, r"0x77\s+0\s+1\s+300")
        self.assertIn("00 00 08 00 4b 00", out)

    def test_an_unnamed_page_gets_no_guessed_name(self):
        _, out, _ = _run(["pages", self.path, "One"])
        line = next(ln for ln in out.splitlines() if "0x77" in ln)
        self.assertRegex(line, r"^\s*0x77\s+0\s+1\s+300$")

    def test_rig_dump_json(self):
        rc, out, _ = _run(["pages", self.path, "One", "--json"])
        doc = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual(doc["rig"], "One")
        block = next(b for b in doc["blocks"] if b["page"] == 0x32)
        self.assertEqual((block["page_hex"], block["start"], block["label"], block["values"]),
                         ("0x32", 0, "A", [33, 0, 0, 1]))
        self.assertEqual(doc["other"], [{"header": "00 00 08 00 4b 00", "bytes": 14}])

    def test_census_text_and_json(self):
        rc, out, _ = _run(["pages", self.path, "--all"])
        self.assertEqual(rc, 0)
        self.assertRegex(out, r"0x32 A\s+2")
        rc, out, _ = _run(["pages", self.path, "--all", "--json"])
        doc = json.loads(out)
        self.assertEqual(doc["rigs"], 3)
        self.assertIn({"page": 0x77, "page_hex": "0x77", "label": None, "rigs": 1,
                       "starts": [0], "param_counts": [1]}, doc["pages"])

    def test_one_operand_is_the_rig_when_the_library_comes_from_the_env(self):
        with mock.patch.dict(os.environ, {"KEMPERRIG_LIBRARY": self.path}):
            rc, out, _ = _run(["pages", "One"])
            self.assertEqual(rc, 0)
            self.assertIn("0x32", out)
            self.assertEqual(_run(["pages", "--all"])[0], 0)

    def test_missing_and_ambiguous_rigs_are_one_line_errors(self):
        rc, _, err = _run(["pages", self.path, "Nope"])
        self.assertEqual((rc, err), (1, "kemperrig: no rig named 'Nope'\n"))
        dup = _lib(tempfile.mkdtemp(dir=self._tmp.name), rigs=[
            {"name": "Twin", "folder": "Guitar/A"}, {"name": "Twin", "folder": "Guitar/B"}])
        rc, _, err = _run(["pages", dup, "Twin"])
        self.assertEqual(rc, 1)
        self.assertIn("--folder", err)
        self.assertEqual(_run(["pages", dup, "Twin", "--folder", "Guitar/B"])[0], 0)

    def test_needs_a_rig_or_all_but_not_both(self):
        for argv in (["pages", self.path, "One", "--all"], ["pages", "a", "b", "c"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as cm:
                _run(argv)
            self.assertEqual(cm.exception.code, 2)
        with mock.patch.dict(os.environ, {"KEMPERRIG_LIBRARY": self.path}):
            with self.assertRaises(SystemExit) as cm:
                _run(["pages"])
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
