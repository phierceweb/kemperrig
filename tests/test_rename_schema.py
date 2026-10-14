"""`rename` on a database whose schema nobody here wrote: none of its triggers runs, so the
rename changes no row but the renamed ones, and the schema reaches the output as it was."""

import io
import os
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

from _fixture import RIG_FIELDS, _rigs_ddl, build_rmbackup
from _payloads import make_blob, rig_track

from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services.edit import _open

# An UPDATE trigger rewriting every other rig, and one writing an FTS5 table's shadow storage.
_OTHER_ROWS = ("CREATE TRIGGER t AFTER UPDATE ON Rigs BEGIN "
               "UPDATE Rigs SET \"Author\" = 'trigger' WHERE id <> NEW.id; END;")
_SHADOW_TABLE = ("CREATE VIRTUAL TABLE f USING fts5(x);"
                 "CREATE TRIGGER t AFTER UPDATE ON Rigs BEGIN "
                 "INSERT INTO f_data VALUES (999, x'00'); END;")
# Rig names compared without case.
_NOCASE_NAME = ("ALTER TABLE Rigs RENAME TO old;"
                + _rigs_ddl(RIG_FIELDS).replace('"Name" TEXT', '"Name" TEXT COLLATE NOCASE')
                + "; INSERT INTO Rigs SELECT * FROM old; DROP TABLE old;")
# Payloads made unique with a conflict clause that deletes the row a new value collides with.
_REPLACE_ON_CONFLICT = ("ALTER TABLE Rigs_blobs RENAME TO old;"
                        "CREATE TABLE Rigs_blobs (id INTEGER PRIMARY KEY, data BLOB,"
                        " UNIQUE(data) ON CONFLICT REPLACE);"
                        "INSERT INTO Rigs_blobs SELECT * FROM old; DROP TABLE old;")


def _entries(path: str) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _rig_db(entries: dict[str, bytes]) -> str:
    return next(n for n in entries if n.startswith("Local Library/"))


def _with_schema(path: str, script: str) -> None:
    """Rewrite the archive so its rig db also holds what `script` creates."""
    entries = _entries(path)
    name = _rig_db(entries)
    con = sqlite3.connect(":memory:")
    con.deserialize(entries[name])
    con.executescript(script)
    entries[name] = con.serialize()
    con.close()
    with zipfile.ZipFile(path, "w") as zf:
        for n, data in entries.items():
            zf.writestr(n, data)


class CraftedSchemaTest(unittest.TestCase):
    def _renamed(self, d: str, script: str) -> str:
        src = build_rmbackup(os.path.join(d, "lib.rmbackup"),
                             rigs=[{"name": "A", "author": "x"}, {"name": "B", "author": "x"}])
        _with_schema(src, script)
        out = os.path.join(d, "out.rmbackup")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["rename", src, "A", "C", "-o", out]), 0)
        return out

    def test_a_trigger_rewriting_other_rows_never_runs(self):
        with tempfile.TemporaryDirectory() as d:
            rigs = Backup.open(self._renamed(d, _OTHER_ROWS)).rigs
            self.assertEqual(sorted((r.name, r.author) for r in rigs), [("B", "x"), ("C", "x")])

    def test_a_trigger_writing_shadow_tables_never_runs_and_is_kept(self):
        with tempfile.TemporaryDirectory() as d:
            entries = _entries(self._renamed(d, _SHADOW_TABLE))
            con = sqlite3.connect(":memory:")
            con.deserialize(entries[_rig_db(entries)])
            self.assertEqual(con.execute("SELECT count(*) FROM f_data WHERE id = 999").fetchone(),
                             (0,))
            self.assertEqual(con.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'"
                                         ).fetchall(), [("t",)])
            con.close()

    def test_a_conflict_clause_never_drops_another_row(self):
        with tempfile.TemporaryDirectory() as d:
            src = build_rmbackup(os.path.join(d, "lib.rmbackup"), rigs=[
                {"name": "A", "blob": make_blob([rig_track("A")])},
                {"name": "X", "blob": make_blob([rig_track("B")])}])
            _with_schema(src, _REPLACE_ON_CONFLICT)
            out, err = os.path.join(d, "out.rmbackup"), io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(main(["rename", src, "A", "B", "-o", out]), 1)
            self.assertEqual(err.getvalue().count("\n"), 1)
            self.assertIn("its schema refuses the rename", err.getvalue())
            self.assertFalse(os.path.exists(out))

    def test_a_case_blind_collation_still_renames_only_the_exact_name(self):
        with tempfile.TemporaryDirectory() as d:
            src = build_rmbackup(os.path.join(d, "lib.rmbackup"),
                                 rigs=[{"name": "A"}, {"name": "a"}])
            _with_schema(src, _NOCASE_NAME)
            out = os.path.join(d, "out.rmbackup")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["rename", src, "A", "C", "-o", out]), 0)
            self.assertEqual(sorted(r.name for r in Backup.open(out).rigs), ["C", "a"])

    def test_the_connection_it_rewrites_is_defensive_with_triggers_off(self):
        src = sqlite3.connect(":memory:")
        src.execute("CREATE TABLE t (x)")
        con = _open(src.serialize())
        self.assertTrue(con.getconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE))
        self.assertFalse(con.getconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_TRIGGER))
        con.close()
        src.close()


if __name__ == "__main__":
    unittest.main()
