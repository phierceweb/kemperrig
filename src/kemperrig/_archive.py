"""The `.rmbackup` zip: open it and read one entry, so a damaged, encrypted or oversized
entry is a ValueError naming it rather than an exception the CLI does not expect."""

from __future__ import annotations

import lzma
import zipfile
import zlib
from pathlib import Path

# Library dbs deflate at most about 20:1 and zero-filled pages about 1000:1, so an entry that
# inflates past 100:1 beyond 16 MiB, or past 1 GiB at all, is refused before it is read.
_MAX_ENTRY_BYTES = 1 << 30
_MAX_RATIO = 100
_RATIO_FLOOR = 16 << 20
_ENCRYPTED = 0x1   # general-purpose flag bit 0
# What zipfile raises for a damaged stream, an encrypted entry or an unknown method.
_ENTRY_ERRORS = (zipfile.BadZipFile, zlib.error, lzma.LZMAError, EOFError,
                 NotImplementedError, RuntimeError)


def open_zip(path: str | Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        raise ValueError(f"{path}: not a readable .rmbackup ({e})") from e


def read_entry(zf: zipfile.ZipFile, entry: str | zipfile.ZipInfo, archive: str | Path) -> bytes:
    info = entry if isinstance(entry, zipfile.ZipInfo) else zf.getinfo(entry)
    where = f"{info.filename} in {archive}"
    size, packed = info.file_size, max(info.compress_size, 1)
    if size > _MAX_ENTRY_BYTES or (size > _RATIO_FLOOR and size / packed > _MAX_RATIO):
        raise ValueError(f"{where}: refusing to inflate {packed} bytes to {size} — no Rig "
                         "Manager database is that large or that compressible")
    if info.flag_bits & _ENCRYPTED:
        raise ValueError(f"{where}: encrypted — Rig Manager does not encrypt its backups")
    try:
        return zf.read(info)
    except _ENTRY_ERRORS as e:
        raise ValueError(f"{where}: unreadable entry ({e})") from e
