"""Names, comments and payload strings come from files other people wrote — a vendor pack, a
shared backup. No control character in them reaches the terminal: the text views and the
one-line errors show it escaped, while `--json` keeps the value as stored."""

import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from _fixture import build_rmbackup
from _pack_fixture import build_pack, pack_rig
from _payloads import make_blob, performance_blob, rig_track, string_msg

from kemperrig import _views
from kemperrig.cli import main

_ESC = "\x1b]0;title\x07\x1b[2J\r\x9b"
_EVIL = f"Evil{_ESC}"
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _run(argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("KEMPERRIG_LIBRARY", None)
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _library(path: str, gain: str) -> str:
    blob = make_blob([rig_track(_EVIL, cab=_EVIL) + [string_msg(f"{_EVIL}.wav", 0x30)]])
    return build_rmbackup(
        path, user="User\x7f\x9b2J",    # XML forbids C0 controls but not DEL or C1
        rigs=[{"name": _EVIL, "folder": f"Guitar/{_EVIL}", "gain": gain, "author": _EVIL,
               "amp_model": _EVIL, "amp_comment": _EVIL, "source_amp": _EVIL, "blob": blob}],
        performances=[{"name": _EVIL, "slots": [{"name": _EVIL, "rig_name": _EVIL}],
                       "blob": performance_blob(rig_track(_EVIL))}],
        presets=[{"name": _EVIL, "preset_class": "6", "preset_type": _EVIL}])


class TextViewsTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.lib = _library(os.path.join(self.d, "a.rmbackup"), "5.0")
        self.other = _library(os.path.join(self.d, "b.rmbackup"), "6.0")
        self.pack = build_pack(os.path.join(self.d, "p.rigpack"), name=_EVIL, author=_EVIL,
                               rigs=[pack_rig(_EVIL, author=_EVIL)])

    def test_no_text_view_prints_a_control_character(self):
        commands = [
            ["summary", self.lib], ["rigs", self.lib, "--decode"], ["rig", self.lib, _EVIL],
            ["presets", self.lib], ["performances", self.lib], ["analyze", self.lib],
            ["doctor", self.lib], ["pages", self.lib, _EVIL], ["pages", self.lib, "--all"],
            ["diff", self.lib, self.other], ["history", self.d, "--rig", _EVIL],
            ["pack", self.pack, "--against", self.lib],
            ["extract", self.lib, "--all", "-o", os.path.join(self.d, "out")],
        ]
        for argv in commands:
            with self.subTest(command=argv[0]):
                _, out, err = _run(argv)
                self.assertEqual(_CONTROL.findall(out + err), [], out)
                if argv[-1] != "--all":    # the page census names no rig
                    self.assertIn(r"Evil\x1b", out)

    def test_json_keeps_the_value_as_stored(self):
        _, out, _ = _run(["rigs", self.lib, "--json"])
        self.assertEqual(json.loads(out)["rigs"][0]["name"], _EVIL)


class ErrorLineTest(unittest.TestCase):
    def test_an_entry_name_in_an_error_is_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.rmbackup")
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr(f"Local Library/{_EVIL}/repositoryR2.db", b"not sqlite")
            code, _, err = _run(["summary", p])
            self.assertEqual(code, 1)
            self.assertEqual(_CONTROL.findall(err.rstrip("\n")), [])
            self.assertIn(r"\x1b", err)


class EveryRendererIsWrappedTest(unittest.TestCase):
    def test_each_exported_renderer_escapes_its_output(self):
        """A renderer exported without the wrapper would print file text raw."""
        renderers = [n for n in _views.__all__ if n.startswith("render_")]
        self.assertTrue(renderers)
        for name in renderers:
            with self.subTest(name=name):
                self.assertIs(getattr(getattr(_views, name), "terminal_safe", False), True)


if __name__ == "__main__":
    unittest.main()
