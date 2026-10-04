# The `.rmbackup` format

How Rig Manager stores a library — the container, its SQLite tables, snapshots and packs,
and the SysEx framing inside every rig and performance payload — as far as it has been
established from real files.

There is no vendor specification for the container or its SysEx framing: everything here was
recovered by inspecting files Rig Manager wrote. The module page numbers come from Kemper's
published *MIDI Parameter Documentation*. A value that could not be established decodes to
`None` rather than a guess.

For AI assistants: the `kemper-rmbackup` skill covers the traps in this format in a
condensed form suited for decode work.

---

## Table of Contents

- [The container](#the-container)
- [Dated snapshots](#dated-snapshots)
- [Rig and preset packs](#rig-and-preset-packs)
- [Rig and performance blobs](#rig-and-performance-blobs)
- [Performance payloads](#performance-payloads)
- [Raw blocks — kemperrig pages](#raw-blocks--kemperrig-pages)
- [Adding a decode](#adding-a-decode)

## The container

A `.rmbackup` is a **ZIP** holding `info.xml` plus one SQLite database per library folder:

| Path in the archive | Holds |
|---|---|
| `Local Library/<folder>/repositoryR2.db` | `Rigs` (metadata) + `Rigs_blobs` (payloads) |
| `Prf/Local Library/repositoryR2.db` | `Performances` — the 5 slots are columns — + blobs |
| `Prst/…/repositoryR2.db` | `Presets` — effect modules and cab IRs |

The **live Rig Manager directory** (`~/Library/Application Support/Kemper Amps/RigManager`)
is the same layout unzipped, which is why every command accepts either.

Each database is read straight from the archive into an in-memory connection via
`sqlite3.deserialize` — nothing is extracted to a temp file.

`Preset Class` distinguishes preset kinds: `6` = cabinet IR, `3` = effect module.

Several `Rigs` columns are exposed raw, uninterpreted:

- `Profile Type`, one number per profile generation. It does not pick the amp-block shape
  the gain decode below reads.
- `Profile Revision`.
- `Cabinet Type` (`0`–`3`) is **not a DI flag**: DI-cab rigs occur under more than one
  value, and one value holds both DI rigs and rigs with a real merged cab. DI vs studio is
  read from `Cabinet Name` being empty, `N/A` or `DIRECT`.
- `Cabinet Configuration` is free text (`4x12`, `4*12`, `2 x 12`, `N/A`, …).

Older databases may lack these columns; they read as `None`.

Amp metadata that matters lives in free-text columns — `Amp Comment` carries boost/drive
notes (pedal names, "Unboosted"), so boost state is inferred from tokens rather than read
from a flag, and is `None` when the text says nothing about drive.

## Dated snapshots

Inside the live directory, `Backups/` holds dated snapshots named
`<device id> - YYYY-MM-DD HH-MM-SSR2.db`. Each is **one bare SQLite database**, not a zip,
holding every table at once:

| Table | Holds |
|---|---|
| `Rigs` + `Rigs_blobs` | rig metadata and payloads, as in a library folder |
| `Performances` + `Performances_blobs` | performances, the 5 slots as columns |
| `Presets` + `Presets_blobs` | effect and cab-IR presets |
| `ROMPresets` + `ROMPresets_blobs` | factory effect presets |

plus per-view preference tables (`<name>/Rigs_viewproperties` and the like). A snapshot is
told apart from a `.rmbackup` by its 16-byte SQLite header (`SQLite format 3\0`), never by
its name, and a SQLite file lacking `Rigs`, `Performances` or `Presets` is refused rather
than read as an empty library.

How it differs from the library tree:

- **No folders.** Rigs and presets are not filed, so they read with an empty folder. `diff`
  keys rigs and presets by folder and name, so against a `.rmbackup` or the live directory
  they never align; performances, keyed by name, do.
- `Rigs` has no `Profile Type` or `Profile Revision` column (both read as `None`) and an
  extra `KPAID` column; `Performances` has an extra `ProgNr`. Neither extra is read.
- `ROMPresets` rows are all class `3`, identical from snapshot to snapshot until the set
  grows in a later one, and never overlap the user's presets. They are not read.
- A snapshot can hold no rows at all.

One `Backups/` folder can hold snapshots under several device ids, interleaved in time and
with different content under each, so snapshots are only comparable with others carrying
the same id. The date-time in a snapshot's name — and in a `.rmbackup` name Rig Manager
wrote, `YYYY-MM-DD HH-MM-SS - <user>.rmbackup` — is local time with dashes for colons.

## Rig and preset packs

`Rig Packs/*.rigpack` and `Preset Packs/*.presetpack` in the live directory are each **one
bare SQLite database**, not a zip, with the same tables whichever they carry:

| Table | Holds |
|---|---|
| `packs` | one row: `name`, `author` (the vendor), `copyright`, `releasedate` (`YYYYMMDDHHMMSS`), `minversion`, GUIDs, a signature |
| `properties` | key/value pairs; `Content` is `Rigs` or `Presets` |
| `rigs` | one row per rig — or per preset, in a preset pack: `name`, `author`, `createdate`, `comment`, `rig_id` |
| `rigdata` | the payloads, joined on `rigs.rig_id = rigdata.id` |
| `texts`, `images`, `packupdates` | description, artwork, update chain — not read |

There is no version column: `minversion` is a minimum and `releasedate` the release stamp.
A pack is told apart from a snapshot by its tables, and `Content` — not the file extension —
decides whether its rows are rigs or presets. A file with more than one `packs` row, or any
other `Content`, is refused.

A payload is stored as a **bare track body**: the `00 F0 …` events with no header or chunk.
Wrapped in the header every stored rig carries (`KThd`, length 6, `00 00 00 01 01 e0`) and
one `KTrk` chunk, it is byte-identical to the blob Rig Manager stores for that rig or preset
— wherever a pack payload also turns up in a library or a snapshot, the wrapped form matches
the stored blob exactly. So a pack rig reads, compares and extracts like a library rig.

The `rigs` table has no amp, gain or cab columns, and its `comment` holds an instrument
category (`Guitar`, `Bass`, …) rather than the rig comment. Those fields are read from the
payload instead, through the strings the `Rigs` columns mirror (see *Strings* below), and the
gain is the decoded amp gain rounded to the one decimal the `Gain` column stores. DI vs
studio follows from the payload's cab name. Pack rigs have no folder, and no
`Profile Type`, `Profile Revision` or `Cabinet Type`.

## Rig and performance blobs

A `.krig` / `.kperformance` blob is a **Standard MIDI File clone**: a `KThd` header chunk
followed by track chunks. The track tag is `KTrk` on most files but plain `MTrk` on some —
both occur in one library, so both are accepted.

A rig blob is exactly a `.krig` file: a vendor-distributed `.krig` is byte-identical to the
blob Rig Manager stores for that rig once imported, which is why `kemperrig extract` writes
blobs out verbatim. Every stored rig blob seen is the 14-byte header `KThd` (or `MThd`),
length 6, `00 00 00 01 01 e0` — one track, 480 ticks — followed by a single track chunk that
runs to the end.

A track is a stream of `<delta varlen> F0 <varlen length> <payload>` events. Each payload is
a Kemper SysEx message beginning with the manufacturer id `00 20 33` and ending at `F7`.

Every blob examined — in libraries, snapshots, packs and published rigs — ends exactly at
the end of its last chunk and holds only `KThd`/`MThd` and `KTrk`/`MTrk` chunks, so a chunk running
past the end, or bytes after the last chunk, mean the payload is damaged. Track bodies are
SysEx events to the last byte, with one exception seen: some slot tracks in a snapshot
performance hold a body that is not an event stream (it opens with an encoded `KThd`).
Nothing here decodes it; parsing stops there, and `doctor` lists such tracks. Parsing stops
the same way at a delta time that runs off the end of its track; an `F0` event whose length
or body runs past the end is damage.

What is decoded:

- **Strings** — payload bytes `[3:6]` equal to `00 00 03` marks a string parameter. This is
  where rig names, author, timestamps, and a loaded cab-IR `.wav` filename live. The next
  three bytes are the string's address, and two addresses are read by it:

  | address | holds | agrees with |
  |---|---|---|
  | `00 00 01` | the rig name — what the Profiler shows | the `Rigs` `Name` column; a slot's `RigName` |
  | `00 00 20` | the name of the loaded cab | a slot's `CabName`; a cab-IR preset carries its own name here |

  The cab's strings run from `0x20` to `0x2e` and are laid out the same in a rig, a slot and
  a cab-IR preset. A user-imported IR has its `.wav` file name among them; factory cabs have
  none.

  A string's value is 7-bit ASCII — no payload byte anywhere is `0x80` or above — ending in
  one `00` with nothing after it. No real rig name is longer than 32 characters. `rename`
  writes a name back by re-encoding that one event (its varlen length, then the chunk
  length) and keeping every other byte.

  More of the `Rigs` columns are copies of a rig's own strings, equal wherever both exist:

  | address | column | address | column |
  |---|---|---|---|
  | `00 00 02` | `Author` | `00 00 18` | `Amp Model` |
  | `00 00 03` | `Date` | `00 00 19` | `Amp Channel` |
  | `00 00 04` | `Comment` | `00 00 1a` | `Amp Pickup` |
  | `00 00 10` | `Amp Name` | `00 00 1b` | `Amp Model Year` |
  | `00 00 14` | `Amp Location` | `00 00 26` | `Mic Type` |
  | `00 00 15` | `Source Amp` | `00 00 28` | `Mic Position` |
  | `00 00 16` | `Amp Comment` | `00 00 29` | `Cabinet Configuration` |
  | `00 00 20` | `Cabinet Name` | `00 00 2c` / `2d` | `Speaker Manufacturer` / `Model` |

  The cab columns describe the rig as it was profiled. Load a cab onto a DI profile later
  and its strings change while the columns keep `N/A` — so in a user's library the two can
  differ; in rigs as their authors published them they agree.
- **Amp gain** — the amp-definition block is page `0x0a` starting at param 0, with a
  14-bit gain value at body offset 14 (param 4 in the function-`02` framing). Full scale is
  `16383 ≙ 10.0`, so `gain = raw / 1638.4`, which agrees with the one-decimal `Gain`
  column. Either byte at `0x80` or above is not SysEx data, so that gain decodes to `null`.
  The block's shape varies by amp-block generation, and every profile type seen
  uses one of these shapes (body length counted from the byte after `00 20 33`):

  | function | body lengths |
  |---|---|
  | `02` (14-bit param pairs) | 36, 40, 50, 54 — 40 is the form most type-1 rigs use |
  | `08` | 74, 94, 102 |

  Any other shape decodes to `None`. `Profile Type` does not pick the shape: type-1 rigs
  occur in several of them.
- **Effect modules** — one page per slot: `0x32`–`0x35` are Stomps A–D, `0x38` is X,
  `0x3a` MOD, `0x3c` DLY. Param 0 is the Type, param 3 the on/off. A slot whose page
  appears only as a function-`08` block (see [Raw blocks](#raw-blocks--kemperrig-pages)) is
  **undecoded**: reported with no type, name or on/off, because its type — and whether it
  holds an effect at all — is unknown. A function-`02` block always decides its slot, an
  empty one (type 0) included.

  The **REV slot has two encodings a firmware generation apart, and they never co-occur** in
  any rig examined. The split is dated: rigs published through 2018 use `0x4b`, 2020 onward
  use `0x3d`, with 2019 the crossover.

  | page | era | what the value means |
  |---|---|---|
  | `0x3d` | 2019 → | a Type on the same global enum as every other slot |
  | `0x4b` | → 2018 | a room size on its own index-based list, *not* a Type |

  Naming `0x4b` from the global enum reports value 1 as "Wah Wah". Type names are not
  hard-coded: they are read at runtime from the `Stomps.xml` inside the Rig Manager app
  bundle, falling back to a small independently verified set. Unlisted values render as
  their raw number.

Numeric knob values buried inside module blocks beyond the amp gain are **not** decoded.

Pages `0x04`, `0x09`, `0x0b` and `0x0c` occur in every rig (in some only in the function-`08`
framing), `0x76` in most and `0x4a` in some; none
is read. Their meaning is unestablished; they are listed here so nobody rediscovers them as
findings. Page `0x04` carries several blocks at different start numbers.

## Performance payloads

A performance blob is a header track followed by one track per slot — six tracks in every
performance seen, all of which used all five slots — and each slot track is
a whole rig: a slot holds its own copy of the rig it was built from, which the Profiler lets
you edit apart from the original. `RigName` and `CabName` mirror the names inside that copy
(addresses `00 00 01` and `00 00 20`). They record where the slot came from; the slot plays
its own copy.

## Raw blocks — `kemperrig pages`

A multi-parameter block is a message whose body starts `00 00 02 00`, followed by the page,
the start number, and 14-bit values as 7-bit pairs. `kemperrig pages RIG` prints each block
keyed by (page, start number) with its raw values, and `kemperrig pages --all` counts, per
page, how many rigs carry it, its start numbers and its lengths. Only the pages decoded
above are named; every other page prints as bare hex.

Messages in other framings are listed by their first six body bytes and length, undecoded:

- `00 00 04 00 …` — long binary messages at several start numbers.
- `02 00 06 00 00 00` — a different header altogether, several per rig.
- `00 00 08 00 <page> <start>` — function `08`, which carries stomp, reverb and amp pages
  in some rigs instead of function `02`. Only the amp gain is read from it (see the amp block table). An effect slot found only in
  this framing is reported as undecoded (`decoded: false`, `SLOT=?`), never as empty.

## Adding a decode

1. **Find it in a real file first.** `kemperrig pages RIG` and `pages --all` show the raw
   blocks; a differential save — one known parameter changed in Rig Manager, everything else
   the same — is the strongest evidence. A plausible-looking offset is not a finding.
2. **Decode in the domain modules only**: `_sysex.py` for framing and strings,
   `_sysex_effects.py` for module blocks, `_tables.py` / `_packs.py` for rows. Return `None`
   for anything not established; never fall back to a neighbouring enum or a default.
3. **Build the bytes in the fixtures**: extend `tests/_payloads.py` so the test writes the
   exact bytes the decode reads, and add the case to `tests/_sample.py` when a command
   should show it.
4. **Record it here**, with what it agrees with in Rig Manager — and in the skill, if it is
   a trap.
5. **Check a real library**: with `KEMPERRIG_GOLDEN` and `KEMPERRIG_LIBRARY` set, the golden
   test shows what moved ([census.md](census.md)); regenerate the census only for an
   intended change.
