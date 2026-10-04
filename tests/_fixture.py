"""Build hermetic synthetic `.rmbackup` archives and dated snapshots for tests, from the
payloads `_payloads.py` builds. Only the columns the model reads are created, and nothing
comes from a real library — commercial profiles never enter the repo."""

from __future__ import annotations

import io
import os
import sqlite3
import tempfile
import zipfile

from _payloads import PERF_SLOTS

RIG_FIELDS = [
    "Filename", "Name", "Date", "Author", "Comment", "Gain", "Amp Model", "Amp Name",
    "Amp Comment", "Amp Channel", "Source Amp", "Amp Model Year", "Amp Location", "Amp Pickup",
    "Cabinet Name", "Mic Type", "Mic Position", "Speaker Manufacturer", "Speaker Model",
    "Profile Type", "Profile Revision", "Cabinet Type", "Cabinet Configuration",
]


def _rigs_ddl(fields: list[str]) -> str:
    cols = ", ".join(f'"{f}" TEXT' for f in fields)
    return f'CREATE TABLE "Rigs" (id INTEGER PRIMARY KEY, {cols})'


RIGS_DDL = _rigs_ddl(RIG_FIELDS)

PERF_DDL = """CREATE TABLE "Performances" (
  id INTEGER PRIMARY KEY, Filename TEXT, "Name" TEXT, "Tempo" TEXT,
  {slotcols})"""
_SLOT_KINDS = ["Name", "Enable", "RigName", "AmpName", "CabName"]


def _perf_ddl() -> str:
    cols = []
    for n in range(1, PERF_SLOTS + 1):
        for kind in _SLOT_KINDS:
            cols.append(f'"Slot{n}{kind}" TEXT')
    return PERF_DDL.format(slotcols=", ".join(cols))


def _fill(con: sqlite3.Connection, ddl: str, blob_table: str, insert_cols: list[str],
          rows: list[dict]) -> None:
    """Create one metadata table and its blob table, and insert `rows` into both."""
    con.execute(ddl)
    con.execute(f'CREATE TABLE "{blob_table}" (id INTEGER PRIMARY KEY, data BLOB)')
    placeholders = ", ".join("?" for _ in insert_cols)
    colnames = ", ".join(f'"{c}"' for c in insert_cols)
    for i, row in enumerate(rows, 1):
        con.execute(
            f'INSERT INTO "{ddl_table(ddl)}" (id, {colnames}) VALUES (?, {placeholders})',
            [i, *[row.get(c) for c in insert_cols]],
        )
        con.execute(f'INSERT INTO "{blob_table}" (id, data) VALUES (?, ?)',
                    [i, row.get("_blob", b"")])


def _db_bytes(ddl: str, blob_table: str, insert_cols: list[str], rows: list[dict]) -> bytes:
    """Build a one-table+blob SQLite db and return its raw bytes."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        con = sqlite3.connect(path)
        _fill(con, ddl, blob_table, insert_cols, rows)
        con.commit()
        con.close()
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(path)


def ddl_table(ddl: str) -> str:
    """Pull the table name out of a CREATE TABLE statement."""
    return ddl.split('"', 2)[1]


PRESET_DDL = """CREATE TABLE "Presets" (
  id INTEGER PRIMARY KEY, Filename TEXT, "Name" TEXT, "Preset Class" TEXT,
  "Preset Category" TEXT, "Preset Type" TEXT)"""
PRESET_FIELDS = ["Filename", "Name", "Preset Class", "Preset Category", "Preset Type"]


def _preset_row(p: dict) -> dict:
    return {"Filename": p.get("filename") or f"{p['name']}.kcab", "Name": p["name"],
            "Preset Class": p.get("preset_class"), "Preset Category": p.get("preset_category"),
            "Preset Type": p.get("preset_type"), "_blob": p.get("blob", b"")}


def _perf_insert_cols(performances: list[dict]) -> list[str]:
    cols = ["Filename", "Name", "Tempo"]
    for n in range(1, PERF_SLOTS + 1):
        for kind in _SLOT_KINDS:
            cols.append(f"Slot{n}{kind}")
    return cols


def _perf_row(perf: dict) -> dict:
    row = {"Filename": perf.get("filename") or f"{perf['name']}.kperformance",
           "Name": perf["name"], "Tempo": perf.get("tempo", "7680")}
    for n, slot in enumerate(perf.get("slots", []), 1):
        row[f"Slot{n}Name"] = slot.get("name")
        row[f"Slot{n}Enable"] = slot.get("enable", "1")
        row[f"Slot{n}RigName"] = slot.get("rig_name")
        row[f"Slot{n}AmpName"] = slot.get("amp_name")
        row[f"Slot{n}CabName"] = slot.get("cab_name")
    row["_blob"] = perf.get("blob", b"")
    return row


def _rig_row(rig: dict) -> dict:
    return {
        "Filename": rig.get("filename") or f"{rig['name']}.krig",
        "Name": rig["name"], "Date": rig.get("date"), "Author": rig.get("author"),
        "Comment": rig.get("comment"), "Gain": rig.get("gain"),
        "Amp Model": rig.get("amp_model"), "Amp Name": rig.get("amp_name"),
        "Amp Comment": rig.get("amp_comment"), "Amp Channel": rig.get("amp_channel"),
        "Source Amp": rig.get("source_amp"), "Amp Model Year": rig.get("amp_model_year"),
        "Amp Location": rig.get("amp_location"), "Amp Pickup": rig.get("amp_pickup"),
        "Cabinet Name": rig.get("cabinet_name", "N/A"),
        "Mic Type": rig.get("mic_type", "N/A"), "Mic Position": rig.get("mic_position", "N/A"),
        "Speaker Manufacturer": rig.get("speaker_manufacturer", "N/A"),
        "Speaker Model": rig.get("speaker_model", "N/A"),
        "Profile Type": rig.get("profile_type", "1"),
        "Profile Revision": rig.get("profile_revision", "0"),
        "Cabinet Type": rig.get("cabinet_type", "0"),
        "Cabinet Configuration": rig.get("cabinet_configuration", "N/A"),
        "_blob": rig.get("blob", b""),
    }


def build_rmbackup(dest: str, *, rigs: list[dict], performances: list[dict] | None = None,
                   presets: list[dict] | None = None,
                   omit_rig_columns: tuple[str, ...] = (),
                   version: str = "1.6.0", user: str = "Test User") -> str:
    """Write a synthetic `.rmbackup` to `dest`.

    Each rig dict needs `name`; optional `author/gain/amp_model/cabinet_name/profile_type/folder/blob`.
    `folder` is the library path (default 'Guitar/Test/Amp'); rigs are grouped into one db per folder.
    `omit_rig_columns` drops `Rigs` columns, modelling a db from an older Rig Manager.
    """
    rig_fields = [f for f in RIG_FIELDS if f not in omit_rig_columns]
    by_folder: dict[str, list[dict]] = {}
    for rig in rigs:
        by_folder.setdefault(rig.get("folder", "Guitar/Test/Amp"), []).append(rig)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Faithful to reality: Kemper writes a malformed declaration (`UTF - 8`, spaces around
        # the hyphen) that strict XML parsers reject — the model must tolerate it.
        zf.writestr("info.xml",
                    f'<?xml version="1.0" encoding="UTF - 8"?>\n<info>\n <db version="{version}"/>\n'
                    f' <user name="{user}"/>\n</info>\n')
        for folder, folder_rigs in by_folder.items():
            data = _db_bytes(_rigs_ddl(rig_fields), "Rigs_blobs", rig_fields,
                             [_rig_row(r) for r in folder_rigs])
            zf.writestr(f"Local Library/{folder}/repositoryR2.db", data)
        if performances:
            data = _db_bytes(_perf_ddl(), "Performances_blobs", _perf_insert_cols(performances),
                             [_perf_row(p) for p in performances])
            zf.writestr("Prf/Local Library/repositoryR2.db", data)
        if presets:
            data = _db_bytes(PRESET_DDL, "Presets_blobs", PRESET_FIELDS,
                             [_preset_row(p) for p in presets])
            zf.writestr("Prst/Local Library/repositoryR2.db", data)
    with open(dest, "wb") as fh:
        fh.write(buf.getvalue())
    return dest


# A snapshot's Rigs table has no profile-type columns; KPAID is extra and unread.
SNAPSHOT_RIG_FIELDS = [f for f in RIG_FIELDS
                       if f not in ("Profile Type", "Profile Revision")] + ["KPAID"]
SNAPSHOT_TABLES = ("Rigs", "Performances", "Presets", "ROMPresets")


def build_snapshot(dest: str, *, rigs: list[dict] = (), performances: list[dict] = (),
                   presets: list[dict] = (), rom_presets: list[dict] = (),
                   omit_tables: tuple[str, ...] = ()) -> str:
    """Write a synthetic dated snapshot to `dest`: one bare SQLite db holding every table,
    as Rig Manager keeps them under `Backups/`. Rigs carry no folder."""
    if os.path.exists(dest):
        os.unlink(dest)
    con = sqlite3.connect(dest)
    tables = {
        "Rigs": (_rigs_ddl(SNAPSHOT_RIG_FIELDS), SNAPSHOT_RIG_FIELDS,
                 [_rig_row(r) for r in rigs]),
        "Performances": (_perf_ddl(), _perf_insert_cols([]), [_perf_row(p) for p in performances]),
        "Presets": (PRESET_DDL, PRESET_FIELDS, [_preset_row(p) for p in presets]),
        "ROMPresets": (PRESET_DDL.replace('"Presets"', '"ROMPresets"'), PRESET_FIELDS,
                       [_preset_row(p) for p in rom_presets]),
    }
    for name in SNAPSHOT_TABLES:
        if name not in omit_tables:
            ddl, cols, rows = tables[name]
            _fill(con, ddl, f"{name}_blobs", cols, rows)
    con.execute('CREATE TABLE "Device/Rigs_viewproperties" (id INTEGER PRIMARY KEY, '
                'key TEXT, val TEXT)')
    con.commit()
    con.close()
    return dest


def sample_library(d: str, name: str = "Lib.rmbackup") -> str:
    """One-rig archive at `d/name` — the stand-in whenever a test just needs a real library."""
    return build_rmbackup(
        os.path.join(d, name),
        rigs=[{"name": "A", "gain": "5.0", "amp_model": "Dual Rectifier",
               "cabinet_name": "N/A"}])
