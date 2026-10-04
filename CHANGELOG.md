# Changelog

Notable changes to kemperrig, newest first.

## v0.1.0 — 2026-10-04

First public release. Apache-2.0; published to PyPI.

### Reading

- Opens a `.rmbackup`, the live Rig Manager directory, a dated snapshot (`Backups/*R2.db`)
  or a rig or preset pack (`.rigpack`, `.presetpack`), told apart by content. Snapshot and
  pack records have no folder; factory `ROMPresets` are not read.
- Rigs (with `profile_type`, `profile_revision`, `cabinet_type` and
  `cabinet_configuration` raw), performances and their slots, effect and cab-IR presets, and
  backup info. A NULL name reads as empty, a non-BLOB payload as an empty payload, a BLOB in
  a text column as NULL, and a `Gain` that is not a finite number as no gain. A damaged
  database is reported with its path.
- A damaged, encrypted or unsupported archive entry, or one that would inflate past 1 GiB or
  past 100:1 beyond 16 MiB, is refused with a message naming it; `history` skips that file.
- Payload decode for KThd/KTrk and MThd/MTrk framing: strings by address, amp gain from every
  verified amp-block shape, the effect in each module slot with its on/off (REV on page
  `0x3d`, or `0x4b` on older rigs), and the cab IR.
- A module slot present only in the function-`08` framing is reported as undecoded — no
  type, name or on/off — rather than dropped.
- Effect type names and categories are read at runtime from the `Stomps.xml` in the user's
  Rig Manager install; `KEMPERRIG_STOMPS_XML` overrides the path, and without it a verified
  subset resolves.
- A payload that is cut short, has a chunk running past its end or bytes after its last
  chunk, or (for a performance) does not hold a header and five slot tracks does not parse.
  Library-wide commands read past it and say so; a command about that one rig names it.

### Commands

- `summary`; `rigs` with metadata filters (`--name`, `--amp`, `--author`, `--folder`,
  `--source`, `--channel`, `--comment`, `--gain-min`/`--gain-max`, `--di`/`--studio`,
  `--boosted`/`--unboosted`); `rig`, narrowed by `--folder` or `--payload DIGEST`;
  `presets`; `performances` with slot gain ladders and locked-effects share.
- `rig --json` and `rigs --decode`: a rig's decoded amp gain, effects, cab IR and strings as
  data. Every rig entry in `--json` carries its payload digest.
- `--effect` and `--ir` select rigs by a decoded effect's type name or category and by cab-IR
  name, on `rigs` and `extract`. Rigs a filter cannot judge are listed, never dropped.
- `pages RIG` dumps a rig's raw parameter blocks; `pages --all` counts which pages occur
  across the library.
- `analyze` — orphaned rigs, per-amp gain coverage, duplicates, effect categories, cab-IR
  usage, out-of-order gain ladders, payloads that do not parse. `--strict` exits 1 when there
  is something to act on; `--rack-folder` exempts one folder from the orphan sweep.
- `doctor` — dangling and ambiguous performance slots and broken payloads (definite);
  unread payload bytes, gain and name disagreements and unused cab IRs (informational).
  `--strict` exits 1 on a definite finding; `--device-backup` marks a slot whose rig is on
  the device.
- `shortlist` — caller-supplied amp patterns above a gain floor, DI-only unless
  `--include-studio`; the criteria file is shape-checked on load.
- `pack` lists a pack and its rigs or presets; `--against [LIBRARY]` marks each as in the
  library, name taken, or new.
- `diff` — rigs, performances and presets added, removed or changed, including a performance
  slot re-pointed at another rig. Exits 1 when the sources differ.
- `history` — per dated snapshot or backup, the counts and what changed since the previous
  file from the same device; `--rig NAME` lists every file holding that rig and each payload
  version.
- `--json` on every read command, specified key by key in `docs/json.md`.

### Writers — none modifies its source

- `rename` writes a new archive with the rig renamed in its row, inside its payload, and in
  each performance slot that loads it, keeping every other byte. It refuses an unknown name,
  a taken one, and a new name that is not printable ASCII of at most 32 characters. Its
  archive is not yet confirmed to restore into Rig Manager, and it says so.
- `extract` writes selected rigs as standalone `.krig` files, verbatim. It requires a
  selection or `--all`, and makes file names safe and numbers collisions.
- `summary --write-golden PATH` writes a library census (format 1, with decoded and
  undecoded effect slots counted apart) for the opt-in golden test.
- All three refuse, exit 2, an output that is the source (case variants, symlinks, hardlinks
  included), one inside the source or any Rig Manager library, and an existing output
  without `--force`; missing folders on the way to the output are created. A file output
  spelled as a folder (`out/`) is refused.

### CLI

- `KEMPERRIG_LIBRARY`, `KEMPERRIG_CRITERIA`, `KEMPERRIG_RACK_FOLDER` and
  `KEMPERRIG_STOMPS_XML` supply the settings, and `--help` names each one.
- Runs as `kemperrig`, `python -m kemperrig`, or `python -m kemperrig.cli`.
- Every failure is a one-line message and a non-zero exit, never a traceback.
- Text output shows control characters from a file as `\xNN`; `--json` is strict JSON.

### Python API

- `Backup.open` and the records, the services under `kemperrig.services`, and
  `use_effect_names()` / `DEFAULT_STOMPS_XML` to name effects from Rig Manager's table.

### Development

- `bin/run sample DIR` writes a synthetic library — every source kind, one of each finding —
  and the test suite runs every command against it.
- Documentation in `docs/`: installation, capabilities, command reference, JSON reference,
  Python API, criteria, census and format. `tests/test_docs.py` keeps the command and JSON
  references in step with the code.
