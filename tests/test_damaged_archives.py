"""Archives damaged below the database: a broken compressed stream, an entry flagged
encrypted or packed some unknown way, one that would inflate past anything a library holds.
Each is a one-line error naming the entry, never a traceback, and `history` skips it."""

import io
import json
import os
import struct
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from _fixture import sample_library

from kemperrig.cli import main

_DB = "Local Library/Guitar/Test/Amp/repositoryR2.db"   # where sample_library files its rig


def _rezip(src: str, dst: str, method: int) -> str:
    """`src` written again with its db entry compressed by `method`."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            zout.writestr(info.filename, zin.read(info),
                          compress_type=method if info.filename == _DB else zipfile.ZIP_STORED)
    return dst


def _data_offset(path: str) -> int:
    with zipfile.ZipFile(path) as zf:
        start = zf.getinfo(_DB).header_offset
    name_len, extra_len = struct.unpack_from("<HH", Path(path).read_bytes(), start + 26)
    return start + 30 + name_len + extra_len


def _central(path: str) -> int:
    """Offset of the db entry's central-directory record."""
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(path) as zf:
        pos = zf.start_dir
    while raw[pos:pos + 4] == b"PK\x01\x02":
        name_len, extra_len, comment_len = struct.unpack_from("<HHH", raw, pos + 28)
        if raw[pos + 46:pos + 46 + name_len] == _DB.encode():
            return pos
        pos += 46 + name_len + extra_len + comment_len
    raise LookupError(_DB)


def _patch(path: str, offset: int, fmt: str, value: int) -> None:
    raw = bytearray(Path(path).read_bytes())
    struct.pack_into(fmt, raw, offset, value)
    Path(path).write_bytes(raw)


def _damaged(d: str, how: str) -> str:
    good = sample_library(d, "good.rmbackup")
    p = os.path.join(d, f"{how}.rmbackup")
    if how == "deflate":
        _rezip(good, p, zipfile.ZIP_DEFLATED)
        _patch(p, _data_offset(p), "<B", 0x07)          # a final block of the reserved type
    elif how == "lzma":
        _rezip(good, p, zipfile.ZIP_LZMA)
        _patch(p, _data_offset(p) + 4, "<B", 0xFF)      # properties out of range
    elif how == "encrypted":
        _rezip(good, p, zipfile.ZIP_DEFLATED)
        _patch(p, _central(p) + 8, "<H", 0x0001)
    elif how == "method":
        _rezip(good, p, zipfile.ZIP_DEFLATED)
        _patch(p, _central(p) + 10, "<H", 99)
    elif how == "huge":
        _rezip(good, p, zipfile.ZIP_DEFLATED)
        _patch(p, _central(p) + 24, "<I", 2 ** 31)      # declares 2 GiB unpacked
    elif how == "ratio":
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_DB, b"SQLite format 3\x00" + bytes(17 << 20))
    return p


_DAMAGE = ("deflate", "lzma", "encrypted", "method", "huge", "ratio")


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class DamagedEntryTest(unittest.TestCase):
    def test_each_damage_is_one_line_naming_the_entry_and_the_archive(self):
        for how in _DAMAGE:
            with self.subTest(how=how), tempfile.TemporaryDirectory() as d:
                p = _damaged(d, how)
                code, _, err = _run(["summary", p])
                self.assertEqual(code, 1)
                self.assertEqual(len(err.strip().splitlines()), 1, err)
                self.assertIn(f"{_DB} in {p}", err)

    def test_oversized_entries_are_refused_before_they_are_inflated(self):
        for how in ("huge", "ratio"):
            with self.subTest(how=how), tempfile.TemporaryDirectory() as d:
                self.assertIn("refusing to inflate", _run(["summary", _damaged(d, how)])[2])

    def test_an_encrypted_entry_is_called_encrypted(self):
        with tempfile.TemporaryDirectory() as d:
            err = _run(["summary", _damaged(d, "encrypted")])[2]
            self.assertIn("encrypted", err)
            self.assertNotIn("ZipInfo", err)

    def test_history_skips_a_damaged_backup_and_reads_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            _damaged(d, "deflate")
            code, out, err = _run(["history", d, "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["files"], 1)
            self.assertIn("skipped deflate.rmbackup", err)

    def test_rename_of_a_damaged_source_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            p = _damaged(d, "deflate")
            out = os.path.join(d, "out.rmbackup")
            code, _, err = _run(["rename", p, "A", "B", "-o", out])
            self.assertEqual(code, 1)
            self.assertEqual(len(err.strip().splitlines()), 1, err)
            self.assertFalse(os.path.exists(out))


class NamedFailureTest(unittest.TestCase):
    """With two sources on the line, the message has to say which one failed."""

    def test_a_file_that_is_not_a_zip_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            good = sample_library(d, "good.rmbackup")
            bad = os.path.join(d, "bad.rmbackup")
            Path(bad).write_text("not a zip")
            code, _, err = _run(["diff", good, bad])
            self.assertEqual(code, 1)
            self.assertIn(bad, err)

    def test_a_malformed_info_xml_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            good = sample_library(d, "good.rmbackup")
            bad = os.path.join(d, "bad.rmbackup")
            with zipfile.ZipFile(good) as zin, zipfile.ZipFile(bad, "w") as zout:
                for info in zin.infolist():
                    data = b"<info><db" if info.filename == "info.xml" else zin.read(info)
                    zout.writestr(info.filename, data)
            code, _, err = _run(["diff", good, bad])
            self.assertEqual(code, 1)
            self.assertIn(f"info.xml in {bad}", err)


if __name__ == "__main__":
    unittest.main()
