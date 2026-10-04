# Layering

No layer skipping, and no layer imports from a layer above it.

```
Entry point:
    cli/                         argparse, env resolution, dispatch, the exception boundary
      │                          (__init__.py: main · _<concern>.py: one per command group)
      ├─ _views/                 plain-text rendering, one module per command group
      └─ _json/                  --json documents, one module per command group
                  ↓
        Service layer (services/)      report · filter · select · shortlist · analyze · doctor · census
                  ↓                    performance · decode · pages · pack · diff · history · edit · extract
   Domain:  model.py               Backup — the container and its entry points (zip / live / snapshot / pack)
              ├─ _tables.py        SQLite rows in, records out
              ├─ _packs.py         rig/preset pack rows in, a Pack record out
              ├─ _archive.py       open the zip, read one entry, bounded and damage-checked
              └─ records.py        Rig / Performance / Slot / Preset / Info
            _sysex.py              KThd/KTrk blob decode, standalone
              ├─ _sysex_effects.py module blocks: raw pages, effect chains
              └─ _sysex_edit.py    rewrite one string in a blob, every other byte kept
```

**Call direction:** `cli` → `_views`/`_json` → `services/` → `model`/`_tables`/`_packs`/`_sysex` →
`records`. There is no orchestrator layer, and adding one needs a reason: every command here
is a single service call plus a render.

`_views/` and `_json/` are two renderings of the same data and sit at the same level.
When a field appears in one, decide deliberately whether it belongs in the other — they have
drifted before.

---

## Per-layer ownership

| Layer | Owns | Must never |
|-------|------|-----------|
| **CLI** (`cli/`) | argparse construction; env resolution via `resolve_str`; dispatch to one service; the exception boundary; exit codes | Decode SysEx or SQLite; contain filter or analysis logic; write to an input path |
| **Views** (`_views/`) | Formatting command output for a terminal | I/O of any kind; deciding what to compute |
| **JSON** (`_json/`) | Building `--json` documents | I/O beyond `print`; diverging from `_views` without a reason |
| **Service** (`services/`) | One concern per module; take records, return plain values | Import from `cli`, `_views` or `_json`; `print()`; read `os.environ` |
| **Domain** (`model.py`, `_archive.py`, `_tables.py`, `_packs.py`, `_sysex.py`, `_sysex_effects.py`, `_sysex_edit.py`) | The container layout, the SQLite tables, the blob framing | Import from any layer above; know what a command does |
| **Records** (`records.py`) | The frozen dataclasses and the properties derived from their own fields | Import anything from this package |

---

## Entry point — the `cli/` package

- `__init__.py` owns `main()`: the parser, `--version`, env resolution, dispatch and the
  exception boundary. `_COMMANDS` there fixes the order `--help` lists commands in.
- Each `_<concern>.py` (`_library`, `_curation`, `_doctor`, `_pages`, `_packs`, `_compare`, `_write`) holds its
  `cmd_*` handlers and a `register_<command>(subparsers)` per command that adds the
  parser and `set_defaults(func=...)`. A new command gets a registrar and a slot in
  `_COMMANDS`; a new concern gets a new module.
- Positionals argparse cannot split alone (`pages [backup] (RIG | --all)`) are resolved by
  a `prepare(args)` default the registrar sets; `main()` runs it before env resolution.
  `history` uses the same hook to set `backup` only when no SOURCE is given, so
  `KEMPERRIG_LIBRARY` resolves just for its bare form; `pack` uses it to set `backup` only
  when `--against` is given, so a bare `--against` resolves `KEMPERRIG_LIBRARY` and no flag
  reads no library.
- One subcommand = one service call plus a render. No transform logic.
- The only package where `resolve_str` and `os.environ` appear, and — beside `_json.dump`
  and the `__main__.py` shims — `print()` and `sys.exit`.
- `main()` is the only place that catches exceptions (`error-handling.md`).
- There are exactly three writers, and each writes new files — never an input path:
  `services/edit.py` (a new archive), `services/extract.py` (`.krig` files) and
  `services/census.py` (`summary --write-golden`, a JSON census). Each keeps its guard
  `refusal` in the service and its writer runs it itself, so a direct caller is guarded
  too; `model.write_refusal` is the source/library check all three start from.
  All three use `atomic_write_bytes`.

## Service layer

- One concern per module; never import from an entry point.
- A service may import a lower-level sibling (`analyze` → `performance`, `pages` → `decode`,
  `select` → `filter` + `decode`, `history` → `diff`, `doctor` → `diff`). Keep the graph acyclic; if two services need each
  other, the shared part belongs lower.
- Never `print()`, never read `os.environ` — take what you need as a parameter and let
  the `cli/` package resolve it. `analyze`'s `rack_folder` is the worked example.

## Domain layer

- `records.py` imports nothing from the package, so `_tables.py` and `model.py` can both
  depend on it without a cycle. That is the whole reason it is a separate file.
- `model.py` owns *which db is which*; `_tables.py` owns *what a library row means* and
  `_packs.py` *what a pack row means* (it reads a pack rig's fields from its payload through
  `_sysex`); `_sysex.py` owns the blob and imports none of them.
- `_archive.py` owns reading the zip. Every entry is read through `read_entry`, so a damaged,
  encrypted or oversized entry is refused in one place — `rename` reads through it too.
- `_sysex.py` decodes to `None` rather than guessing — see `anti-patterns.md`.

---

## Why this matters

- **The invariant.** Writing lives in exactly three files, so "nothing modifies a source" is
  provable by reading `services/edit.py`, `services/extract.py` and `services/census.py`
  (writer and guard together) and `model.write_refusal`, not audited everywhere.
- **Embeddability.** The library is stdlib-only, quiet, and importable — no logging config,
  no framework exceptions, no output — so it works from something other than this CLI.
- **Testability.** Services take records and return values, so they test against the
  in-memory fixture with no I/O and no hardware.
