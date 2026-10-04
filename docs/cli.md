# Command reference

Every command, flag, environment variable and exit code. `kemperrig <command> --help`
prints the same for one command; [capabilities.md](capabilities.md) explains what each
command is for.

---

## Table of Contents

- [Sources](#sources)
- [Environment](#environment)
- [Exit codes and errors](#exit-codes-and-errors)
- [Library overview](#library-overview): summary · rigs · rig · presets · performances
- [Raw blocks](#raw-blocks): pages
- [Curation](#curation): analyze · doctor · shortlist
- [Packs](#packs): pack
- [Comparing](#comparing): diff · history
- [Writers](#writers): rename · extract · summary --write-golden
- [Adding a command or flag](#adding-a-command-or-flag)

## Sources

A `SOURCE` is any of:

- a `.rmbackup` archive Rig Manager wrote;
- the live Rig Manager directory (on macOS,
  `~/Library/Application Support/Kemper Amps/RigManager`);
- a dated snapshot from that directory's `Backups/` folder (`*R2.db`);
- a rig or preset pack (`Rig Packs/*.rigpack`, `Preset Packs/*.presetpack`).

Each is told apart by its content, not its name. Where `SOURCE` is optional, it defaults to
`KEMPERRIG_LIBRARY`. Snapshot and pack rigs have no folder.

## Environment

| Variable | Used for |
|---|---|
| `KEMPERRIG_LIBRARY` | the `SOURCE` when a command is given none; `history`'s `Backups/` folder; a bare `pack --against` |
| `KEMPERRIG_CRITERIA` | the criteria file `shortlist` reads without `--criteria` ([criteria.md](criteria.md)) |
| `KEMPERRIG_RACK_FOLDER` | the folder `analyze` exempts from the orphan sweep without `--rack-folder`; no default |
| `KEMPERRIG_STOMPS_XML` | Rig Manager's `Stomps.xml`, where effect names come from, when it is not at `/Applications/Rig Manager.app/Contents/Resources/Stomps.xml` |
| `KEMPERRIG_GOLDEN` | not read by the CLI: the census the opt-in golden test compares `KEMPERRIG_LIBRARY` with ([census.md](census.md)) |

A flag always wins over its variable. `bin/run` in a checkout reads a gitignored `.env`;
see `.env.example` in the repository.

## Exit codes and errors

| Code | Meaning |
|---|---|
| `0` | It worked — including `diff` of identical sources, and `analyze` / `doctor` without `--strict` |
| `1` | A failure, or a finding: `diff` found differences, `analyze --strict` found something to act on, `doctor --strict` found a definite defect |
| `2` | A bad invocation, or a writer's guard refused — nothing was written |

Every failure is one line on stderr, prefixed `kemperrig:`, never a traceback. Output stays
clean for `--json`, and a closed pipe (`| head`) exits 0.

A damaged, encrypted or unsupported archive entry is such a failure, and so is one that would
inflate past 1 GiB, or past 100:1 beyond 16 MiB — no Rig Manager database comes close. The
message names the entry and the archive; `history` skips that file and reads the rest.

Names and strings come from files other people may have written, so text output shows any
control character in them as `\xNN` rather than send it to the terminal. `--json` keeps
the value as stored.

## Library overview

| Usage | What it does |
|---|---|
| `summary [SOURCE] [--json]` | counts, DI/studio split, gain range and bands, amp models, authors |
| `rigs [SOURCE] [filters] [--decode] [--json]` | list rigs, highest gain first, filtered by every flag given (AND) |
| `rig [SOURCE] NAME [--folder TEXT] [--payload DIGEST] [--json]` | one rig's metadata and decoded payload: amp gain, effects, cab IR, strings |
| `presets [SOURCE] [--json]` | the effect and cab-IR preset inventory |
| `performances [SOURCE] [--json]` | each performance's slots, gain ladder and locked-effects share |

Filters, shared by `rigs` and `extract`:

| Usage | What it selects |
|---|---|
| `rigs --name NAME` | an exact rig name; repeat for more than one |
| `rigs --amp TEXT` | amp-model substring |
| `rigs --author TEXT` | author substring |
| `rigs --folder TEXT` | library-folder substring |
| `rigs --source MAKER` | manufacturer substring (`Source Amp`) |
| `rigs --channel TEXT` | amp-channel substring |
| `rigs --comment TEXT` | amp-comment substring |
| `rigs --gain-min N` / `--gain-max N` | the `Gain` column, inclusive |
| `rigs --di` / `--studio` | DI profiles only, or studio (cab-baked) profiles only |
| `rigs --boosted` / `--unboosted` | by the boost the amp comment describes; rigs whose comment says nothing about drive match neither |
| `rigs --effect TEXT` | a decoded effect whose type name or category contains `TEXT`, in any slot, on or off |
| `rigs --ir TEXT` | a cab IR whose file name contains `TEXT` |

Substring matches ignore case. With `--effect` or `--ir`, rigs the filter cannot judge — a
payload that does not parse, or an undecoded slot that might hold the effect — are listed
after the results (and under `unchecked` in `--json`), never silently dropped.

`rig` refuses a name several rigs share: narrow it with `--folder`, or, where folders do not
tell them apart, with `--payload` and a digest prefix the error lists.

## Raw blocks

| Usage | What it does |
|---|---|
| `pages [SOURCE] RIG [--folder TEXT] [--payload DIGEST] [--json]` | the rig's raw parameter blocks as 14-bit values, plus messages in other framings |
| `pages [SOURCE] --all [--json]` | which pages occur across the library, at which start numbers and lengths |

## Curation

| Usage | What it does |
|---|---|
| `analyze [SOURCE] [--rack-folder FOLDER] [--strict] [--json]` | orphans, per-amp gain coverage, duplicates, effect categories, cab IRs in use, out-of-order gain ladders |
| `doctor [SOURCE] [--device-backup SOURCE] [--strict] [--json]` | dangling and ambiguous slots, broken payloads; informational gain, name and unread-payload findings and unused cab IRs |
| `shortlist [SOURCE] --criteria FILE [--gain-min N] [--include-studio] [--json]` | rigs on the criteria's amps at or above the gain floor, DI only unless `--include-studio` |

- `analyze --strict` exits 1 on orphans, duplicates, a bad gain ladder or a payload that does
  not parse. `--rack-folder` names the folder of rigs pulled off the Profiler, which count as
  in use.
- `doctor --strict` exits 1 on a definite finding only. `--device-backup` takes any source
  holding what is on your Profiler and marks a dangling slot whose rig it holds as on the
  device only.
- `shortlist --criteria` defaults to `KEMPERRIG_CRITERIA`; the file's format is in
  [criteria.md](criteria.md).

## Packs

| Usage | What it does |
|---|---|
| `pack PACKFILE [--json]` | a pack's name, vendor and release date, and each rig's amp, gain and DI/studio, or each preset |
| `pack PACKFILE --against [LIBRARY] [--json]` | each item's standing in the library: in library, name taken, or new |

A bare `--against` compares with `KEMPERRIG_LIBRARY`; put it after `PACKFILE`.

## Comparing

| Usage | What it does |
|---|---|
| `diff BEFORE AFTER [--json]` | rigs, performances and presets added, removed or changed; exit 1 when they differ |
| `history [SOURCE ...] [--order name\|mtime] [--rig NAME] [--json]` | counts and changes across dated snapshots and backups, each compared with the previous file from the same device |

`history` with no `SOURCE` reads the `Backups/` folder of `KEMPERRIG_LIBRARY`. A `SOURCE` is
a snapshot or `.rmbackup` file, or a folder of them. `--rig NAME` lists every file holding a
rig of that name and each distinct payload as a numbered version.

## Writers

None of these modifies its source.

| Usage | What it writes |
|---|---|
| `rename [SOURCE] OLD NEW -o/--out OUT [--force]` | a new `.rmbackup` with the rig renamed — row, payload, and every performance slot that loads it |
| `extract [SOURCE] -o/--out DIR (--all \| filters) [--force] [--json]` | each selected rig's payload, byte for byte, as `DIR/<name>.krig` |
| `extract` filters | the same as `rigs`: `--name`, `--amp`, `--author`, `--folder`, `--source`, `--channel`, `--comment`, `--gain-min`, `--gain-max`, `--di`, `--studio`, `--boosted`, `--unboosted`, `--effect`, `--ir` |
| `summary [SOURCE] --write-golden PATH [--force]` | the library census ([census.md](census.md)) |

- Each refuses, exit 2, an output that is the source (case variants, symlinks, hardlinks and
  `..` included), one inside the source or any Rig Manager library, and an existing output
  without `--force`. `--force` never permits writing over the source.
- `rename` takes a `.rmbackup` only, and refuses an unknown old name, a new name another rig
  has or a performance slot loads, and a new name that is not printable ASCII of at most 32
  characters. Missing folders on the way to `OUT` are created. Its archive is not yet
  confirmed to restore into Rig Manager — keep the original.
- `rename -o` and `--write-golden` name a file: a path that is a folder, or ends in a path
  separator, is refused.
- `extract` needs a selection or `--all`, and refuses `--all` with filters. `DIR` is created
  if missing; names are made file-safe and numbered on collision.
- `summary --force` without `--write-golden` is an error.

## Adding a command or flag

1. Add the parser in its `register_<command>` in the matching `src/kemperrig/cli/_<group>.py`
   and give the command a slot in `_COMMANDS` (`cli/__init__.py`); a new environment variable
   resolves there through `resolve_str`, and joins the help epilog.
2. Add its row here — `tests/test_docs.py` fails when a command or long flag is missing from
   this page, or when a row names a flag the command lacks.
3. Document any new `--json` keys in [json.md](json.md), and the behaviour in
   [capabilities.md](capabilities.md) and `README.md`.
