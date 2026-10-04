"""Build a synthetic Rig Manager pack (`.rigpack` / `.presetpack`) for tests.

A pack is one bare SQLite db with the pack tables; each rig or preset payload is stored as a
bare track body, without the header and chunk a stored rig carries.
"""

from __future__ import annotations

import os
import sqlite3

from _payloads import _track_body, amp_msg, string_msg

# The one-track header every stored rig carries, then its single `KTrk` chunk.
KRIG_HEADER = b"KThd\x00\x00\x00\x06\x00\x00\x00\x01\x01\xe0"

_DDL = (
    "CREATE TABLE `packupdates` (`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE, "
    "`packguid` TEXT NOT NULL, `oldguid` TEXT NOT NULL)",
    "CREATE TABLE `texts` (`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE, "
    "`packs_id` INTEGER NOT NULL, `lang` TEXT, `short` TEXT, `long` TEXT)",
    "CREATE TABLE `properties` (`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE, "
    "`packs_id` INTEGER NOT NULL, `key` TEXT, `val` TEXT)",
    "CREATE TABLE `images` (`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE, "
    "`packs_id` INTEGER NOT NULL, `sequence` INTEGER, `image` BLOB, `locator` INTEGER, "
    "`description` TEXT)",
    "CREATE TABLE `packs` (`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE, "
    "`name` TEXT NOT NULL, `copyright` TEXT NOT NULL, `author` TEXT NOT NULL, "
    "`releasedate` TEXT NOT NULL, `guid` TEXT NOT NULL, `updateguid` TEXT NOT NULL, "
    "`minversion` TEXT NOT NULL, `signature2` BLOB)",
    "CREATE TABLE `rigs` (`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE, "
    "`packs_id` INTEGER NOT NULL, `name` TEXT, `author` TEXT, `createdate` TEXT, "
    "`comment` TEXT, `rig_id` INTEGER NOT NULL)",
    "CREATE TABLE `rigdata` (`id` INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT UNIQUE, "
    "`rig` BLOB)",
)


def krig(body: bytes) -> bytes:
    """What Rig Manager stores for a rig or preset whose pack payload is `body`."""
    return KRIG_HEADER + b"KTrk" + len(body).to_bytes(4, "big") + body


def rig_body(name: str, *, author: str = "Vendor", gain: float | None = 5.0,
             strings: dict[int, str] | None = None) -> bytes:
    """A pack rig's track body: name, author and date strings, `strings` by address, and an
    amp block carrying `gain`."""
    payloads = [string_msg(name, 0x01), string_msg(author, 0x02),
                string_msg("2020-01-02 03:04:05", 0x03)]
    payloads += [string_msg(text, addr) for addr, text in (strings or {}).items()]
    if gain is not None:
        payloads.append(amp_msg(gain, length=50))
    return _track_body(payloads)


def pack_rig(name: str, *, category: str = "Guitar", **kw) -> dict:
    """A `rigs` row and its payload; `category` is what a pack keeps in `rigs.comment`."""
    return {"name": name, "author": kw.get("author", "Vendor"),
            "createdate": "2020-01-02 03:04:05", "comment": category,
            "body": kw.pop("body", None) or rig_body(name, **kw)}


def build_pack(dest: str, *, name: str = "Test Pack", author: str = "Vendor",
               content: str | None = "Rigs", rigs: list[dict] = (),
               released: str = "20200102030405", extra_packs: int = 0) -> str:
    """Write a synthetic pack to `dest`. `content` None leaves the Content property out;
    `extra_packs` adds more `packs` rows than the one a real pack holds."""
    if os.path.exists(dest):
        os.unlink(dest)
    con = sqlite3.connect(dest)
    for ddl in _DDL:
        con.execute(ddl)
    for n in range(1 + extra_packs):
        con.execute("INSERT INTO packs (name, copyright, author, releasedate, guid, updateguid, "
                    "minversion, signature2) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name if n == 0 else f"{name} {n}", "(c) Vendor", author, released,
                     "{guid}", "{update}", "5.0", b"\x00" * 20))
    props = {"type": "factory", "rm_minversion": "3.0"}
    if content is not None:
        props["Content"] = content
    for key, val in props.items():
        con.execute("INSERT INTO properties (packs_id, key, val) VALUES (1, ?, ?)", (key, val))
    con.execute("INSERT INTO texts (packs_id, lang, short, long) VALUES (1, 'en', '', 'about')")
    for rig in rigs:
        rig_id = con.execute("INSERT INTO rigdata (rig) VALUES (?)",
                             (rig.get("body"),)).lastrowid
        if rig.get("orphan_row"):
            rig_id += 1000
        con.execute("INSERT INTO rigs (packs_id, name, author, createdate, comment, rig_id) "
                    "VALUES (1, ?, ?, ?, ?, ?)",
                    (rig["name"], rig.get("author"), rig.get("createdate"), rig.get("comment"),
                     rig_id))
    con.commit()
    con.close()
    return dest
