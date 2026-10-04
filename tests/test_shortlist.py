"""Shortlist: amp-pattern relevance and the gain floor, plus criteria-file loading."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from _fixture import build_rmbackup

from kemperrig import Backup
from kemperrig.cli import main
from kemperrig.services.shortlist import load_criteria, matches_amp, shortlist

AMPS = ("Rectifier", "SLO")


class ShortlistTest(unittest.TestCase):
    def setUp(self):
        path = build_rmbackup(
            os.path.join(tempfile.mkdtemp(), "t.rmbackup"),
            rigs=[
                {"name": "Recto-hi", "gain": "6.0", "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
                {"name": "SLO-hi", "gain": "7.5", "amp_model": "SLO 100", "cabinet_name": "N/A"},
                {"name": "AC30-clean", "gain": "2.0", "amp_model": "AC30TBR", "cabinet_name": "N/A"},
                {"name": "Recto-low", "gain": "3.0", "amp_model": "Dual Rectifier", "cabinet_name": "N/A"},
            ],
        )
        self.rigs = Backup.open(path).rigs

    def test_default_gain_floor_and_amp_relevance(self):
        got = shortlist(self.rigs, AMPS)
        self.assertEqual({r.name for r in got}, {"Recto-hi", "SLO-hi"})

    def test_unmatched_amp_excluded_regardless_of_gain(self):
        got = shortlist(self.rigs, AMPS, gain_min=0.0)
        self.assertNotIn("AC30-clean", {r.name for r in got})
        self.assertIn("Recto-low", {r.name for r in got})

    def test_matches_amp_is_case_insensitive_substring(self):
        self.assertTrue(matches_amp("Dual Rectifier", AMPS))
        self.assertTrue(matches_amp("dual rectifier rev f", AMPS))
        self.assertFalse(matches_amp("AC30TBR", AMPS))
        self.assertFalse(matches_amp(None, AMPS))


class LoadCriteriaTest(unittest.TestCase):
    def _write(self, payload) -> str:
        path = os.path.join(tempfile.mkdtemp(), "crit.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        return path

    def test_reads_patterns_and_optional_fields(self):
        crit = load_criteria(self._write(
            {"amp_patterns": ["Recto"], "gain_min": 7.0, "context": "cab held constant"}))
        self.assertEqual(crit["amp_patterns"], ["Recto"])
        self.assertEqual(crit["gain_min"], 7.0)

    def test_grouped_patterns_flatten_in_order(self):
        crit = load_criteria(self._write(
            {"amp_patterns": {"Mesa": ["Recto", "DR2"], "Diezel": ["VH4"]}}))
        self.assertEqual(crit["amp_patterns"], ["Recto", "DR2", "VH4"])
        self.assertEqual(list(crit["amp_families"]), ["Mesa", "Diezel"])

    def test_rejects_criteria_without_patterns(self):
        with self.assertRaises(ValueError):
            load_criteria(self._write({"gain_min": 5.0}))


class ShippedCriteriaTest(unittest.TestCase):
    """The shipped example must stay loadable — it is what users copy."""

    def test_repo_criteria_file_is_valid(self):
        path = os.path.join(os.path.dirname(__file__), "..",
                            "config", "example-shortlist.json")
        crit = load_criteria(path)
        self.assertTrue(all(isinstance(p, str) and p for p in crit["amp_patterns"]))
        self.assertIn("Mesa Rectifier", crit["amp_families"])
        self.assertTrue(matches_amp("Dual Rectifier Rev F", crit["amp_patterns"]))


if __name__ == "__main__":
    unittest.main()


class CriteriaValidationTest(unittest.TestCase):
    """A criteria file is user-authored, so a wrong shape must be a message, not a traceback."""

    def _crit(self, d: str, body: str) -> str:
        p = os.path.join(d, "c.json")
        Path(p).write_text(body, encoding="utf-8")
        return p

    def _run(self, body: str) -> int:
        with tempfile.TemporaryDirectory() as d:
            lib = build_rmbackup(os.path.join(d, "L.rmbackup"),
                                 rigs=[{"name": "A", "gain": "6.0", "amp_model": "Recto",
                                        "cabinet_name": "N/A"}])
            return main(["shortlist", lib, "--criteria", self._crit(d, body)])

    def test_top_level_list_is_rejected(self):
        self.assertEqual(self._run("[]"), 1)

    def test_top_level_null_is_rejected(self):
        self.assertEqual(self._run("null"), 1)

    def test_amp_patterns_as_a_number_is_rejected(self):
        self.assertEqual(self._run('{"amp_patterns": 5}'), 1)

    def test_amp_patterns_as_a_list_of_numbers_is_rejected(self):
        self.assertEqual(self._run('{"amp_patterns": [1, 2]}'), 1)

    def test_non_numeric_gain_min_is_rejected(self):
        self.assertEqual(self._run('{"amp_patterns": ["Recto"], "gain_min": "x"}'), 1)

    def test_a_bare_string_is_not_silently_iterated_per_character(self):
        """"Recto" as a string once matched any amp containing r, e, c, t or o."""
        self.assertEqual(self._run('{"amp_patterns": "Recto"}'), 1)

    def test_a_well_formed_file_still_works(self):
        self.assertEqual(self._run('{"amp_patterns": ["Recto"], "gain_min": 1}'), 0)

    def test_an_empty_pattern_is_rejected_not_matched_against_everything(self):
        for body in ('{"amp_patterns": [""]}', '{"amp_patterns": ["Recto", "  "]}',
                     '{"amp_patterns": {"Mesa": [""]}}'):
            with self.subTest(body):
                self.assertEqual(self._run(body), 1)

    def test_a_gain_min_that_is_not_finite_is_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value):
                self.assertEqual(self._run(f'{{"amp_patterns": ["Recto"], "gain_min": {value}}}'),
                                 1)

    def test_an_integer_gain_min_too_large_for_a_float_is_not_a_traceback(self):
        self.assertEqual(self._run('{"amp_patterns": ["Recto"], "gain_min": 1' + "0" * 400 + "}"),
                         0)


class GainFlagTest(unittest.TestCase):
    """A NaN gain bound compares false against everything, so it would silently filter
    nothing; it is a usage error instead."""

    def test_nan_and_infinite_gain_flags_are_usage_errors(self):
        with tempfile.TemporaryDirectory() as d:
            lib = build_rmbackup(os.path.join(d, "L.rmbackup"), rigs=[{"name": "A"}])
            for argv in (["rigs", lib, "--gain-min", "nan"], ["rigs", lib, "--gain-max", "inf"],
                         ["shortlist", lib, "--criteria", "x.json", "--gain-min", "nan"]):
                with self.subTest(argv), redirect_stderr(StringIO()), \
                        self.assertRaises(SystemExit) as caught:
                    main(argv)
                self.assertEqual(caught.exception.code, 2)


class StudioEscapeHatchTest(unittest.TestCase):
    """`shortlist` is DI-only by default, so there must be a way out."""

    def _lib(self, d: str) -> str:
        return build_rmbackup(
            os.path.join(d, "L.rmbackup"),
            rigs=[{"name": "DI", "gain": "7.0", "amp_model": "Recto", "cabinet_name": "N/A"},
                  {"name": "Studio", "gain": "7.0", "amp_model": "Recto",
                   "cabinet_name": "V30 4x12"}])

    def _names(self, d: str, *extra) -> set[str]:
        crit = os.path.join(d, "c.json")
        Path(crit).write_text('{"amp_patterns": ["Recto"], "gain_min": 1}', encoding="utf-8")
        buf = StringIO()
        with redirect_stdout(buf):
            main(["shortlist", self._lib(d), "--criteria", crit, "--json", *extra])
        return {r["name"] for r in json.loads(buf.getvalue())["rigs"]}

    def test_di_only_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._names(d), {"DI"})

    def test_include_studio_widens_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self._names(d, "--include-studio"), {"DI", "Studio"})
