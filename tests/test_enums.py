"""Effect-type names resolved from Rig Manager's own table, with a verified fallback.

The names are Kemper's, so they are never vendored — they are read at runtime from the
user's own install. Every test here therefore builds its own XML rather than depending on
Rig Manager being present.
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from _fixture import build_rmbackup
from _payloads import make_blob, module_msg, rig_track

import kemperrig
from kemperrig import _enums
from kemperrig.cli import main
from kemperrig.services.decode import rig_detail

_XML = """<?xml version="1.0" encoding="iso-8859-1"?>
<logic><domain id="d"><group id="Effects"><group id="StompEffects">
  <list id="Types" imax="1" vmax="193">
    <entry value="0">- empty -</entry>
    <entry value="33">Green Scream</entry>
    <entry value="49">Compressor</entry>
    <entry value="177">Legacy Reverb</entry>
    <entry value="193">Spring Reverb</entry>
  </list>
  <list id="CategoryList" imax="1" vmax="193">
    <entry value="0">-</entry>
    <entry value="33">Distortion</entry>
    <entry value="49">Compressor</entry>
    <entry value="177">Reverb</entry>
    <entry value="193">Reverb</entry>
  </list>
  <list id="legacyreverbtypelist" imax="5" vmax="5">
    <entry>Hall</entry>
    <entry>Large Room</entry>
    <entry>Small Room</entry>
  </list>
</group></group></domain></logic>
"""


def _xml(d: str, body: str = _XML) -> str:
    p = os.path.join(d, "Stomps.xml")
    Path(p).write_text(body, encoding="iso-8859-1")
    return p


class LoadTest(unittest.TestCase):
    def test_reads_the_three_lists(self):
        with tempfile.TemporaryDirectory() as d:
            t = _enums.load(_xml(d))
            self.assertEqual(t.types[33], "Green Scream")
            self.assertEqual(t.categories[177], "Reverb")
            self.assertEqual(t.legacy_reverb[1], "Large Room")

    def test_the_legacy_list_is_index_based_not_value_based(self):
        """Its entries carry no value attribute, so position is the value."""
        with tempfile.TemporaryDirectory() as d:
            t = _enums.load(_xml(d))
            self.assertEqual(t.legacy_reverb[0], "Hall")
            self.assertEqual(t.legacy_reverb[2], "Small Room")

    def test_latin1_names_survive(self):
        body = _XML.replace("Green Scream", "Fuzz Frisör")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_enums.load(_xml(d, body)).types[33], "Fuzz Frisör")

    def test_a_missing_file_falls_back_rather_than_raising(self):
        t = _enums.load("/nope/Stomps.xml")
        self.assertEqual(t.types[33], "Green Scream")   # from the built-in verified set
        self.assertEqual(t.legacy_reverb, {})

    def test_malformed_xml_falls_back(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_enums.load(_xml(d, "<broken")).types, _enums.FALLBACK_TYPES)

    def test_the_fallback_only_holds_independently_verified_entries(self):
        """Each was confirmed by pairing a preset's blob against its own metadata name."""
        self.assertEqual(len(_enums.FALLBACK_TYPES), 12)


class InstallTest(unittest.TestCase):
    def tearDown(self):
        _enums.install(None)

    def test_install_replaces_the_active_table(self):
        with tempfile.TemporaryDirectory() as d:
            _enums.install(_xml(d))
            self.assertEqual(_enums.tables().types[49], "Compressor")

    def test_without_install_the_fallback_is_active(self):
        _enums.install(None)
        self.assertEqual(_enums.tables().types, _enums.FALLBACK_TYPES)

    def test_install_none_after_a_load_reverts(self):
        with tempfile.TemporaryDirectory() as d:
            _enums.install(_xml(d))
            _enums.install(None)
            self.assertNotIn(49, _enums.tables().types)


class PublicApiTest(unittest.TestCase):
    """A library user names effects through the package, never the private module."""

    def tearDown(self):
        kemperrig.use_effect_names(None)

    def test_names_come_from_the_file_given(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(kemperrig.use_effect_names(_xml(d)), 5)
            blob = make_blob([rig_track("R") + [module_msg(0x32, [49, 0, 0, 1])]])
            path = build_rmbackup(os.path.join(d, "t.rmbackup"), rigs=[{"name": "R", "blob": blob}])
            rig = kemperrig.Backup.open(path).rigs[0]
        self.assertEqual([e.type_name for e in rig_detail(rig).effects], ["Compressor"])

    def test_none_or_a_missing_file_leaves_the_built_in_subset(self):
        for path in (None, "/nonexistent/Stomps.xml"):
            with self.subTest(path=path):
                self.assertEqual(kemperrig.use_effect_names(path), len(_enums.FALLBACK_TYPES))

    def test_the_default_is_where_rig_manager_installs_it(self):
        self.assertEqual(kemperrig.DEFAULT_STOMPS_XML, _enums.DEFAULT_PATH)
        self.assertIn("use_effect_names", kemperrig.__all__)


class SuiteIsolationTest(unittest.TestCase):
    """The suite gives the same answers whether or not Rig Manager is installed here."""

    def test_a_cli_run_names_effects_from_the_fallback_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = build_rmbackup(os.path.join(d, "t.rmbackup"), rigs=[
                {"name": "R", "blob": make_blob([rig_track("R") + [module_msg(0x32, [1, 0, 0, 1])]])}])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["rig", path, "R"]), 0)
        self.assertNotIn(1, _enums.FALLBACK_TYPES)
        self.assertIn("A=type 1 on", out.getvalue())


if __name__ == "__main__":
    unittest.main()
