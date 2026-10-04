"""What `rename` says and writes beyond the rename itself: that its archive is unconfirmed in
Rig Manager, that `-o dir/` names a folder, and that every other entry is copied verbatim."""

import io
import os
import tempfile
import unittest
import warnings
import zipfile
from contextlib import redirect_stderr, redirect_stdout

from _fixture import sample_library

from kemperrig.cli import main
from kemperrig.services.edit import rename_rig


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as e:   # --help
            code = e.code
    return code, out.getvalue(), err.getvalue()


class UnconfirmedRestoreTest(unittest.TestCase):
    def test_help_says_the_archive_is_unconfirmed_in_rig_manager(self):
        code, out, _ = _run(["rename", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("not confirmed to restore", " ".join(out.split()))

    def test_a_rename_says_so_and_to_keep_the_original(self):
        with tempfile.TemporaryDirectory() as d:
            p = sample_library(d)
            code, out, _ = _run(["rename", p, "A", "B", "-o", os.path.join(d, "out.rmbackup")])
            self.assertEqual(code, 0)
            self.assertIn("not confirmed to restore into Rig Manager — keep the original", out)


class FolderOutputTest(unittest.TestCase):
    def test_a_trailing_separator_names_a_folder_and_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = sample_library(d)
            for argv in (["rename", p, "A", "B", "-o"], ["summary", p, "--write-golden"]):
                with self.subTest(command=argv[0]):
                    folder = os.path.join(d, f"new-{argv[0]}")
                    code, _, err = _run([*argv, folder + os.sep])
                    self.assertEqual(code, 2)
                    self.assertIn("is a folder — name a file", err)
                    self.assertFalse(os.path.exists(folder))


class VerbatimEntriesTest(unittest.TestCase):
    def test_a_repeated_entry_keeps_each_copy_quietly(self):
        with tempfile.TemporaryDirectory() as d:
            src = sample_library(d)
            with zipfile.ZipFile(src, "a") as zf, warnings.catch_warnings():
                warnings.simplefilter("ignore")
                zf.writestr("notes.txt", b"FIRST")
                zf.writestr("notes.txt", b"SECOND")
            out = os.path.join(d, "out.rmbackup")
            with warnings.catch_warnings(record=True) as raised:
                warnings.simplefilter("always")
                rename_rig(src, out, "A", "B")
            self.assertEqual([str(w.message) for w in raised], [])
            with zipfile.ZipFile(out) as zf:
                copies = [zf.read(i) for i in zf.infolist() if i.filename == "notes.txt"]
            self.assertEqual(copies, [b"FIRST", b"SECOND"])


if __name__ == "__main__":
    unittest.main()
