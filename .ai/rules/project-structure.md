# Project Structure

kemperrig is a library + CLI in src-layout. No web layer, no database, no migrations —
adding one is out of scope (`scope.md`).

```
kemperrig/
├── src/kemperrig/              # Importable package (src-layout)
│   ├── records.py              # Rig/Performance/Slot/Preset/Info — dataclasses only
│   ├── _tables.py              # SQLite rows in, records out
│   ├── _packs.py               # rig/preset pack rows in, a Pack record out
│   ├── model.py                # Backup — the container and its entry points (zip / live / snapshot / pack)
│   ├── _archive.py             # open the zip, read one entry, bounded and damage-checked
│   ├── _sysex.py               # KThd/KTrk blob decode
│   ├── _sysex_effects.py       # module blocks: raw pages, effect chains
│   ├── _sysex_edit.py          # rewrite one string in a blob, byte-for-byte
│   ├── cli/                    # __init__.py: main — argparse, env, exception boundary
│   │                           #   _library _curation _doctor _pages _packs _compare _write: one per concern
│   ├── _views/                 # text presentation; __init__ re-exports render_*
│   │                           #   _library _curation _doctor _pages _packs _compare: one per command group
│   ├── _json/                  # machine-readable presentation, one module per command group
│   └── services/               # report, filter, select, shortlist, analyze, doctor,
│                               #   performance, decode, pages, pack, diff, history, census,
│                               #   edit, extract
├── config/                     # example-shortlist.json — criteria are data, not code
├── docs/format.md              # the container, the tables, the SysEx framing
├── bin/run                     # Venv wrapper — setup / pytest / lint / kemperrig / sample
├── AGENTS.md, CLAUDE.md        # the agent guide (CLAUDE.md imports AGENTS.md)
├── .ai/rules/, .ai/skills/    # tracked rules and the format skill; .ai/plans/ is local
├── MANIFEST.in                 # sdist extras — tests/_fixture.py is not implicit
├── .env, CLAUDE.local.md       # local only: KEMPERRIG_* settings; private agent notes
└── tests/                      # hermetic: _payloads / _fixture / _pack_fixture build files,
                                #   _sample.py a whole library on disk
```

**Flat until a directory is earned.** `records.py`, `_tables.py` and `model.py` are three
files, not a `domain/` package wrapping them. Promote a concern to a directory once it holds
two or more modules; a lone module stays a flat file. This keeps a small tool from carrying
empty scaffolding.

`records.py` exists to break a cycle, not for tidiness: `_tables.py` builds the dataclasses
and `model.py` needs both, so the dataclasses live below both.

## Key conventions

- **One concern per file.** Each `services/` module owns exactly one — reporting, analysis,
  filtering, shortlisting, diffing, renaming. If a name needs "and" in it, it is two files.
- **No `sys.path` hacks.** src-layout plus an editable install (`bin/run setup`).
- **No config module.** Runtime input is CLI arguments, with `KEMPERRIG_*` env vars read
  through `pf_core.utils.env.resolve_str` in the `cli/` package as the fallback. Services never read
  the environment — they take the resolved value as a parameter (`analyze`'s `rack_folder`).
- **Nothing about one person's rig is a constant.** A library path, a criteria file, a
  folder name someone can rename in Rig Manager: all resolve at the boundary. Format
  constants (`Local Library/`, Preset Class `6`) are the opposite — they are the spec, and
  they stay in the domain modules (`_tables.py`; Preset Class in `records.py`).
- **Layer direction is enforced by review, not imports.** See `layering.md`.

## File size limits

The build gate (`python -m pf_core.guards`, run by `bin/run lint` and by CI) enforces a
flat soft-WARN / hard-FAIL budget across `src` and `tests`. **The canonical
limit values are code, not this doc:** the `GuardsConfig` defaults in
`pf_core/guards/config.py`. Split past the soft target by concern.

| Over its limit | Action |
|---|---|
| A `services/` module | Split by concern: `{domain}_{concern}.py` (e.g. `analyze_orphans.py`, `analyze_coverage.py`) |
| `model.py` | Split by concern, as `records.py` / `_tables.py` / `model.py` already were |
| A `cli/` module | Move display code to `_views/` / `_json/`; a command's logic belongs in its service; a new command group gets its own `_<concern>.py` |
| A `_views/` module | Split by command group; re-export from `_views/__init__.py` |
| A `_json/` module | Split by command group; re-export from `_json/__init__.py` |

No baseline table exists and none should be added — if a file is over the limit, split it.

When splitting a file:
- Name the new files `{domain}_{concern}.py` — not `{domain}_2.py` or `{domain}_helpers.py`
- Update the package `__init__.py` to re-export if needed
- `grep -r` the old import paths to catch all callers

## Dependency on pf-core

In `pyproject.toml`:
```toml
[project]
dependencies = [
    "pf-core~=0.25.0",  # pin the current minor (see CHANGELOG)
]
```

Only foundation helpers are imported, and only where `framework-first.md` allows. No
`[web]` or `[db]` extras — this project has neither.
