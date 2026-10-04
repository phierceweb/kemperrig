"""`kemperrig pack` — a pack's contents, and where each item stands against a library."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _fixture import build_rmbackup
from _payloads import _track_body, string_msg
from _pack_fixture import build_pack, krig, pack_rig, rig_body

from kemperrig.cli import main
from kemperrig.model import Backup, read_pack
from kemperrig.services.pack import IN_LIBRARY, NAME_TAKEN, NEW, placements

HELD, CLASH, FRESH = rig_body("Held"), rig_body("Clash"), rig_body("Fresh")
OTHER = rig_body("Clash", author="Someone Else")


def _run(argv, env: dict | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env or {}, clear=False):
        if env is None:
            os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


class PlacementTest(unittest.TestCase):
    def setUp(self):
        self.d = self.enterContext(tempfile.TemporaryDirectory())
        self.pack = read_pack(build_pack(os.path.join(self.d, "p.rigpack"), rigs=[
            pack_rig("Held", body=HELD), pack_rig("Clash", body=CLASH),
            pack_rig("Fresh", body=FRESH)]))

    def _library(self, rigs: list[dict], presets: list[dict] | None = None) -> Backup:
        return Backup.open(build_rmbackup(os.path.join(self.d, "lib.rmbackup"), rigs=rigs,
                                          presets=presets))

    def test_same_payload_is_in_the_library_and_says_where(self):
        lib = self._library([{"name": "Renamed", "folder": "Amps", "blob": krig(HELD)}])
        got = placements(self.pack, lib)[0]
        self.assertEqual((got.status, got.where), (IN_LIBRARY, [("Amps", "Renamed")]))

    def test_same_name_different_payload_is_a_name_collision(self):
        lib = self._library([{"name": "Clash", "folder": "Amps", "blob": krig(OTHER)},
                             {"name": "Clash", "folder": "Old",
                              "blob": krig(rig_body("Clash", author="Another"))}])
        got = placements(self.pack, lib)[1]
        self.assertEqual((got.status, got.where), (NAME_TAKEN, [("Amps", "Clash"),
                                                               ("Old", "Clash")]))

    def test_neither_payload_nor_name_is_new(self):
        got = placements(self.pack, self._library([{"name": "Other", "blob": krig(HELD)}]))[2]
        self.assertEqual((got.status, got.where), (NEW, []))

    def test_an_empty_payload_never_matches_an_empty_payload(self):
        pack = read_pack(build_pack(os.path.join(self.d, "e.rigpack"),
                                    rigs=[{**pack_rig("Lost"), "orphan_row": True}]))
        got = placements(pack, self._library([{"name": "Gone", "blob": b""}]))[0]
        self.assertEqual(got.status, NEW)

    def test_a_preset_pack_is_placed_against_the_library_presets(self):
        body = _track_body([string_msg("Spring", 0x00)])
        pack = read_pack(build_pack(os.path.join(self.d, "p.presetpack"), content="Presets",
                                    rigs=[pack_rig("Spring", body=body)]))
        lib = self._library([{"name": "Spring", "blob": krig(body)}],
                            presets=[{"name": "Kept", "blob": krig(body)}])
        got = placements(pack, lib)[0]
        self.assertEqual((got.status, got.where), (IN_LIBRARY, [("Local Library", "Kept")]))


class PackCliTest(unittest.TestCase):
    def setUp(self):
        self.d = self.enterContext(tempfile.TemporaryDirectory())
        self.pack = build_pack(os.path.join(self.d, "p.rigpack"), name="A Pack",
                               author="A Vendor", rigs=[
                                   pack_rig("Held", body=HELD), pack_rig("Clash", body=CLASH),
                                   pack_rig("Fresh", body=FRESH)])
        self.lib = build_rmbackup(os.path.join(self.d, "lib.rmbackup"), rigs=[
            {"name": "Held", "folder": "Amps", "blob": krig(HELD)},
            {"name": "Clash", "folder": "Amps", "blob": krig(OTHER)}])

    def test_lists_the_pack_and_its_rigs(self):
        code, out, err = _run(["pack", self.pack])
        self.assertEqual((code, err), (0, ""))
        self.assertIn("A Pack — A Vendor", out)
        self.assertIn("released 2020-01-02", out)
        for name in ("Held", "Clash", "Fresh"):
            self.assertIn(name, out)
        self.assertNotIn("new", out)

    def test_against_a_library_places_each_rig(self):
        code, out, _ = _run(["pack", self.pack, "--against", self.lib])
        self.assertEqual(code, 0)
        self.assertIn("in library 1 · new 1 · name taken 1", out)
        self.assertIn("in library: Amps/Held", out)
        self.assertIn("name taken: Amps/Clash", out)

    def test_bare_against_uses_kemperrig_library(self):
        code, out, _ = _run(["pack", self.pack, "--against"], {"KEMPERRIG_LIBRARY": self.lib})
        self.assertEqual(code, 0)
        self.assertIn("in library 1", out)

    def test_bare_against_without_a_library_is_a_usage_error(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            _run(["pack", self.pack, "--against"])
        self.assertEqual(cm.exception.code, 2)

    def test_without_against_the_library_is_not_read(self):
        code, out, _ = _run(["pack", self.pack], {"KEMPERRIG_LIBRARY": self.lib})
        self.assertEqual(code, 0)
        self.assertNotIn("in library", out)

    def test_json(self):
        code, out, _ = _run(["pack", self.pack, "--against", self.lib, "--json"])
        doc = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual((doc["pack"]["name"], doc["pack"]["author"], doc["pack"]["content"]),
                         ("A Pack", "A Vendor", "rigs"))
        self.assertEqual(doc["counts"], {"in_library": 1, "new": 1, "name_taken": 1})
        held = doc["rigs"][0]
        self.assertEqual((held["name"], held["status"], held["library"]),
                         ("Held", "in_library", [{"folder": "Amps", "name": "Held"}]))
        self.assertIn("gain", held)
        self.assertEqual(len(held["digest"]), 12)

    def test_json_without_against_has_no_placement(self):
        doc = json.loads(_run(["pack", self.pack, "--json"])[1])
        self.assertIsNone(doc["against"])
        self.assertIsNone(doc["counts"])
        self.assertNotIn("status", doc["rigs"][0])

    def test_a_preset_pack_lists_presets(self):
        body = _track_body([string_msg("Spring", 0x00)])
        p = build_pack(os.path.join(self.d, "p.presetpack"), content="Presets",
                       rigs=[pack_rig("Spring", body=body)])
        code, out, _ = _run(["pack", p])
        self.assertEqual(code, 0)
        self.assertIn("1 presets", out)
        self.assertIn("Spring", out)

    def test_a_file_that_is_not_a_pack_is_a_one_line_error(self):
        code, out, err = _run(["pack", self.lib])
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not a Rig Manager rig or preset pack", err)
        self.assertEqual(err.count("\n"), 1)

    def test_a_missing_pack_is_a_one_line_error(self):
        code, _, err = _run(["pack", os.path.join(self.d, "nope.rigpack")])
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("kemperrig: "))



class BlankPackPathTest(unittest.TestCase):
    def test_a_blank_packfile_is_refused(self):
        code, _, err = _run(["pack", " "])
        self.assertEqual(code, 2)
        self.assertIn("blank", err)


if __name__ == "__main__":
    unittest.main()
