# What kemperrig can do

Everything kemperrig does, organized by the question you are asking of your library. Every
command is `kemperrig <name>`; [cli.md](cli.md) has the exact flags and
[json.md](json.md) every `--json` document.

For AI assistants: the `kemper-rmbackup` skill covers the format traps behind these
commands in a condensed form.

---

## Table of Contents

- [What it reads](#what-it-reads)
- [Browse and filter](#browse-and-filter)
- [Decode one rig](#decode-one-rig)
- [Select by what a rig holds](#select-by-what-a-rig-holds)
- [Tidy a library: analyze](#tidy-a-library-analyze)
- [Check what points where: doctor](#check-what-points-where-doctor)
- [Packs](#packs)
- [What changed: diff and history](#what-changed-diff-and-history)
- [The writers](#the-writers)
- [Machine output](#machine-output)
- [What it does not do](#what-it-does-not-do)
- [Adding a capability](#adding-a-capability)

## What it reads

| Source | What it is |
|---|---|
| `.rmbackup` | a backup Rig Manager wrote: a zip of SQLite databases |
| the live directory | Rig Manager's own library folder, the same layout unzipped |
| a dated snapshot | one `Backups/*R2.db` file Rig Manager keeps in the live directory |
| a rig pack, a preset pack | `Rig Packs/*.rigpack`, `Preset Packs/*.presetpack` |

Every read command takes any of them. Snapshots and packs have no folders, so their rigs
are known by name alone. Databases are read into memory from the file's bytes: nothing is
extracted to disk and nothing is written beside a live library.

## Browse and filter

- `summary` — counts, DI/studio split, gain range and bands, amp models, authors.
- `rigs` — every rig, highest gain first, narrowed by any mix of `--name`, `--amp`,
  `--author`, `--folder`, `--source`, `--channel`, `--comment`, `--gain-min`/`--gain-max`,
  `--di`/`--studio` and `--boosted`/`--unboosted`.
- `presets` — the effect and cab-IR presets.
- `performances` — each performance's five slots, the gain each slot's rig carries, and how
  many effects stay locked across the slots in use.

Boost is read from the free-text `Amp Comment` (pedal names, "unboosted", "no boost");
when the text says nothing about drive, the rig is neither boosted nor unboosted.

## Decode one rig

`rig NAME` decodes the rig's payload — the bytes the Profiler loads — beside its metadata:
the amp gain from the amp block, the effect in each module slot with its on/off, the
loaded cab IR, and every string. `rig NAME --json` gives the same as data.

A slot whose block exists only in the function-`08` framing is shown as `SLOT=?`: its
type, and whether it holds an effect at all, are unknown, so it is never guessed and never
dropped. `pages NAME` prints the raw parameter blocks behind the decode, and `pages --all`
counts which pages occur across the library — the starting point for decoding something
new.

When several rigs share a name, `rig` and `pages` refuse to guess: narrow with `--folder`,
or with `--payload` and a digest prefix, which the error lists.

## Select by what a rig holds

`rigs --effect TEXT` and `rigs --ir TEXT` select by the decoded payload rather than the
metadata — "which rigs carry a delay", "which rigs load this IR":

```bash
kemperrig rigs "<backup>" --effect delay --gain-min 6
kemperrig rigs "<backup>" --ir "4x12 V30" --decode
```

`--effect` matches a decoded effect's type name or category, on or off; `--ir` the cab-IR
file name. `--decode` shows each rig's effects and cab IR under it (or adds `decode` to each
rig in `--json`). `extract` takes the same flags.

A filter never silently drops a rig it cannot judge. It lists, after the results:

- rigs whose payload does not parse;
- rigs that miss `--effect` but hold an undecoded slot, where the effect may be.

## Tidy a library: analyze

`analyze` reports what is worth acting on:

- **orphaned rigs** — no performance uses them;
- **per-amp gain coverage** — amps with several rigs but no clean one or no high-gain one;
- **duplicates** — byte-identical profiles, byte-identical amp blocks with other effects,
  and rigs that merely share author, amp, gain and boost (a prompt to listen, not
  evidence);
- **effect categories** in use, and **cab IRs** in use;
- **performances whose gain ladder is out of order**;
- **payloads that do not parse**, skipped and listed.

Rigs pulled off the Profiler and filed in their own folder are in use even though no
performance names them. Tell `analyze` which folder that is with `--rack-folder`, or set
`KEMPERRIG_RACK_FOLDER`. There is no default: the folder name is your filing convention,
not something Rig Manager defines. `--strict` exits 1 when there is something to act on.

## Check what points where: doctor

A performance slot holds its own copy of the rig it was built from, under that rig's name.
`doctor` joins those names, and the payloads themselves, back to the library:

| Finding | Kind | What it means |
|---|---|---|
| dangling slot | definite | No library rig has the slot's rig name: the rig was deleted, renamed, or never in the library. The slot still plays its own copy. |
| ambiguous slot | definite | Rigs with different payloads share the slot's rig name, so which one it came from is undefined. |
| broken payload | definite | A payload that is empty, cut short, holds no Kemper SysEx, or — for a performance — does not hold a header and five slot tracks. |
| bytes nothing reads | informational | A payload that parses, but one of its tracks stops being SysEx events before its end. |
| on the device only | informational | With `--device-backup`, a dangling slot whose rig that backup holds. |
| amp gain differs | informational | A rig's decoded amp gain and its stored `Gain` differ by more than the column's rounding. |
| name differs | informational | The name in the library differs from the one inside the payload, which is what the Profiler shows. |
| unused cab IR | informational | A cab-IR preset no rig or slot loads. |

`--strict` exits 1 on a definite finding only. `--device-backup` takes any source holding
what is on your Profiler.

A payload that does not parse stops only a command about that one rig (`rig`, `pages RIG`),
and the error names it. `analyze` and `pages --all` skip and list it, `performances` shows
no locked share for it, `extract` skips it with a note, and every other command reads past
it.

## Packs

`pack PACKFILE` lists a pack's name, vendor and release date and each rig's amp, gain and
DI/studio — or each preset. A pack has no amp or gain columns, so those are read from each
rig's payload. With `--against LIBRARY`, every item gets a standing:

| Standing | Meaning |
|---|---|
| in library | The library holds this exact payload — under the name shown, which may differ. |
| name taken | Library rigs (or presets) use this name, with a different payload. |
| new | Neither. |

A bare `--against` compares with `KEMPERRIG_LIBRARY`. A pack also works as the source of
any read command, of `diff` and of `extract`.

## What changed: diff and history

`diff BEFORE AFTER` lists rigs, performances and presets added, removed and changed between
two sources, field by field, with payloads compared by digest. A performance slot pointed at
another rig shows as `slot N`; same-named records are paired by payload, then by fields.
It exits 1 when the sources differ, so it can gate a script.

`history` reads Rig Manager's dated snapshots — or any snapshots and `.rmbackup` files — one
at a time and prints, for each, its counts and what was added (`+`), removed (`-`) or
changed (`~`) since the previous file **from the same device**: one `Backups/` folder can
hold snapshots from several devices, and those are never compared with each other. With no
source it reads the `Backups/` folder of `KEMPERRIG_LIBRARY`. Unreadable files are skipped
with a note on stderr; an empty snapshot is never used as a baseline.

`history --rig NAME` answers "which snapshot still has the version before I changed it":
every file holding that rig, each distinct payload as a numbered version, and where each
was first and last seen.

## The writers

kemperrig reads; three commands write, and none of them modifies its source.

**`rename`** writes a **new** `.rmbackup` with a rig renamed in the library row, inside its
payload (the name the Profiler shows), and in every performance slot that loads it. Every
other byte is kept, so renaming back restores the original. It refuses a name no rig has,
a new name another rig has or a slot already loads, and a new name that is not printable
ASCII of at most 32 characters. The renamed archive has not been confirmed to restore into
Rig Manager, and `rename` says so after every run: keep the original.

**`extract`** writes selected rigs as standalone `.krig` files, byte for byte — a rig's
payload *is* its `.krig` file. It selects with exactly the flags `rigs` takes (so `rigs`
previews it) or `--all`, refuses to run with no selection, makes names file-safe, and
numbers collisions the same way on every run. A rig whose payload is empty or does not
parse is skipped with a note.

**`summary --write-golden`** writes a census of the library, for the opt-in golden test —
see [census.md](census.md).

All three refuse, with one line and exit 2 before writing anything:

- an output that is the source — case variants, symlinks, hardlinks and `..` included —
  even with `--force`;
- an output inside the source or inside any Rig Manager library;
- an output that exists, unless `--force` is given.

Missing folders on the way to the output are created; nothing is ever deleted.

## Machine output

Every read command takes `--json`, so a whole library can go through `jq` or into a
spreadsheet:

```bash
kemperrig rigs "<backup>" --json --amp Rectifier --gain-min 6 | jq '.rigs[].name'
kemperrig diff a.rmbackup b.rmbackup --json | jq '.rigs.changed'
```

`diff`, `analyze --strict` and `doctor --strict` exit 1 when they find something.

## What it does not do

- Talk to the Profiler, or change a library in place.
- Decode the profile itself — the amp model's DSP — or knob values beyond the amp gain.
- Guess a value it has not verified against a real file: those decode to `null`.
- Ship any Kemper data: effect names are read from your own Rig Manager install.

## Adding a capability

A new command is one service call plus a render: the logic in a module under
`src/kemperrig/services/`, the text view in `_views/`, the document in `_json/`, the parser
in `cli/`. [python-api.md](python-api.md#adding-a-command) walks through it; add the command
to this page, [cli.md](cli.md) and [json.md](json.md) in the same change.
