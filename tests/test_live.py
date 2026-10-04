"""Backup.open on a live Rig Manager directory tree (unzipped .rmbackup layout)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from kemperrig.model import Backup

RIG_COLS = ["Filename", "Name", "Date", "Author", "Comment", "Gain", "Amp Model",
            "Amp Name", "Amp Comment", "Amp Channel", "Source Amp", "Amp Model Year",
            "Amp Location", "Amp Pickup", "Cabinet Name", "Mic Type", "Mic Position",
            "Speaker Manufacturer", "Speaker Model", "Profile Type"]


def _make_rigs_db(path: Path, name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    cols = ", ".join(f'"{c}" TEXT' for c in RIG_COLS)
    con.execute(f"CREATE TABLE Rigs (id INTEGER PRIMARY KEY, {cols})")
    con.execute("CREATE TABLE Rigs_blobs (id INTEGER PRIMARY KEY, data BLOB)")
    values = {c: f"{name}-{c}" for c in RIG_COLS}
    values["Name"] = name
    values["Gain"] = "5.5"
    col_names = ", ".join(f'"{c}"' for c in values)
    qmarks = ", ".join("?" for _ in values)
    con.execute(f"INSERT INTO Rigs (id, {col_names}) VALUES (1, {qmarks})",
                list(values.values()))
    con.execute("INSERT INTO Rigs_blobs (id, data) VALUES (1, ?)", (b"KThd-test",))
    con.commit()
    con.close()


def _make_presets_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE Presets (id INTEGER PRIMARY KEY, Filename TEXT, "Name" TEXT, '
                '"Preset Class" TEXT, "Preset Category" TEXT, "Preset Type" TEXT)')
    con.execute("CREATE TABLE Presets_blobs (id INTEGER PRIMARY KEY, data BLOB)")
    con.execute('INSERT INTO Presets VALUES (1, "f", "My IR", "6", "cat", "t")')
    con.commit()
    con.close()


class OpenLiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _make_rigs_db(self.root / "Local Library" / "AmpX" / "repositoryR2.db", "RigOne")
        _make_presets_db(self.root / "Prst" / "Local Library" / "Cabinet IRs"
                         / "repositoryR2.db")
        # noise that must be ignored: nested Prf db + a non-repository db
        _make_rigs_db(self.root / "Prf" / "Local Library" / "Sub" / "repositoryR2.db", "Nope")
        (self.root / "RigExchangeR2.db").write_bytes(b"not opened")

    def tearDown(self):
        self.tmp.cleanup()

    def test_open_live_reads_rigs_and_presets(self):
        b = Backup.open_live(self.root)
        self.assertEqual([r.name for r in b.rigs], ["RigOne"])
        self.assertEqual(b.rigs[0].folder, "AmpX")
        self.assertEqual(b.rigs[0].gain, 5.5)
        self.assertEqual(b.rigs[0].blob, b"KThd-test")
        self.assertEqual([p.name for p in b.presets], ["My IR"])
        self.assertEqual(b.presets[0].folder, "Local Library/Cabinet IRs")
        self.assertEqual(b.performances, [])

    def test_open_dispatches_directories_to_live(self):
        b = Backup.open(str(self.root))
        self.assertEqual([r.name for r in b.rigs], ["RigOne"])


if __name__ == "__main__":
    unittest.main()
