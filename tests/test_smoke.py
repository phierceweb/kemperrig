"""Every command against the synthetic sample library: exit codes, parseable `--json`, and
writers that leave their source byte-identical."""

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _sample import build_sample

from kemperrig.cli import main


def _cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        try:
            rc = main(list(argv))
        except SystemExit as e:
            rc = e.code
    return rc, out.getvalue(), err.getvalue()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.p = build_sample(Path(cls._tmp.name) / "sample")
        cls.out = Path(cls._tmp.name) / "out"

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _reads(self):
        p = self.p
        b, older, newer = str(p.backup), str(p.snapshots[0]), str(p.snapshots[1])
        return [
            (0, ["summary", b]), (0, ["rigs", b]), (0, ["analyze", b]),
            (1, ["analyze", b, "--strict"]), (0, ["doctor", b]), (1, ["doctor", b, "--strict"]),
            (0, ["presets", b]), (0, ["performances", b]),
            (0, ["rig", b, "Recto Rhythm"]), (0, ["pages", b, "Recto Rhythm"]),
            (0, ["pages", b, "--all"]), (0, ["shortlist", b, "--criteria", str(p.criteria)]),
            (0, ["pack", str(p.rigpack)]), (0, ["pack", str(p.rigpack), "--against", b]),
            (0, ["pack", str(p.presetpack)]),
            (1, ["diff", older, newer]), (0, ["diff", b, b]),
            (0, ["history", str(p.live / "Backups")]),
            (0, ["history", str(p.live / "Backups"), "--rig", "Recto Lead"]),
        ]

    def test_every_read_command_exits_as_documented(self):
        for code, argv in self._reads():
            with self.subTest(argv=" ".join(argv[:1] + argv[2:])):
                rc, _, err = _cli(*argv)
                self.assertEqual(rc, code, err)

    def test_every_json_document_parses(self):
        for code, argv in self._reads():
            with self.subTest(argv=" ".join(argv[:1] + argv[2:])):
                rc, out, err = _cli(*argv, "--json")
                self.assertEqual(rc, code, err)
                json.loads(out)

    def test_every_source_kind_reads(self):
        p = self.p
        for source in (p.backup, p.live, p.snapshots[0], p.rigpack):
            for cmd in ("summary", "rigs", "doctor"):
                with self.subTest(source=source.name, cmd=cmd):
                    rc, _, err = _cli(cmd, str(source))
                    self.assertEqual(rc, 0, err)

    def test_the_writers_leave_their_source_untouched(self):
        before = _sha(self.p.backup)
        writes = [
            ["rename", str(self.p.backup), "Spare Lead", "Spare Two",
             "-o", str(self.out / "renamed.rmbackup")],
            ["extract", str(self.p.backup), "-o", str(self.out / "krig"), "--all"],
            ["summary", str(self.p.backup), "--write-golden", str(self.out / "census.json")],
        ]
        for argv in writes:
            with self.subTest(cmd=argv[0]):
                rc, _, err = _cli(*argv)
                self.assertEqual(rc, 0, err)
        self.assertEqual(_sha(self.p.backup), before)
        self.assertTrue(list((self.out / "krig").glob("*.krig")))
        json.loads((self.out / "census.json").read_text())


if __name__ == "__main__":
    unittest.main()
