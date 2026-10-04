---
name: kemper-rmbackup
description: Use when reading, decoding, or troubleshooting a Kemper Rig Manager backup (.rmbackup) or the live Rig Manager library — rig/performance/preset metadata, amp gain, effect chains, cab IRs, or the KThd/KTrk SysEx inside a blob. Covers the format traps that make a naive read give wrong answers.
---

# Kemper `.rmbackup` files

Use `kemperrig` rather than parsing by hand. Every read command takes a `.rmbackup`, the
live directory, a dated snapshot from its `Backups/`, or a rig/preset pack (`Rig Packs/`,
`Preset Packs/`); `history` walks all the snapshots.
Every read command takes `--json`; `rig --json` and `rigs --decode` give a rig's decode
(amp gain, effects, cab IR, strings) as data, and `rigs` / `extract` select with `--effect`
and `--ir` as well as the metadata filters. `pack PACKFILE --against [LIBRARY]` says which
pack items a library already holds (same payload digest).
`extract [SOURCE] -o DIR (--all | rigs filters)` writes rig blobs verbatim as `.krig` files
(a blob *is* the `.krig`; pack rigs are wrapped first) and refuses DIR inside the source or
any Rig Manager tree. `doctor` checks what slots
and payloads point at (dangling/ambiguous slots, broken payloads, name and gain
disagreements, unused cab IRs).
`pages RIG` dumps raw blocks and `pages --all` censuses pages library-wide — start there
when investigating a new decode. `bin/run sample DIR` writes a synthetic library to try any
command on. Reach for this skill when a decoded value looks wrong, or when adding decode
support. The full format reference is `docs/format.md`.

After any decode change, run `bin/run pytest`: with `KEMPERRIG_GOLDEN` and
`KEMPERRIG_LIBRARY` in `.env`, `tests/test_golden.py` compares the real library field by
field with its census (`summary --write-golden`: totals, gain decodes per profile type,
rigs per effect slot, `doctor` counts, a sample rig and performance). A moved field is
either a regression or an intended change — decide which from the diff, then regenerate
the census with `--force`; never relax the test.

## Never read the archive as text

A `.rmbackup` is a ZIP of SQLite databases plus binary SysEx blobs. Opening it in an editor
or `Read`-ing it whole tells you nothing and burns context. Query it:

```bash
kemperrig rigs "<backup>" --json --amp Recto --gain-min 6
kemperrig rig  "<backup>" "<rig name>"      # decode one blob's strings
```

## The traps

- **Two track tags.** Blobs are Standard-MIDI-File clones. Most use `KThd`/`KTrk`, but some
  performances use plain `MThd`/`MTrk`. Code that matches only `KTrk` silently returns no
  tracks — it does not error.
- **The amp block has several shapes.** Gain is the 14-bit value at body offset 14 of the
  page-`0x0a` block starting at param 0, `gain = raw / 1638.4`. The block is 40 bytes
  (function `02`) for Profile Type 1, but 36/50/54 bytes (function `02`) and 74/94/102
  bytes (function `08`) occur too — and type-1 rigs use them as well, so do not gate on
  Profile Type. Matching only the 40-byte form drops every later-generation rig; an
  unlisted shape decodes to `None`. Every listed shape was checked against the `Gain`
  column and agrees within its one-decimal rounding.
- **A performance slot is a copy, not a link.** Each slot track is a whole rig, editable
  apart from its parent (the manual says so). `RigName`/`CabName` mirror the strings at
  addresses `00 00 01`/`00 00 20` inside that track — in every slot checked — so a slot
  naming no library rig still plays; `doctor` calls it dangling, not broken on-device.
- **Strings are addressed.** The 3 bytes after `00 00 03` are the address: `00 00 01` is
  the rig name (equal to the `Name` column in every rig checked), `00 00 20` the loaded
  cab's name, and a cab-IR preset carries
  its own name there — that is how `doctor` knows which IRs are loaded. A `.wav` name is
  only present for user IRs; factory cabs have none, so do not key IR usage on `.wav`.
  `rename` rewrites `00 00 01` in the rig and each re-pointed slot track (byte-level,
  `_sysex_edit.replace_string`); a payload name differing from the row means an outside edit.
- **A truncated blob raises `ValueError("truncated blob: …")`**, never `IndexError` — and so
  do bytes after the last chunk and a chunk running past the end (no real blob has either).
  A performance payload holds exactly six tracks (header + 5 slots) in every one seen;
  `_sysex.performance_tracks` rejects any other count. A track whose events stop early is
  *not* an error: snapshot performances can hold slot tracks with an encoded `.krig` body
  (`4b 80 54 68 64 80 …`), undecoded; `doctor` lists such tracks as unread.
- **A pack payload is a bare track, not a `.krig`.** `rigdata.rig` in a `.rigpack` /
  `.presetpack` (bare SQLite) starts `00 F0 …` — no `KThd`/`KTrk`. Its raw digest matches
  nothing; wrapped by `_sysex.krig` (`KThd` len 6 `00 00 00 01 01 e0` + one `KTrk`) it is
  byte-identical to the stored blob wherever it also occurs. Pack `rigs`
  rows have no amp/gain/cab columns, and `rigs.comment` is an instrument category, not the
  comment — `_packs.py` reads those from the payload strings the `Rigs` columns mirror
  (`00 00 04` comment, `10` amp name, `18` amp model, `20` cab, …; see `docs/format.md`).
  `Content` (`Rigs`/`Presets`) in `properties`, not the extension, says which it holds.
- **The cab columns and the cab strings can disagree in a user's library.** Loading a cab
  onto a DI profile changes the payload's `0x20–0x2e` strings; the `Cabinet Name` column keeps
  `N/A`. In published rigs (Rig Exchange, packs) they agree, which is why a pack rig's DI flag
  can come from its payload.
- **Performance slot tracks carry their own amp block**, and its gain often differs from
  the referenced rig's. Slot gain in reports comes from the referenced rig; the slot-track
  value is unverified — do not surface it as the slot's gain without checking.
- **The REV slot has two encodings, one firmware generation apart.** Rigs uploaded through
  2018 put it on page `0x4B`, where the value is a *room size* on an index-based list.
  Rigs from 2019 on use page `0x3D`, where the value is a Type on the same global enum as
  every other slot. **They never co-occur** in any rig checked. Reading only `0x4B` drops
  the reverb from every modern rig; naming `0x4B` from the global enum calls value 1
  "Wah Wah".
  Delay page `0x4A` is deprecated since OS 4.0; delays live in the DLY stomp slot.
- **Function `08` blocks are undecoded.** Some rigs carry stomp, REV and amp pages as
  `00 00 08 00 <page> <start>` instead of function `02`, and only the amp gain is read from
  them. A slot present only in that framing is reported as undecoded (`decoded: false`,
  `SLOT=?` in text): its type — and whether it holds an effect at all — is unknown. A
  function-`02` block always decides its slot. `pages RIG` lists them under "other
  framings".
- **Effect names are not hard-coded.** They come from `Stomps.xml` inside the Rig Manager
  app bundle, read at runtime, with a category per type. Point
  `KEMPERRIG_STOMPS_XML` elsewhere to override. Without it, only a verified subset resolves.
- **Preset Class is the kind discriminator.** `6` = cabinet IR, `3` = effect module.
- **Boost is inferred, not stored.** It comes from free-text in `Amp Comment` (pedal names,
  "Unboosted"). `is_boosted` is `None` when the text says nothing about drive — treat
  `None` as unknown, never as False.
- **DI vs studio profile** is `cabinet_name` being absent/`N/A`/`DIRECT`, not a flag.
  `Cabinet Type` (`rigs --json` → `cabinet_type`) looks like one and is not: DI rigs sit
  under more than one value, and one value mixes DI rigs with real merged cabs.
- **Duplicate rig names are real** — across folders, and inside one snapshot or pack, which
  has no folders. `rig`/`pages` refuse an ambiguous name: `--folder` when folders tell the
  rigs apart, else `--payload DIGEST` (the 12-hex digest `history --rig` prints; the error
  lists them). `rename` rewrites every match.
- **Snapshots are not library folders.** `Backups/*R2.db` is one bare SQLite db per dated
  snapshot, detected by the SQLite header, not the name. Its rigs and presets have no
  folder, so `diff` against a `.rmbackup` or the live tree never aligns rigs or presets —
  every one shows as removed and re-added; only performances (keyed by name) line up. Its
  `ROMPresets` table is factory content and is skipped. Snapshot file names start with a
  personal device id — never copy one into a tracked file.
- **One `Backups/` folder mixes devices.** Several device ids interleave in time with
  different content, so consecutive snapshots in time order are often two devices, not an
  edit. `history` compares each snapshot only with the previous one of its own id; a plain
  sort by name groups ids, so "first/last seen" is taken from the file-name date-times.

## Where the format is documented

`docs/format.md` in this repo owns the container, the tables, and the framing. The Kemper
Main Manual explains what a decoded value *means* but contains no SysEx spec, no page
numbers, and nothing about `.rmbackup` — do not use it for byte layout. Numeric parameter
values live in Kemper's separate MIDI Parameter Documentation.

## Provenance

The backup file is ground truth. Rig Manager agreeing is confirmation. The manual is
authoritative for meaning, never for byte layout. Anything else is a hypothesis — decode it
as `None` rather than guessing.
