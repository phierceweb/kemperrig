"""The one invariant: `rename` writes a new archive and never reaches a source path.

The alias cases are the reason this file exists — a string compare misses every one of
them, and on a case-insensitive filesystem that silently destroys the library."""

import io
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from _fixture import build_rmbackup, build_snapshot, sample_library

from kemperrig.cli import main
from kemperrig.services.edit import rename_rig

_lib = sample_library


class RenameSafetyTest(unittest.TestCase):
    def test_refuses_the_exact_source_path(self):
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d)
            self.assertEqual(main(["rename", p, "A", "B", "-o", p]), 2)

    def test_refuses_a_path_that_aliases_the_source(self):
        """On a case-insensitive filesystem `lib` and `Lib` are one file — a string
        compare misses it and the source is destroyed."""
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d, "Lib.rmbackup")
            alias = os.path.join(d, "lib.rmbackup")
            before = Path(p).read_bytes()
            rc = main(["rename", p, "A", "B", "-o", alias])
            if os.path.exists(alias) and not os.path.samefile(p, alias):
                self.skipTest("case-sensitive filesystem — no alias to refuse")
            self.assertEqual(rc, 2)
            self.assertEqual(Path(p).read_bytes(), before, "source was modified")

    def test_writes_a_distinct_output_and_leaves_the_source_alone(self):
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d)
            before = Path(p).read_bytes()
            out = os.path.join(d, "renamed.rmbackup")
            self.assertEqual(main(["rename", p, "A", "B", "-o", out]), 0)
            self.assertTrue(os.path.exists(out))
            self.assertEqual(Path(p).read_bytes(), before, "source was modified")


class RenameNameClashTest(unittest.TestCase):
    """A rename that would leave slots ambiguous, or rename nothing, is refused up front."""

    def _refused(self, old: str, new: str, why: str):
        with tempfile.TemporaryDirectory() as d:
            src = build_rmbackup(
                os.path.join(d, "lib.rmbackup"), rigs=[{"name": "A"}, {"name": "B"}],
                performances=[{"name": "P", "slots": [{"rig_name": "B"}, {"rig_name": "Ghost"}]}])
            out, err = os.path.join(d, "out.rmbackup"), io.StringIO()
            with redirect_stderr(err):
                code = main(["rename", src, old, new, "-o", out])
            self.assertEqual(code, 2)
            self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
            self.assertIn(why, err.getvalue())
            self.assertFalse(os.path.exists(out))

    def test_a_new_name_another_rig_has(self):
        self._refused("A", "B", "a rig named 'B' is already in")

    def test_an_old_name_only_a_slot_has(self):
        self._refused("Ghost", "New", "no rig named 'Ghost'")

    def test_a_new_name_only_a_dangling_slot_has(self):
        """The slot was built from another rig; the rename would silently claim it."""
        self._refused("A", "Ghost", "a performance slot already loads a rig named 'Ghost'")


class RenameSourceLayoutTest(unittest.TestCase):
    """A zip that is not a Rig Manager backup is named as such, not as a rig it lacks."""

    def _refused(self, entries: dict[str, bytes], why: str):
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "src.rmbackup"), os.path.join(d, "out.rmbackup")
            with zipfile.ZipFile(src, "w") as zf:
                for name, data in entries.items():
                    zf.writestr(name, data)
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(main(["rename", src, "A", "B", "-o", out]), 2)
            self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
            self.assertIn(why, err.getvalue())
            with self.assertRaisesRegex(ValueError, why):
                rename_rig(src, out, "A", "B")
            self.assertFalse(os.path.exists(out))

    def test_a_zip_with_no_library_db(self):
        self._refused({"notes.txt": b"hi"}, "not a Rig Manager backup")

    def test_a_backup_zipped_one_folder_too_deep(self):
        with tempfile.TemporaryDirectory() as d:
            src = build_rmbackup(os.path.join(d, "lib.rmbackup"), rigs=[{"name": "A"}])
            with zipfile.ZipFile(src) as zf:
                entries = {f"RigManager/{n}": zf.read(n) for n in zf.namelist()}
        self._refused(entries, "point at the Rig Manager library root")


class RenameOutputOverwriteTest(unittest.TestCase):
    """`-o` overwrites no existing archive without `--force`, whichever archive it is."""

    def _two(self, d: str) -> tuple[str, str, bytes]:
        src = _lib(d, "Src.rmbackup")
        other = os.path.join(d, "Other.rmbackup")
        Path(other).write_bytes(Path(src).read_bytes())
        return src, other, Path(other).read_bytes()

    def test_refuses_an_existing_output_file(self):
        with tempfile.TemporaryDirectory() as d:
            src, other, before = self._two(d)
            self.assertEqual(main(["rename", src, "A", "B", "-o", other]), 2)
            self.assertEqual(Path(other).read_bytes(), before, "output was overwritten")

    def test_force_allows_an_existing_output_file(self):
        with tempfile.TemporaryDirectory() as d:
            src, other, before = self._two(d)
            self.assertEqual(main(["rename", src, "A", "B", "-o", other, "--force"]), 0)
            self.assertNotEqual(Path(other).read_bytes(), before)

    def _refused_in_one_line(self, argv):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main(argv), 2)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        return err.getvalue()

    def test_refuses_an_output_that_is_a_folder(self):
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d)
            before = Path(p).read_bytes()
            folder = os.path.join(d, "out")
            os.mkdir(folder)
            self.assertIn("folder", self._refused_in_one_line(["rename", p, "A", "B", "-o", folder]))
            self.assertEqual(os.listdir(folder), [])
            self.assertEqual(Path(p).read_bytes(), before, "source was modified")

    def test_refuses_a_blank_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d)
            for blank in ("", "   "):
                with self.subTest(out=repr(blank)):
                    self.assertIn("-o", self._refused_in_one_line(["rename", p, "A", "B", "-o", blank]))

    def test_missing_folders_on_the_way_to_the_output_are_created(self):
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d)
            before = Path(p).read_bytes()
            out = os.path.join(d, "new", "deeper", "out.rmbackup")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["rename", p, "A", "B", "-o", out]), 0)
            self.assertTrue(zipfile.is_zipfile(out))
            self.assertEqual(Path(p).read_bytes(), before, "source was modified")

    def test_force_still_refuses_the_source_itself(self):
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d)
            before = Path(p).read_bytes()
            self.assertEqual(main(["rename", p, "A", "B", "-o", p, "--force"]), 2)
            self.assertEqual(Path(p).read_bytes(), before, "source was modified")


class RenameAliasTest(unittest.TestCase):
    """Alias forms that exist on every filesystem, so the invariant is covered on CI too.

    The case-variant alias only exists on a case-insensitive filesystem and skips elsewhere;
    symlinks, hardlinks and `..` paths do not, and they exercise the same guard.
    """

    def _src(self, d: str) -> tuple[str, bytes]:
        p = _lib(d)
        return p, Path(p).read_bytes()

    def _refused(self, src: str, out: str, before: bytes) -> None:
        """--force is deliberate: it bypasses the exists-check, so only the alias guard can
        refuse. Without it these would pass on the exists-check alone and prove nothing."""
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = main(["rename", src, "A", "B", "-o", out, "--force"])
        self.assertEqual(rc, 2)
        self.assertIn("refusing to overwrite the source", err.getvalue())
        self.assertEqual(Path(src).read_bytes(), before, "source was modified")

    def test_refuses_a_symlink_to_the_source(self):
        with tempfile.TemporaryDirectory() as d:
            src, before = self._src(d)
            link = os.path.join(d, "link.rmbackup")
            os.symlink(src, link)
            self._refused(src, link, before)

    def test_refuses_when_the_source_is_reached_through_a_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            src, before = self._src(d)
            link = os.path.join(d, "link.rmbackup")
            os.symlink(src, link)
            self._refused(link, src, before)

    def test_refuses_a_hardlink_to_the_source(self):
        with tempfile.TemporaryDirectory() as d:
            src, before = self._src(d)
            hard = os.path.join(d, "hard.rmbackup")
            os.link(src, hard)
            self._refused(src, hard, before)

    def test_refuses_a_dotdot_path_that_resolves_to_the_source(self):
        with tempfile.TemporaryDirectory() as d:
            src, before = self._src(d)
            os.makedirs(os.path.join(d, "sub"), exist_ok=True)
            self._refused(src, os.path.join(d, "sub", "..", os.path.basename(src)), before)

    def test_refuses_the_source_reached_through_a_symlinked_parent_directory(self):
        with tempfile.TemporaryDirectory() as d:
            real = os.path.join(d, "real")
            os.makedirs(real)
            src, before = self._src(real)
            os.symlink(real, os.path.join(d, "via"))
            self._refused(src, os.path.join(d, "via", os.path.basename(src)), before)


class RenameDestinationTest(unittest.TestCase):
    """rename refuses what extract and --write-golden refuse, and says what it takes."""

    def _refused(self, argv: list[str], needle: str) -> None:
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = main(argv)
        self.assertEqual(rc, 2, err.getvalue())
        self.assertIn(needle, err.getvalue())
        self.assertEqual(err.getvalue().count("\n"), 1)

    def test_refuses_an_output_inside_a_rig_manager_library(self):
        with tempfile.TemporaryDirectory() as d:
            src = _lib(d)
            (Path(d) / "RigManager" / "Local Library").mkdir(parents=True)
            out = Path(d) / "RigManager" / "Local Library" / "new.rmbackup"
            self._refused(["rename", src, "A", "B", "-o", str(out)], "Rig Manager library")
            self.assertFalse(out.exists())

    def test_refuses_an_output_through_a_symlink_loop(self):
        with tempfile.TemporaryDirectory() as d:
            src = _lib(d)
            os.symlink(os.path.join(d, "b"), os.path.join(d, "a"))
            os.symlink(os.path.join(d, "a"), os.path.join(d, "b"))
            self._refused(["rename", src, "A", "B", "-o", os.path.join(d, "a", "new.rmbackup")],
                          "cannot resolve")

    def test_refuses_a_source_that_is_not_an_archive(self):
        with tempfile.TemporaryDirectory() as d:
            snap = build_snapshot(os.path.join(d, "S - 2020-01-01 00-00-00R2.db"),
                                  rigs=[{"name": "A"}])
            for src in (snap, d):
                with self.subTest(src=os.path.basename(src)):
                    self._refused(["rename", src, "A", "B", "-o", os.path.join(d, "o.rmbackup")],
                                  "rename takes a .rmbackup")

    def test_the_service_guards_itself(self):
        from kemperrig.services.edit import rename_rig
        with tempfile.TemporaryDirectory() as d:
            src = _lib(d)
            with self.assertRaises(ValueError):
                rename_rig(src, src, "A", "B", force=True)
