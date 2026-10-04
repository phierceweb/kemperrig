"""A `Gain` cell that `float()` reads but that is no gain — NaN, infinities, an overflow —
reads as no gain, so no command crashes on it, emits non-JSON, or lets it pass a filter."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _fixture import build_rmbackup
from _payloads import make_blob, rig_track

from kemperrig import _json
from kemperrig.cli import main
from kemperrig.model import Backup

_NOT_GAINS = ("nan", "inf", "-inf", "1e999")


def _strict(text: str):
    def reject(token):
        raise ValueError(f"{token} is not JSON")
    return json.loads(text, parse_constant=reject)


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


class NonFiniteGainTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        rigs = [{"name": name, "gain": gain, "amp_model": "X", "blob": make_blob([rig_track(name)])}
                for name, gain in [("Real", "5.0"), *((f"Odd {g}", g) for g in _NOT_GAINS)]]
        self.lib = build_rmbackup(os.path.join(self.d, "lib.rmbackup"), rigs=rigs)

    def test_each_reads_as_no_gain(self):
        gains = {r.name: r.gain for r in Backup.open(self.lib).rigs}
        self.assertEqual(gains, {"Real": 5.0, **{f"Odd {g}": None for g in _NOT_GAINS}})

    def test_summary_counts_only_the_real_gain(self):
        code, out, err = _run(["summary", self.lib, "--json"])
        self.assertEqual((code, err), (0, ""))
        gain = _strict(out)["gain"]
        self.assertEqual((gain["min"], gain["max"], gain["bands"]), (5.0, 5.0, {"5": 1}))

    def test_every_json_document_is_strict_json(self):
        for argv in (["rigs"], ["rigs", "--decode"], ["analyze"], ["doctor"], ["performances"],
                     ["rig", "Odd nan"]):
            with self.subTest(argv=argv):
                code, out, _ = _run([argv[0], self.lib, *argv[1:], "--json"])
                self.assertIn(code, (0, 1))
                _strict(out)

    def test_a_gain_filter_does_not_let_them_through(self):
        code, out, _ = _run(["rigs", self.lib, "--gain-min", "0", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual([r["name"] for r in _strict(out)["rigs"]], ["Real"])

    def test_a_backup_diffed_with_itself_is_identical(self):
        self.assertEqual(_run(["diff", self.lib, self.lib])[0], 0)


class JsonOutputRefusesNonFiniteTest(unittest.TestCase):
    def test_dump_raises_rather_than_print_nan(self):
        with redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(ValueError):
                _json.dump({"gain": float("nan")})
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
