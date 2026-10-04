"""A real library against its census — opt-in, and nothing here looks for a library itself.

`KEMPERRIG_GOLDEN` names the census `summary --write-golden` wrote and `KEMPERRIG_LIBRARY`
the library it describes; unless both are set and exist, the check skips. When the library
changes on purpose, regenerate the census rather than relaxing a field.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from _fixture import build_rmbackup, sample_library

from kemperrig import _json
from kemperrig.cli import main
from kemperrig.model import Backup
from kemperrig.services import census

ABSENT = "<absent>"


def fields(doc: dict, prefix: str = "") -> dict[str, object]:
    """Every value of a census by dotted path; lists and empty objects are values, and keys
    starting `_` are notes, not fields."""
    out: dict[str, object] = {}
    for key, value in doc.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and value:
            out.update(fields(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def mismatches(expected: dict, actual: dict) -> list[str]:
    want, got = fields(expected), fields(actual)
    return [f"{p}: census {want.get(p, ABSENT)!r}, library {got.get(p, ABSENT)!r}"
            for p in sorted(want.keys() | got.keys()) if want.get(p, ABSENT) != got.get(p, ABSENT)]


def _setting(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def _why_skipped() -> str | None:
    golden, library = _setting("KEMPERRIG_GOLDEN"), _setting("KEMPERRIG_LIBRARY")
    if golden is None or library is None:
        return "opt-in: set KEMPERRIG_GOLDEN and KEMPERRIG_LIBRARY"
    if not os.path.isfile(golden):
        return "KEMPERRIG_GOLDEN names no file"
    if not os.path.exists(library):
        return "KEMPERRIG_LIBRARY names nothing that exists"
    return None


class GoldenLibraryTest(unittest.TestCase):
    """The library `KEMPERRIG_LIBRARY` names, field by field against its census."""

    @classmethod
    def setUpClass(cls):
        why = _why_skipped()
        if why:
            raise unittest.SkipTest(why)
        with open(_setting("KEMPERRIG_GOLDEN"), encoding="utf-8") as fh:
            cls.expected = json.load(fh)
        cls.actual = _json.census_doc(census.take(Backup.open(_setting("KEMPERRIG_LIBRARY"))))

    def test_the_file_is_a_census(self):
        self.assertEqual(self.expected.get("census"), _json.CENSUS_FORMAT,
                         "KEMPERRIG_GOLDEN was not written by this version's "
                         "`summary --write-golden` — regenerate it")

    def test_every_field_matches(self):
        want, got = fields(self.expected), fields(self.actual)
        for path in sorted(want.keys() | got.keys()):
            with self.subTest(field=path):
                self.assertEqual(got.get(path, ABSENT), want.get(path, ABSENT))


def _run_golden(golden: str | None, library: str | None) -> unittest.TestResult:
    env = {k: v for k, v in (("KEMPERRIG_GOLDEN", golden), ("KEMPERRIG_LIBRARY", library)) if v}
    with mock.patch.dict(os.environ, env, clear=False):
        for name in {"KEMPERRIG_GOLDEN", "KEMPERRIG_LIBRARY"} - env.keys():
            os.environ.pop(name, None)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(GoldenLibraryTest)
        return unittest.TextTestRunner(stream=io.StringIO()).run(suite)


class GoldenCheckTest(unittest.TestCase):
    """The opt-in check itself, against fixture libraries."""

    def setUp(self):
        self.d = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.lib = sample_library(str(self.d))
        self.golden = str(self.d / "golden.json")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["summary", self.lib, "--write-golden", self.golden]), 0)

    def _census(self, path: str) -> dict:
        return _json.census_doc(census.take(Backup.open(path)))

    def test_it_passes_on_the_library_the_census_was_written_from(self):
        result = _run_golden(self.golden, self.lib)
        self.assertTrue(result.wasSuccessful(), result.failures)
        self.assertEqual((result.testsRun, len(result.skipped)), (2, 0))

    def test_it_fails_when_the_library_has_moved(self):
        grown = build_rmbackup(str(self.d / "grown.rmbackup"), rigs=[
            {"name": "A", "gain": "5.0", "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
            {"name": "B", "gain": "6.0", "amp_model": "Dual Rectifier", "cabinet_name": "N/A"}])
        self.assertFalse(_run_golden(self.golden, grown).wasSuccessful())
        with open(self.golden, encoding="utf-8") as fh:
            found = mismatches(json.load(fh), self._census(grown))
        self.assertIn("totals.rigs: census 1, library 2", found)

    def test_it_fails_on_a_file_that_is_not_a_census(self):
        other = self.d / "other.json"
        other.write_text(json.dumps({"totals": {"rigs": 1}}), encoding="utf-8")
        self.assertFalse(_run_golden(str(other), self.lib).wasSuccessful())

    def test_it_skips_unless_both_settings_name_something(self):
        for golden, library in ((None, None), (self.golden, None), (None, self.lib),
                                (str(self.d / "missing.json"), self.lib),
                                (self.golden, str(self.d / "missing.rmbackup"))):
            with self.subTest(golden=golden, library=library):
                result = _run_golden(golden, library)
                self.assertTrue(result.wasSuccessful())
                self.assertEqual((result.testsRun, len(result.skipped)), (0, 1))

    def test_notes_are_not_fields_and_absence_is_a_mismatch(self):
        self.assertEqual(fields({"_comment": "x", "a": {"b": 1, "c": {}}, "d": [1]}),
                         {"a.b": 1, "a.c": {}, "d": [1]})
        self.assertEqual(mismatches({"a": 1}, {}), ["a: census 1, library '<absent>'"])


if __name__ == "__main__":
    unittest.main()
