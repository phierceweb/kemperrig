"""`services.extract` — file names, the plan, and the guards that keep the writer off its
source and out of any Rig Manager library."""

import os
import random
import tempfile
import unicodedata
import unittest
import zipfile
from pathlib import Path

from _fixture import sample_library
from _payloads import make_blob, rig_track

from kemperrig.model import Rig, library_root
from kemperrig.services.extract import file_name, plan, refusal, write


def _rig(name: str, folder: str = "Amps", blob: bytes | None = None) -> Rig:
    return Rig(name=name, folder=folder,
               blob=make_blob([rig_track(name)]) if blob is None else blob)


class FileNameTest(unittest.TestCase):
    def test_a_plain_name_keeps_its_spelling(self):
        self.assertEqual(file_name("Crunch 5.0"), "Crunch 5.0.krig")

    def test_separators_and_reserved_characters_become_underscores(self):
        self.assertEqual(file_name('a/b:c\\d*e?f"g<h>i|j'), "a_b_c_d_e_f_g_h_i_j.krig")

    def test_nul_and_control_characters_become_underscores(self):
        self.assertEqual(file_name("a\x00b\x1fc\x7fd\ne"), "a_b_c_d_e.krig")

    def test_leading_dots_and_spaces_are_dropped(self):
        self.assertEqual(file_name(" ..hidden"), "hidden.krig")

    def test_trailing_spaces_and_dots_are_dropped(self):
        self.assertEqual(file_name("name. . "), "name.krig")

    def test_windows_device_names_are_prefixed(self):
        for name in ("CON", "nul", "Com1", "LPT9", "aux.old"):
            with self.subTest(name=name):
                self.assertEqual(file_name(name), f"_{name}.krig")

    def test_a_name_with_nothing_left_is_rig(self):
        for name in ("", "...", "  ", "."):
            with self.subTest(name=name):
                self.assertEqual(file_name(name), "rig.krig")

    def test_a_long_name_is_cut_on_a_character_boundary(self):
        got = file_name("é" * 300)
        self.assertLessEqual(len(got.encode()), 210)
        self.assertTrue(got.endswith(".krig"))
        got.encode().decode("utf-8")

    def test_the_name_is_normalised_to_composed_form(self):
        self.assertEqual(file_name(unicodedata.normalize("NFD", "Café")),
                         unicodedata.normalize("NFC", "Café") + ".krig")


class PlanTest(unittest.TestCase):
    def test_colliding_names_are_numbered_by_folder_order(self):
        got = plan([_rig("A", "Zeta"), _rig("A", "Alpha")])
        self.assertEqual([(p.rig.folder, p.file) for p in got],
                         [("Alpha", "A.krig"), ("Zeta", "A (2).krig")])

    def test_collisions_ignore_case_and_unicode_form(self):
        nfd = unicodedata.normalize("NFD", "Café")
        got = plan([_rig("café", "A"), _rig(nfd, "B"), _rig("CAFÉ", "C")])
        self.assertEqual(sorted(p.file.casefold() for p in got),
                         sorted(f.casefold() for f in ("café.krig", "Café (2).krig",
                                                       "CAFÉ (3).krig")))
        self.assertEqual(len({unicodedata.normalize("NFC", p.file).casefold() for p in got}), 3)

    def test_a_numbered_name_never_takes_a_name_already_used(self):
        got = plan([_rig("A"), _rig("A", "B"), _rig("A (2)", "C")])
        self.assertEqual(sorted(p.file for p in got), ["A (2) (2).krig", "A (2).krig", "A.krig"])

    def test_the_plan_does_not_depend_on_input_order(self):
        rigs = [_rig(n, f) for n in ("A", "a", "B", "A/B", "A_B") for f in ("X", "Y")]
        first = [(p.rig.folder, p.rig.name, p.file) for p in plan(rigs)]
        for seed in range(5):
            shuffled = rigs[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual([(p.rig.folder, p.rig.name, p.file) for p in plan(shuffled)], first)

    def test_an_empty_payload_is_skipped_with_a_reason(self):
        got = plan([Rig(name="Empty", folder="Amps", blob=b""), _rig("Full")])
        self.assertEqual([(p.rig.name, p.file, p.skipped) for p in got],
                         [("Empty", None, "empty payload"), ("Full", "Full.krig", None)])

    def test_a_payload_that_does_not_parse_is_skipped_with_a_reason(self):
        got = plan([_rig("Cut", blob=_rig("Cut").blob[:-3]), _rig("Full")])
        self.assertEqual([(p.rig.name, p.file, p.skipped) for p in got],
                         [("Cut", None, "payload does not parse"), ("Full", "Full.krig", None)])


class _Dirs(unittest.TestCase):
    def setUp(self):
        self.d = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def _live(self) -> Path:
        """An unzipped library tree, as Rig Manager keeps it."""
        live = self.d / "RigManager"
        with zipfile.ZipFile(sample_library(str(self.d))) as zf:
            zf.extractall(live)
        return live


class RefusalTest(_Dirs):
    def _refused(self, out, source, needle: str, planned=None, force=True) -> None:
        why = refusal(out, source=str(source), planned=planned or plan([_rig("A")]),
                      force=force)
        self.assertIsNotNone(why)
        self.assertIn(needle, why)

    def test_a_fresh_folder_outside_the_source_is_fine(self):
        live = self._live()
        self.assertIsNone(refusal(self.d / "out", source=str(live), planned=plan([_rig("A")]),
                                  force=False))

    def test_the_source_folder_itself(self):
        live = self._live()
        self._refused(live, live, "inside the source")

    def test_a_folder_inside_the_source(self):
        live = self._live()
        self._refused(live / "Local Library" / "new", live, "inside the source")

    def test_a_folder_inside_the_source_through_a_symlink(self):
        live = self._live()
        os.symlink(live, self.d / "via")
        self._refused(self.d / "via" / "out", live, "inside the source")

    def test_a_folder_inside_the_source_through_dotdot(self):
        live = self._live()
        self._refused(self.d / "elsewhere" / ".." / "RigManager" / "x", live, "inside the source")

    def test_a_case_variant_of_the_source(self):
        live = self._live()
        variant = self.d / "rigmanager" / "out"
        if not (self.d / "rigmanager").exists():
            self.skipTest("case-sensitive filesystem — no alias to refuse")
        self._refused(variant, live, "inside the source")

    def test_a_folder_inside_any_library_tree(self):
        live = self._live()
        source = sample_library(str(self.d), "Other.rmbackup")
        self._refused(live / "Backups" / "out", source, "Rig Manager library")

    def test_every_library_marker_counts(self):
        for marker in ("Local Library", "Prst", "Prf"):
            with self.subTest(marker=marker):
                root = self.d / f"tree-{marker}"
                (root / marker).mkdir(parents=True)
                self.assertEqual(library_root(root / "a" / "b"), root)
        loose = self.d / "loose"
        loose.mkdir()
        (loose / "repositoryR2.db").write_bytes(b"")
        self.assertEqual(library_root(loose / "out"), loose)
        self.assertIsNone(library_root(self.d / "plain" / "out"))

    def test_an_empty_output(self):
        self._refused("", sample_library(str(self.d)), "no folder")

    def test_an_output_through_a_symlink_loop(self):
        os.symlink(self.d / "b", self.d / "a")
        os.symlink(self.d / "a", self.d / "b")
        self._refused(self.d / "a" / "out", sample_library(str(self.d)), "cannot resolve")

    def test_an_output_that_is_a_file(self):
        f = self.d / "taken"
        f.write_bytes(b"x")
        self._refused(f, sample_library(str(self.d)), "not a folder")

    def test_existing_files_without_force(self):
        out = self.d / "out"
        out.mkdir()
        (out / "A.krig").write_bytes(b"old")
        self._refused(out, sample_library(str(self.d)), "--force", force=False)
        self.assertIsNone(refusal(out, source=sample_library(str(self.d), "S.rmbackup"),
                                  planned=plan([_rig("A")]), force=True))

    def test_a_target_that_is_a_folder_even_with_force(self):
        out = self.d / "out"
        (out / "A.krig").mkdir(parents=True)
        self._refused(out, sample_library(str(self.d)), "not a file")

    def test_a_target_that_is_the_source_file_even_with_force(self):
        source = Path(sample_library(str(self.d), "A.krig"))
        self._refused(self.d, source, "the source")

    def test_a_target_linked_to_the_source_file_even_with_force(self):
        source = Path(sample_library(str(self.d)))
        out = self.d / "out"
        out.mkdir()
        os.symlink(source, out / "A.krig")
        self._refused(out, source, "the source")


class WriteTest(_Dirs):
    def test_writes_each_payload_verbatim_and_creates_the_folder(self):
        rigs = [_rig("A"), _rig("B", blob=make_blob([rig_track("B") + [bytes(range(256))]]))]
        out = self.d / "new" / "deeper"
        written = write(plan(rigs), out, source=sample_library(str(self.d)), force=False)
        self.assertEqual(written, 2)
        self.assertEqual((out / "A.krig").read_bytes(), rigs[0].blob)
        self.assertEqual((out / "B.krig").read_bytes(), rigs[1].blob)

    def test_an_existing_file_is_refused_and_nothing_is_written(self):
        out = self.d / "out"
        out.mkdir()
        (out / "B.krig").write_bytes(b"keep")
        with self.assertRaises(ValueError):
            write(plan([_rig("A"), _rig("B")]), out, source=sample_library(str(self.d)),
                  force=False)
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["B.krig"])
        self.assertEqual((out / "B.krig").read_bytes(), b"keep")

    def test_force_replaces_only_the_planned_files(self):
        out = self.d / "out"
        out.mkdir()
        (out / "A.krig").write_bytes(b"old")
        (out / "keep.txt").write_bytes(b"mine")
        write(plan([_rig("A")]), out, source=sample_library(str(self.d)), force=True)
        self.assertEqual((out / "A.krig").read_bytes(), _rig("A").blob)
        self.assertEqual((out / "keep.txt").read_bytes(), b"mine")

    def test_write_checks_the_destination_itself(self):
        live = self._live()
        before = sorted(p.relative_to(live) for p in live.rglob("*"))
        with self.assertRaises(ValueError):
            write(plan([_rig("A")]), live / "out", source=str(live), force=True)
        self.assertEqual(sorted(p.relative_to(live) for p in live.rglob("*")), before)

    def test_skipped_rigs_write_nothing(self):
        out = self.d / "out"
        n = write(plan([Rig(name="E", folder="", blob=b"")]), out,
                  source=sample_library(str(self.d)), force=False)
        self.assertEqual(n, 0)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
