"""One rig's decode as data: `rig --json`, the `decode` object, and `digest` on rig entries."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _sample import build_sample

from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services import decode
from kemperrig.services.diff import digest

_EFFECT_KEYS = {"slot", "type_value", "type_name", "category", "on", "decoded"}


def _cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class RigDecodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.lib = str(build_sample(Path(cls._tmp.name) / "s").backup)
        cls.backup = Backup.open(cls.lib)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _rig_json(self, name: str) -> dict:
        rc, out, err = _cli("rig", self.lib, name, "--json")
        self.assertEqual(rc, 0, err)
        return json.loads(out)

    def test_every_rig_entry_carries_its_payload_digest(self):
        rc, out, _ = _cli("rigs", self.lib, "--json")
        by_path = {r.path: r for r in self.backup.rigs}
        for entry in json.loads(out)["rigs"]:
            rig = by_path[f"{entry['folder']}/{entry['name']}"]
            self.assertEqual(entry["digest"], digest(rig.blob))

    def test_rig_json_is_the_rigs_entry_plus_its_decode(self):
        rc, out, _ = _cli("rigs", self.lib, "--json", "--name", "Recto Rhythm")
        (entry,) = json.loads(out)["rigs"]
        doc = self._rig_json("Recto Rhythm")
        self.assertEqual(set(doc), set(entry) | {"decode"})
        self.assertEqual({k: doc[k] for k in entry}, entry)

    def test_the_decode_object(self):
        d = self._rig_json("Recto Rhythm")["decode"]
        self.assertEqual(set(d), {"amp_gain", "cab_ir", "effects", "strings"})
        self.assertAlmostEqual(d["amp_gain"], 7.0, places=2)
        self.assertEqual(d["cab_ir"], "Cab 4x12 V30.wav")
        self.assertEqual([e["slot"] for e in d["effects"]], ["A", "DLY", "REV"])
        self.assertTrue(all(set(e) == _EFFECT_KEYS and e["decoded"] for e in d["effects"]))
        self.assertIn("Recto Rhythm", d["strings"])

    def test_an_undecoded_slot_in_the_decode(self):
        d = self._rig_json("Legacy Room")["decode"]
        self.assertEqual(d["effects"], [{"slot": "REV", "type_value": None, "type_name": None,
                                         "category": None, "on": None, "decoded": False}])

    def test_a_payload_that_does_not_parse_is_a_one_line_error(self):
        rc, out, err = _cli("rig", self.lib, "Broken Rig", "--json")
        self.assertEqual(rc, 1)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("Broken Rig", err)

    def test_try_rig_detail_is_none_only_for_a_payload_that_does_not_parse(self):
        rigs = {r.name: r for r in self.backup.rigs}
        self.assertIsNone(decode.try_rig_detail(rigs["Broken Rig"]))
        self.assertEqual(decode.try_rig_detail(rigs["Recto Rhythm"]).cab_ir, "Cab 4x12 V30.wav")


class RigsDecodeCliTest(unittest.TestCase):
    """`rigs --decode`, and `--effect` / `--ir` with their unchecked lists, on the sample."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.lib = str(build_sample(Path(cls._tmp.name) / "s").backup)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _json(self, *flags: str) -> dict:
        rc, out, err = _cli("rigs", self.lib, "--json", *flags)
        self.assertEqual(rc, 0, err)
        return json.loads(out)

    def test_decode_adds_a_decode_object_to_every_rig(self):
        doc = self._json("--decode")
        by_name = {r["name"]: r for r in doc["rigs"]}
        self.assertEqual(by_name["Recto Rhythm"]["decode"]["cab_ir"], "Cab 4x12 V30.wav")
        self.assertIsNone(by_name["Broken Rig"]["decode"])
        self.assertEqual(doc["unparsed"], ["Amps/Recto/Broken Rig"])

    def test_an_effect_filter_lists_what_it_could_not_judge(self):
        doc = self._json("--effect", "reverb")
        self.assertEqual(sorted(r["name"] for r in doc["rigs"]), ["Recto Lead", "Recto Rhythm"])
        self.assertEqual(doc["unchecked"], {"unparsed": ["Amps/Recto/Broken Rig"],
                                            "undecoded": ["Amps/Clean/Legacy Room"]})

    def test_an_ir_filter_has_an_empty_undecoded_list(self):
        doc = self._json("--ir", "v30")
        self.assertEqual([r["name"] for r in doc["rigs"]], ["Recto Rhythm"])
        self.assertEqual(doc["unchecked"]["undecoded"], [])

    def test_without_decode_flags_the_document_is_unchanged(self):
        doc = self._json()
        self.assertNotIn("unchecked", doc)
        self.assertNotIn("unparsed", doc)
        self.assertNotIn("decode", doc["rigs"][0])

    def test_decode_filters_combine_with_metadata_filters(self):
        doc = self._json("--effect", "reverb", "--gain-min", "8")
        self.assertEqual([r["name"] for r in doc["rigs"]], ["Recto Lead"])

    def test_the_text_view_counts_what_a_filter_could_not_judge(self):
        rc, out, _ = _cli("rigs", self.lib, "--effect", "reverb")
        tail = out.strip().splitlines()[-2:]
        self.assertIn("1 rig not checked: its payload does not parse", tail)
        self.assertIn("1 rig not ruled out: it has an undecoded effect slot", tail)

    def test_the_text_view_shows_each_rigs_decode(self):
        rc, out, _ = _cli("rigs", self.lib, "--decode")
        self.assertIn("effects: A=Green Scream on · DLY=Quad Delay on · REV=Natural Reverb on"
                      "  ·  cab IR: Cab 4x12 V30.wav", out)
        self.assertIn("effects: REV=?", out)
        self.assertIn("payload does not parse", out)


if __name__ == "__main__":
    unittest.main()
