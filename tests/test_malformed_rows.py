"""Rows Rig Manager never writes but a damaged db can hold: every command reports, none crashes."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _fixture import build_rmbackup
from _payloads import amp_msg, make_blob, performance_blob, rig_track, string_msg
from _pack_fixture import build_pack, pack_rig

from kemperrig.cli import main
from kemperrig.model import Backup


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _good(name: str) -> dict:
    return {"name": name, "gain": "5.0", "blob": make_blob([rig_track(name) + [amp_msg(5.0)]])}


class NullAndTextRowsTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.lib = build_rmbackup(
            os.path.join(self.d, "lib.rmbackup"),
            rigs=[_good("A"), {"name": None, "filename": "x.krig", "blob": _good("B")["blob"]},
                  {"name": "T", "blob": "not a blob"}],
            performances=[{"name": None, "slots": [{"name": "A", "rig_name": "A"}]}])

    def test_rows_read_as_empty_name_and_empty_payload(self):
        b = Backup.open(self.lib)
        self.assertEqual(sorted(r.name for r in b.rigs), ["", "A", "T"])
        self.assertEqual(next(r for r in b.rigs if r.name == "T").blob, b"")
        self.assertEqual(b.performances[0].name, "")

    def test_every_new_command_runs(self):
        for argv in (["doctor", self.lib], ["pages", self.lib, "--all"],
                     ["extract", self.lib, "--all", "-o", os.path.join(self.d, "out")],
                     ["summary", self.lib, "--write-golden", os.path.join(self.d, "g.json")]):
            with self.subTest(argv[0]):
                code, _, err = _run(argv)
                self.assertEqual(code, 0, err)

    def test_doctor_reports_the_text_payload_as_empty(self):
        code, out, _ = _run(["doctor", self.lib, "--json"])
        broken = json.loads(out)["definite"]["broken_payloads"]
        self.assertIn("T", [b["name"] for b in broken])


class TruncatedPackRigTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        whole = pack_rig("Whole")
        cut = pack_rig("Cut")
        cut["body"] = cut["body"][: len(cut["body"]) // 2]
        self.pack = build_pack(os.path.join(self.d, "p.rigpack"), rigs=[whole, cut])

    def test_the_pack_still_opens_and_keeps_the_broken_rig(self):
        rigs = {r.name: r for r in Backup.open(self.pack).rigs}
        self.assertEqual(set(rigs), {"Whole", "Cut"})
        self.assertEqual(rigs["Whole"].gain, 5.0)
        self.assertIsNone(rigs["Cut"].gain)

    def test_doctor_names_it_and_extract_skips_it(self):
        code, out, _ = _run(["doctor", self.pack, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual([b["name"] for b in json.loads(out)["definite"]["broken_payloads"]],
                         ["Cut"])
        code, out, err = _run(["extract", self.pack, "--all", "-o", os.path.join(self.d, "out")])
        self.assertEqual(code, 0, err)
        self.assertEqual(os.listdir(os.path.join(self.d, "out")), ["Whole.krig"])
        self.assertIn("Cut  (payload does not parse)", out)


class PagesCensusToleratesBrokenRigsTest(unittest.TestCase):
    def test_a_truncated_rig_is_counted_not_fatal(self):
        d = tempfile.mkdtemp()
        whole = make_blob([rig_track("A") + [amp_msg(5.0)]])
        lib = build_rmbackup(os.path.join(d, "lib.rmbackup"),
                             rigs=[{"name": "A", "blob": whole},
                                   {"name": "Cut", "blob": whole[: len(whole) - 7]}])
        code, out, err = _run(["pages", lib, "--all", "--json"])
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual(doc["unparsed"], ["Guitar/Test/Amp/Cut"])


class CutPayloadsBesideWholeOnesTest(unittest.TestCase):
    """A rig and a performance whose payloads end early, beside whole ones."""

    def setUp(self):
        d = tempfile.mkdtemp()
        whole = make_blob([rig_track("A") + [string_msg("a.wav", 0x21), amp_msg(5.0)]])
        two_slots = performance_blob(rig_track("A"), rig_track("A"))
        self.lib = build_rmbackup(
            os.path.join(d, "lib.rmbackup"),
            rigs=[{"name": "A", "gain": "5.0", "blob": whole},
                  {"name": "Cut", "gain": "5.0", "blob": whole[:-7]}],
            performances=[
                {"name": "P", "slots": [{"rig_name": "A"}, {"rig_name": "A"}],
                 "blob": two_slots},
                {"name": "Solo", "slots": [{"rig_name": "A"}],
                 "blob": performance_blob(rig_track("A"))},
                {"name": "Torn", "slots": [{"rig_name": "A"}, {"rig_name": "A"}],
                 "blob": two_slots[:-7]}])

    def test_analyze_decodes_the_whole_payloads_and_skips_the_cut_ones(self):
        code, out, err = _run(["analyze", self.lib, "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["ir_inventory"], [{"name": "a.wav", "count": 1}])

    def test_analyze_names_the_payloads_it_skipped(self):
        code, out, err = _run(["analyze", self.lib, "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["unparsed"],
                         {"rigs": ["Guitar/Test/Amp/Cut"], "performances": ["Torn"]})
        code, out, err = _run(["analyze", self.lib])
        self.assertEqual(code, 0, err)
        self.assertIn("rig Guitar/Test/Amp/Cut", out)
        self.assertIn("performance Torn", out)

    def test_performances_give_a_cut_performance_no_locked_share(self):
        code, out, err = _run(["performances", self.lib, "--json"])
        self.assertEqual(code, 0, err)
        ratios = {p["name"]: p["locked_ratio"] for p in json.loads(out)["performances"]}
        self.assertEqual((ratios["P"], ratios["Torn"]), (1.0, None))
        code, out, err = _run(["performances", self.lib])
        self.assertEqual(code, 0, err)
        rows = {line.split()[0]: line for line in out.splitlines()[1:]}
        self.assertIn("100%", rows["P"])
        self.assertRegex(rows["Torn"], r"locked\s+-\s")

    def test_a_one_slot_performance_has_no_locked_share_in_json_either(self):
        code, out, err = _run(["performances", self.lib, "--json"])
        self.assertEqual(code, 0, err)
        ratios = {p["name"]: p["locked_ratio"] for p in json.loads(out)["performances"]}
        self.assertIsNone(ratios["Solo"])

    def test_rig_and_pages_name_the_rig_whose_payload_is_cut(self):
        for argv in (["rig", self.lib, "Cut"], ["pages", self.lib, "Cut"]):
            with self.subTest(argv[0]):
                code, out, err = _run(argv)
                self.assertEqual((code, out), (1, ""))
                self.assertEqual(len(err.strip().splitlines()), 1)
                self.assertIn("'Guitar/Test/Amp/Cut'", err)
                self.assertIn("truncated blob", err)


def _flipped(name: str) -> bytes:
    """A rig payload whose second event's status byte is not F0, so the parse stops there."""
    blob = make_blob([rig_track(name) + [amp_msg(5.0)]])
    body = blob.index(b"KTrk") + 8
    second = blob.index(b"\xf0", blob.index(b"\xf0", body) + 1)
    return blob[:second] + b"\x90" + blob[second + 1:]


class DamageThatStillFramesTest(unittest.TestCase):
    """A performance missing its last slot track is broken; a rig whose track stops early is
    read as far as it goes and listed, not called broken."""

    def setUp(self):
        d = tempfile.mkdtemp()
        whole = performance_blob(rig_track("A"))
        self.lib = build_rmbackup(
            os.path.join(d, "lib.rmbackup"),
            rigs=[_good("A"), {"name": "Flipped", "gain": "5.0", "blob": _flipped("Flipped")}],
            performances=[{"name": "Short", "slots": [{"rig_name": "A"}],
                           "blob": whole[:whole.rfind(b"KTrk")]}])
        self.unread_only = build_rmbackup(
            os.path.join(d, "unread.rmbackup"),
            rigs=[_good("A"), {"name": "Flipped", "gain": "5.0", "blob": _flipped("Flipped")}])

    def test_analyze_skips_the_short_performance(self):
        code, out, err = _run(["analyze", self.lib, "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["unparsed"]["performances"], ["Short"])

    def test_doctor_calls_the_short_performance_broken(self):
        code, out, err = _run(["doctor", self.lib, "--json"])
        self.assertEqual(code, 0, err)
        broken = json.loads(out)["definite"]["broken_payloads"]
        self.assertEqual([(b["kind"], b["name"]) for b in broken], [("performance", "Short")])
        self.assertIn("holds 5 tracks, not 6", broken[0]["problem"])

    def test_doctor_lists_the_unread_rig_without_failing_strict(self):
        code, out, err = _run(["doctor", self.unread_only, "--json", "--strict"])
        self.assertEqual(code, 0, err)
        unread = json.loads(out)["informational"]["unread_payloads"]
        self.assertEqual([(u["kind"], u["name"], [t["track"] for t in u["tracks"]])
                          for u in unread], [("rig", "Flipped", [0])])
        code, out, err = _run(["doctor", self.unread_only])
        self.assertIn("payloads with bytes nothing reads: 1", out)
        self.assertRegex(out, r"rig Guitar/Test/Amp/Flipped — track 0: \d+ of \d+ bytes")


class BlobInATextColumnTest(unittest.TestCase):
    """A TEXT column keeps a BLOB as a BLOB; it reads as NULL, never as bytes in a record."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.lib = build_rmbackup(
            os.path.join(self.d, "lib.rmbackup"),
            rigs=[_good("A") | {"author": b"\x01", "amp_model": b"\x02", "comment": b"\x03"}],
            performances=[{"name": b"\x04", "filename": "p.kperformance",
                           "slots": [{"name": b"\x05", "rig_name": "A"}]}],
            presets=[{"name": b"\x06", "filename": "c.kcab", "preset_class": "6"}])
        self.pack = build_pack(os.path.join(self.d, "p.rigpack"), author=b"\x07",
                               rigs=[pack_rig("R") | {"author": b"\x08"}])

    def test_the_fields_read_as_null(self):
        b = Backup.open(self.lib)
        self.assertEqual((b.rigs[0].author, b.rigs[0].amp_model, b.rigs[0].comment),
                         (None, None, None))
        self.assertEqual((b.performances[0].name, b.performances[0].slots[0].name), ("", None))
        self.assertEqual(b.presets[0].name, "")

    def test_every_json_document_serializes(self):
        for argv in (["summary", self.lib], ["rigs", self.lib, "--decode"], ["rig", self.lib, "A"],
                     ["presets", self.lib], ["performances", self.lib], ["analyze", self.lib],
                     ["doctor", self.lib], ["pack", self.pack, "--against", self.lib],
                     ["diff", self.lib, self.lib]):
            with self.subTest(command=argv[0]):
                code, out, _ = _run([*argv, "--json"])
                self.assertIn(code, (0, 1))
                json.loads(out)


if __name__ == "__main__":
    unittest.main()
