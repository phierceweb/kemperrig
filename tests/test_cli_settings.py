"""How the CLI resolves settings and presents itself: env-var fallbacks, the program
name, the error prefix, and disambiguating a rig name used more than once."""

import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from importlib.metadata import entry_points
from pathlib import Path
from unittest import mock

from _fixture import build_rmbackup, sample_library

from kemperrig import __version__
from kemperrig.cli import main

_lib = sample_library

_CRITERIA = os.path.join(os.path.dirname(__file__), "..", "config", "example-shortlist.json")

class EnvironmentResolutionTest(unittest.TestCase):
    def test_library_comes_from_the_environment_when_no_path_is_given(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"KEMPERRIG_LIBRARY": _lib(d)}):
                self.assertEqual(main(["summary"]), 0)

    def test_an_explicit_path_wins_over_the_environment(self):
        with tempfile.TemporaryDirectory() as d:
            good = _lib(d, "Good.rmbackup")
            with mock.patch.dict(os.environ, {"KEMPERRIG_LIBRARY": "/nope/missing"}):
                self.assertEqual(main(["summary", good]), 0)

    def test_criteria_comes_from_the_environment(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict(os.environ, {"KEMPERRIG_CRITERIA": _CRITERIA}):
                self.assertEqual(main(["shortlist", _lib(d)]), 0)

    def test_missing_library_is_a_clean_usage_error(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KEMPERRIG_LIBRARY", None)
            with self.assertRaises(SystemExit) as cm:
                main(["summary"])
            self.assertEqual(cm.exception.code, 2)


class CliPolishTest(unittest.TestCase):
    """Small contracts a user notices: the program name, the error prefix, an empty env var."""

    def _err(self, argv) -> tuple[int, str]:
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = main(argv)
        return rc, err.getvalue()

    def test_program_name_is_kemperrig_not_the_module_path(self):
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            with self.assertRaises(SystemExit):
                main(["rigs", "--nope"])
        self.assertIn("usage: kemperrig", err.getvalue())
        self.assertNotIn("__main__", err.getvalue())

    def test_missing_rig_error_carries_the_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            rc, err = self._err(["rig", _lib(d), "Nope"])
            self.assertEqual(rc, 1)
            self.assertTrue(err.startswith("kemperrig: "), err)

    def test_rename_refusal_carries_the_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            p = _lib(d)
            rc, err = self._err(["rename", p, "A", "B", "-o", p])
            self.assertEqual(rc, 2)
            self.assertTrue(err.startswith("kemperrig: "), err)

    def test_an_empty_library_env_var_counts_as_unset(self):
        with mock.patch.dict(os.environ, {"KEMPERRIG_LIBRARY": "   "}):
            with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                with self.assertRaises(SystemExit) as cm:
                    main(["summary"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("KEMPERRIG_LIBRARY is not set", err.getvalue())

    def test_a_blank_source_is_named_as_blank_when_the_library_is_set(self):
        """The variable is set; saying it is not would send the user to the wrong place."""
        with tempfile.TemporaryDirectory() as d:
            for argv, expected in ((["summary", "   "], "SOURCE is blank"),
                                   (["pack", "x.rigpack", "--against", "  "],
                                    "--against LIBRARY is blank")):
                with self.subTest(argv=argv), \
                        mock.patch.dict(os.environ, {"KEMPERRIG_LIBRARY": _lib(d)}), \
                        mock.patch("sys.stderr", new_callable=io.StringIO) as err, \
                        self.assertRaises(SystemExit) as cm:
                    main(argv)
                self.assertEqual(cm.exception.code, 2)
                self.assertIn(expected, err.getvalue())
                self.assertNotIn("not set", err.getvalue())


class RigDisambiguationTest(unittest.TestCase):
    """Duplicate rig names across folders are real; `rig` must not pick one silently."""

    def _lib2(self, d: str) -> str:
        return build_rmbackup(
            os.path.join(d, "L.rmbackup"),
            rigs=[{"name": "Crunch", "folder": "Guitar/A", "gain": "3.0"},
                  {"name": "Crunch", "folder": "Guitar/B", "gain": "8.0"}])

    def test_an_ambiguous_name_is_an_error_not_a_silent_pick(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                rc = main(["rig", self._lib2(d), "Crunch"])
            self.assertEqual(rc, 1)
            self.assertIn("--folder", err.getvalue())

    def test_folder_disambiguates(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["rig", self._lib2(d), "Crunch", "--folder", "Guitar/B"]), 0)

    def test_a_unique_name_needs_no_folder(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["rig", _lib(d), "A"]), 0)


class EntryPointTest(unittest.TestCase):
    """The three ways to start the CLI reach the same `main`, under the same program name."""

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", *argv],
                              capture_output=True, text=True, check=False)

    def test_python_dash_m_kemperrig_cli(self):
        done = self._run("kemperrig.cli", "--help")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.startswith("usage: kemperrig "), done.stdout)

    def test_python_dash_m_kemperrig(self):
        done = self._run("kemperrig", "--version")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, f"kemperrig {__version__}"))

    def test_console_script_is_main(self):
        (ep,) = entry_points(group="console_scripts", name="kemperrig")
        self.assertIs(ep.load(), main)


if __name__ == "__main__":
    unittest.main()


def _help(*argv: str) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.suppress(SystemExit):
        main([*argv, "--help"])
    return out.getvalue()


_CLI = Path(__file__).resolve().parents[1] / "src" / "kemperrig" / "cli"
_READ = sorted({v for f in _CLI.glob("*.py")
                for v in re.findall(r'"(KEMPERRIG_[A-Z_]+)"', f.read_text())})
_TAKES_A_LIBRARY = ("summary", "rigs", "analyze", "doctor", "presets", "rig", "pages",
                    "shortlist", "performances", "rename", "extract", "pack", "history")


class HelpTextTest(unittest.TestCase):
    def test_the_cli_reads_the_variables_this_test_expects(self):
        self.assertIn("KEMPERRIG_LIBRARY", _READ)
        self.assertIn("KEMPERRIG_STOMPS_XML", _READ)

    def test_the_top_level_help_names_every_variable(self):
        top = _help()
        for name in [*_READ, "KEMPERRIG_GOLDEN"]:
            with self.subTest(name=name):
                self.assertIn(name, top)

    def test_every_command_that_takes_a_library_names_its_default(self):
        for cmd in _TAKES_A_LIBRARY:
            with self.subTest(cmd=cmd):
                self.assertIn("KEMPERRIG_LIBRARY", _help(cmd))

    def test_no_help_points_into_the_test_suite(self):
        for cmd in ("", *_TAKES_A_LIBRARY, "diff"):
            with self.subTest(cmd=cmd or "top"):
                self.assertNotIn("tests/", _help(*([cmd] if cmd else [])))
