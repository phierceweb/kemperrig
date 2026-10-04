"""What the CLI does with input it did not write: malformed archives, unreadable
databases, and a path pointing one level off the library root."""

import io
import os
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from _fixture import RIG_FIELDS, RIGS_DDL, _db_bytes, sample_library

from kemperrig.cli import main

_lib = sample_library

_CRITERIA = os.path.join(os.path.dirname(__file__), "..", "config", "example-shortlist.json")

class MalformedInputTest(unittest.TestCase):
    """Every one of these must be a one-line message and exit 1, never a traceback."""

    def _run(self, argv) -> int:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KEMPERRIG_LIBRARY", None)
            return main(argv)

    def test_missing_file(self):
        self.assertEqual(self._run(["summary", "/nope/missing.rmbackup"]), 1)

    def test_not_a_zip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.rmbackup")
            Path(p).write_text("not a zip")
            self.assertEqual(self._run(["summary", p]), 1)

    def test_zip_without_databases(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "empty.rmbackup")
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("readme.txt", "nothing here")
            self.assertEqual(self._run(["summary", p]), 1)

    def test_zip_with_a_corrupt_database(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "corrupt.rmbackup")
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("Local Library/Guitar/repositoryR2.db", "not sqlite")
                zf.writestr("info.xml", "<info/>")
            self.assertEqual(self._run(["summary", p]), 1)

    def test_directory_that_is_not_a_rig_manager_tree(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "Some Folder"))
            self.assertEqual(self._run(["summary", d]), 1)

    def test_bad_criteria_json(self):
        with tempfile.TemporaryDirectory() as d:
            crit = os.path.join(d, "crit.json")
            Path(crit).write_text("{ not json")
            self.assertEqual(self._run(["shortlist", _lib(d), "--criteria", crit]), 1)

    def test_criteria_without_patterns(self):
        with tempfile.TemporaryDirectory() as d:
            crit = os.path.join(d, "crit.json")
            Path(crit).write_text('{"gain_min": 5.0}')
            self.assertEqual(self._run(["shortlist", _lib(d), "--criteria", crit]), 1)


def _drop_amp_pickup(data: bytes) -> bytes:
    con = sqlite3.connect(":memory:")
    con.deserialize(data)
    con.execute('ALTER TABLE Rigs DROP COLUMN "Amp Pickup"')
    con.commit()
    return con.serialize()


class DamagedDatabaseTest(unittest.TestCase):
    """A damaged folder db inside an archive or a live tree names that db, not just the
    SQLite error."""

    def _err(self, path: str) -> str:
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main(["summary", path]), 1)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        return err.getvalue()

    def _rebuilt(self, d: str, damage) -> tuple[str, str]:
        with zipfile.ZipFile(_lib(d)) as zf:
            items = [(i, zf.read(i)) for i in zf.infolist()]
        entry = next(i.filename for i, _ in items if i.filename.startswith("Local Library/"))
        out = os.path.join(d, "damaged.rmbackup")
        with zipfile.ZipFile(out, "w") as zf:
            for info, data in items:
                zf.writestr(info, damage(data) if info.filename == entry else data)
        return out, entry

    def test_a_truncated_folder_db_in_an_archive(self):
        with tempfile.TemporaryDirectory() as d:
            path, entry = self._rebuilt(d, lambda data: data[:500])
            self.assertIn(f"{entry} in {path}", self._err(path))

    def test_a_folder_db_missing_a_column(self):
        with tempfile.TemporaryDirectory() as d:
            path, entry = self._rebuilt(d, _drop_amp_pickup)
            err = self._err(path)
            self.assertIn(f"{entry} in {path}", err)
            self.assertIn("Amp Pickup", err)

    def test_a_truncated_folder_db_in_a_live_tree(self):
        with tempfile.TemporaryDirectory() as d:
            live = Path(d) / "RigManager"
            with zipfile.ZipFile(_lib(d)) as zf:
                zf.extractall(live)
            db = next(live.glob("Local Library/**/repositoryR2.db"))
            db.write_bytes(db.read_bytes()[:500])
            self.assertIn(str(db), self._err(str(live)))


class MisRootedLibraryTest(unittest.TestCase):
    """A path one level off must fail loudly: read as `rigs: 0` and exit 0, the parent of a
    Rig Manager tree is indistinguishable from an empty library, and `analyze --strict` goes
    green on it."""

    def _nested(self, d: str) -> str:
        """A live tree whose dbs sit one level too deep, as if the parent were given."""
        root = os.path.join(d, "parent")
        inner = os.path.join(root, "RigManager")
        os.makedirs(inner)
        src = _lib(d)
        with zipfile.ZipFile(src) as zf:
            zf.extractall(inner)
        return root

    def test_live_tree_one_level_too_deep_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._nested(d)
            self.assertTrue(list(Path(root).rglob("repositoryR2.db")), "probe needs real dbs")
            self.assertEqual(main(["summary", root]), 1)

    def test_analyze_strict_does_not_go_green_on_a_mis_rooted_path(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["analyze", "--strict", self._nested(d)]), 1)

    def test_archive_zipped_from_the_parent_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src = _lib(d)
            nested = os.path.join(d, "nested.rmbackup")
            with zipfile.ZipFile(src) as zin, zipfile.ZipFile(nested, "w") as zout:
                for item in zin.infolist():
                    zout.writestr(f"RigManager/{item.filename}", zin.read(item.filename))
            self.assertEqual(main(["summary", nested]), 1)

    def test_a_matched_but_empty_library_folder_still_opens(self):
        """A `Local Library/<folder>` db with no rows matched a rule — not an error."""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "Empty.rmbackup")
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("info.xml", "<info/>")
                zf.writestr("Local Library/F/repositoryR2.db",
                            _db_bytes(RIGS_DDL, "Rigs_blobs", RIG_FIELDS, []))
            self.assertEqual(main(["summary", p]), 0)


class ZeroByteDatabaseTest(unittest.TestCase):
    def test_zero_byte_db_is_a_one_line_error(self):
        """sqlite3.deserialize(b"") raises MemoryError, which the boundary does not catch."""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "Zero.rmbackup")
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("info.xml", "<info/>")
                zf.writestr("Local Library/F/repositoryR2.db", b"")
            self.assertEqual(main(["summary", p]), 1)


