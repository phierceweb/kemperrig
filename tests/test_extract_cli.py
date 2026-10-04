"""`kemperrig extract` — selection, output, and every refusal as a one-line exit 2 that
leaves the source byte-identical."""

import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _fixture import build_rmbackup, build_snapshot
from _payloads import amp_msg, make_blob, rig_track
from _pack_fixture import build_pack, krig, pack_rig, rig_body
from _sample import build_sample

from kemperrig.cli import main


def _blob(name: str) -> bytes:
    return make_blob([rig_track(name) + [amp_msg(5.0)]])


RIGS = [
    {"name": "Clean", "folder": "Amps/Plexi", "gain": "2.0", "amp_model": "Plexi",
     "blob": _blob("Clean")},
    {"name": "Lead", "folder": "Amps/Plexi", "gain": "7.0", "amp_model": "Plexi",
     "blob": _blob("Lead")},
    {"name": "Lead", "folder": "Amps/Recto", "gain": "8.0", "amp_model": "Rectifier",
     "blob": _blob("Lead 2")},
    {"name": "Hollow", "folder": "Amps/Recto", "gain": "4.0", "amp_model": "Rectifier",
     "blob": b""},
]


def _run(argv, env: dict | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env or {}, clear=False):
        if env is None:
            os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


class _Case(unittest.TestCase):
    def setUp(self):
        self.d = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.lib = build_rmbackup(str(self.d / "lib.rmbackup"), rigs=RIGS)
        self.before = Path(self.lib).read_bytes()
        self.out = self.d / "out"

    def tearDown(self):
        self.assertEqual(Path(self.lib).read_bytes(), self.before, "source was modified")

    def _files(self) -> list[str]:
        return sorted(p.name for p in self.out.iterdir()) if self.out.exists() else []


class ExtractTest(_Case):
    def test_by_name_writes_each_matching_rig_verbatim(self):
        code, out, err = _run(["extract", self.lib, "-o", str(self.out), "--name", "Lead"])
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self._files(), ["Lead (2).krig", "Lead.krig"])
        self.assertEqual((self.out / "Lead.krig").read_bytes(), RIGS[1]["blob"])
        self.assertEqual((self.out / "Lead (2).krig").read_bytes(), RIGS[2]["blob"])
        self.assertIn("wrote 2", out)

    def test_name_is_exact_and_repeatable(self):
        code, _, _ = _run(["extract", self.lib, "-o", str(self.out), "--name", "Clean",
                           "--name", "Lea"])
        self.assertEqual(code, 0)
        self.assertEqual(self._files(), ["Clean.krig"])

    def test_the_rigs_filters_select(self):
        code, _, _ = _run(["extract", self.lib, "-o", str(self.out), "--amp", "plexi",
                           "--gain-min", "5"])
        self.assertEqual(code, 0)
        self.assertEqual(self._files(), ["Lead.krig"])

    def test_a_negative_or_zero_filter_is_still_a_selection(self):
        for flags, files in ((["--studio"], []), (["--unboosted"], []),
                             (["--gain-min", "0", "--gain-max", "2"], ["Clean.krig"])):
            with self.subTest(flags=flags):
                code, out, err = _run(["extract", self.lib, "-o", str(self.out), *flags])
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(self._files(), files)

    def test_all_writes_every_rig_and_notes_an_empty_payload(self):
        code, out, _ = _run(["extract", self.lib, "-o", str(self.out), "--all"])
        self.assertEqual(code, 0)
        self.assertEqual(self._files(), ["Clean.krig", "Lead (2).krig", "Lead.krig"])
        self.assertIn("skipped 1", out)
        self.assertIn("Amps/Recto/Hollow", out)

    def test_each_file_digest_equals_its_payload_digest(self):
        _, out, _ = _run(["extract", self.lib, "-o", str(self.out), "--all", "--json"])
        doc = json.loads(out)
        self.assertEqual((doc["count"]["written"], doc["count"]["skipped"]), (3, 1))
        for w in doc["written"]:
            data = (self.out / w["file"]).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest()[:12], w["digest"])
        self.assertEqual(doc["skipped"], [{"folder": "Amps/Recto", "name": "Hollow",
                                           "reason": "empty payload"}])

    def test_no_match_writes_nothing_and_creates_nothing(self):
        code, out, _ = _run(["extract", self.lib, "-o", str(self.out), "--name", "Nope"])
        self.assertEqual(code, 0)
        self.assertIn("no rig matched", out)
        self.assertFalse(self.out.exists())

    def test_source_defaults_to_kemperrig_library(self):
        code, _, _ = _run(["extract", "-o", str(self.out), "--name", "Clean"],
                          {"KEMPERRIG_LIBRARY": self.lib})
        self.assertEqual(code, 0)
        self.assertEqual(self._files(), ["Clean.krig"])

    def test_a_pack_rig_extracts_as_the_stored_rig(self):
        body = rig_body("Packed")
        pack = build_pack(str(self.d / "p.rigpack"), rigs=[pack_rig("Packed", body=body)])
        code, _, _ = _run(["extract", pack, "-o", str(self.out), "--all"])
        self.assertEqual(code, 0)
        self.assertEqual((self.out / "Packed.krig").read_bytes(), krig(body))

    def test_a_snapshot_source(self):
        snap = build_snapshot(str(self.d / "DEV - 2024-01-02 03-04-05R2.db"), rigs=RIGS[:1])
        code, _, _ = _run(["extract", snap, "-o", str(self.out), "--all"])
        self.assertEqual(code, 0)
        self.assertEqual((self.out / "Clean.krig").read_bytes(), RIGS[0]["blob"])

    def test_rigs_takes_the_same_name_selection(self):
        code, out, _ = _run(["rigs", self.lib, "--name", "Lead", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["count"], 2)


class RefusedTest(_Case):
    def _refused(self, argv: list[str], needle: str, env: dict | None = None) -> None:
        code, out, err = _run(argv, env)
        self.assertEqual(code, 2, err)
        self.assertEqual(out, "")
        self.assertTrue(err.startswith("kemperrig: "), err)
        self.assertEqual(err.count("\n"), 1, err)
        self.assertIn(needle, err)

    def test_no_selection_at_all(self):
        self._refused(["extract", self.lib, "-o", str(self.out)], "--all")
        self.assertFalse(self.out.exists())

    def test_a_blank_filter_is_no_selection(self):
        self._refused(["extract", self.lib, "-o", str(self.out), "--folder", " "], "--all")
        self.assertFalse(self.out.exists())

    def test_all_with_a_filter(self):
        self._refused(["extract", self.lib, "-o", str(self.out), "--all", "--amp", "x"],
                      "--all")

    def test_an_existing_file_without_force(self):
        self.out.mkdir()
        (self.out / "Clean.krig").write_bytes(b"old")
        self._refused(["extract", self.lib, "-o", str(self.out), "--name", "Clean"], "--force")
        self.assertEqual((self.out / "Clean.krig").read_bytes(), b"old")

    def test_force_replaces_an_existing_file(self):
        self.out.mkdir()
        (self.out / "Clean.krig").write_bytes(b"old")
        code, _, _ = _run(["extract", self.lib, "-o", str(self.out), "--name", "Clean",
                           "--force"])
        self.assertEqual(code, 0)
        self.assertEqual((self.out / "Clean.krig").read_bytes(), RIGS[0]["blob"])

    def test_an_output_inside_a_live_source(self):
        live = self.d / "RigManager"
        with zipfile.ZipFile(self.lib) as zf:
            zf.extractall(live)
        before = sorted(p.relative_to(live) for p in live.rglob("*"))
        self._refused(["extract", str(live), "-o", str(live / "x"), "--all", "--force"],
                      "inside the source")
        self.assertEqual(sorted(p.relative_to(live) for p in live.rglob("*")), before)

    def test_an_output_inside_a_library_tree(self):
        live = self.d / "RigManager"
        with zipfile.ZipFile(self.lib) as zf:
            zf.extractall(live)
        self._refused(["extract", self.lib, "-o", str(live / "Backups" / "x"), "--all"],
                      "Rig Manager library")
        self.assertFalse((live / "Backups").exists())

    def test_an_output_that_is_the_source_file(self):
        self._refused(["extract", self.lib, "-o", self.lib, "--all", "--force"],
                      "refusing to overwrite the source")

    def test_a_link_to_the_source_among_the_outputs(self):
        self.out.mkdir()
        os.symlink(self.lib, self.out / "Clean.krig")
        self._refused(["extract", self.lib, "-o", str(self.out), "--name", "Clean", "--force"],
                      "the source")
        self.assertTrue((self.out / "Clean.krig").is_symlink())


if __name__ == "__main__":
    unittest.main()


class DecodeSelectionTest(unittest.TestCase):
    """`--effect` / `--ir` select what extract writes; rigs they cannot judge are reported."""

    def setUp(self):
        d = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.lib = str(build_sample(d / "s").backup)
        self.before = Path(self.lib).read_bytes()
        self.out = d / "out"

    def tearDown(self):
        self.assertEqual(Path(self.lib).read_bytes(), self.before, "source was modified")

    def test_an_effect_selects_what_is_written_and_lists_what_it_could_not_judge(self):
        code, out, err = _run(["extract", self.lib, "-o", str(self.out), "--effect", "reverb",
                               "--json"])
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual(sorted(w["name"] for w in doc["written"]), ["Recto Lead", "Recto Rhythm"])
        self.assertEqual(doc["unchecked"], {"unparsed": ["Amps/Recto/Broken Rig"],
                                            "undecoded": ["Amps/Clean/Legacy Room"]})
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         ["Recto Lead.krig", "Recto Rhythm.krig"])

    def test_the_text_view_counts_what_a_filter_could_not_judge(self):
        code, out, err = _run(["extract", self.lib, "-o", str(self.out), "--ir", "v30"])
        self.assertEqual(code, 0, err)
        self.assertIn("1 rig not checked: its payload does not parse", out)
        self.assertNotIn("not ruled out", out)

    def test_without_a_decode_filter_there_is_no_unchecked_list(self):
        code, out, err = _run(["extract", self.lib, "-o", str(self.out), "--all", "--json"])
        self.assertEqual(code, 0, err)
        self.assertNotIn("unchecked", json.loads(out))
