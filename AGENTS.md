# kemperrig — guide for coding agents

kemperrig reads Kemper Profiler Rig Manager libraries — `.rmbackup` archives, the live Rig
Manager directory, its dated snapshots, and rig and preset packs — and decodes the SQLite
metadata and SysEx payloads inside them. A library plus a CLI. The user-facing docs start at
[README.md](README.md) and [docs/README.md](docs/README.md).

## The one invariant

A `.rmbackup` is often the only copy of someone's profile library. **Nothing here modifies a
source file.** Three writers exist, each writing new files only:

- `rename` → a new archive (`services/edit.py`)
- `extract` → `.krig` files (`services/extract.py`)
- `summary --write-golden` → a JSON census (`services/census.py`)

Each keeps its `refusal` guard in the service and re-runs it before writing, starting from
`model.write_refusal`: an output that is the source, aliases it (case variant, symlink,
hardlink, `..`) or lies inside any Rig Manager library is refused — by file identity, never
by comparing path strings. A change that writes in place does not land.

## Layout

    src/kemperrig/
      records.py         Rig / Performance / Slot / Preset / Info — frozen dataclasses, no I/O
      _tables.py         SQLite rows in, records out
      _packs.py          rig/preset pack rows in, a Pack record out
      model.py           Backup — the container and its entry points (zip / live / snapshot / pack)
      _archive.py        open the .rmbackup zip and read one entry, bounded and damage-checked
      _sysex.py          KThd/KTrk blob decode: framing, strings, amp gain, locked share
      _sysex_effects.py  module blocks: raw pages, other framings, effect chains
      _sysex_edit.py     rewrite one string in a blob, every other byte kept
      _enums.py          effect type names, read from Rig Manager's Stomps.xml at runtime
      cli/               argparse, env resolution, the exception boundary; one module per command group
      _views/            plain-text rendering, no I/O
      _json/             --json documents, no I/O
      services/          one concern each: report, filter, select, shortlist, analyze, doctor,
                         performance, decode, pages, pack, diff, history, census, edit, extract
    tests/               hermetic: _payloads.py builds SysEx, _fixture.py archives,
                         _pack_fixture.py packs, _sample.py a whole library on disk

The library core is stdlib-only. pf-core appears at the CLI boundary (`resolve_str`) and in
the three writers (`atomic_write_bytes`); `tests/test_dependencies.py` pins that surface —
widen it deliberately, in the same commit as the reason, or not at all.

## Commands

    bin/run setup            venv + editable install
    bin/run pytest           the suite
    bin/run lint             ruff + the pf-core file-size gate (300 soft / 500 hard)
    bin/run kemperrig ...    the CLI
    bin/run sample DIR       write a synthetic library to DIR, to try any command on

`bin/run` sources a gitignored `.env` (see `.env.example`) for `KEMPERRIG_*` settings.

## Rules and skills

- `.ai/rules/` — layering, error handling, code style, testing, scope, logging, framework
  use, anti-patterns, docs sync. Read the ones your change touches before writing code.
- `.ai/skills/kemper-rmbackup/` — the format traps that make a naive read give wrong
  answers. Read it before changing any decode.

## Two kinds of knowledge

**Format** — the container, the SQLite tables, the SysEx framing, page and parameter
numbers — lives in [docs/format.md](docs/format.md) and in the files themselves. Kemper
publishes no specification for the container; module page numbers come from Kemper's
*MIDI Parameter Documentation*.

**Semantics** — what a module slot, a Direct Amp Profile or a reverb type means — come from
Kemper's Main Manual: authoritative for meaning, never for byte layout.

Provenance, strongest first: **the file** → **Rig Manager agreeing** → **the manual** →
**inference**. Inference is a hypothesis: decode it as `None` rather than guess.

## House rules

- **This repo is public.** Nothing from a real library goes in a tracked file — no rig,
  performance, author, folder or pack names, no library counts, no device ids, no absolute
  paths — including docstrings, comments and fixtures.
- **Fixtures stay synthetic.** Never commit a `.rmbackup`, `.rigpack`, `.presetpack` or
  `.krig`, nor a detail taken from one; extend the builders in `tests/` instead.
- **Every CLI failure is one line on stderr and a non-zero exit**, never a traceback.
- **Code and docs travel together** (`.ai/rules/docs-sync.md`); `tests/test_docs.py`
  fails the build when the CLI or `--json` references drift.
- **File-size target 300 lines, hard limit 500**, one concern per file.
- Personal notes for your agent belong in a gitignored `CLAUDE.local.md`, never here.
