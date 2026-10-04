# Framework First

Before writing a utility, check whether pf-core already has it. The module index is
`docs/pf-core/modules.md` — a symlink into the installed framework's own docs, so it is
never out of date with the version in the venv. Recreate it with:

```bash
ln -sfn "$(bin/run python -c 'import pf_core, pathlib; print(pathlib.Path(pf_core.__file__).parent / "docs")')" docs/pf-core
```

A framework's surface is larger than one session's memory of it. Check before hand-rolling.

## But this project's default is stdlib

kemperrig is a read-only reader whose core is stdlib-only, and
`tests/test_dependencies.py` pins the pf-core surface to **two symbols, each in named files**:

| Symbol | Where | Why |
|---|---|---|
| `pf_core.utils.env.resolve_str` | `cli/__init__.py`, `cli/_curation.py` | `KEMPERRIG_*` fallbacks, so no personal path is baked in |
| `pf_core.utils.io.atomic_write_bytes` | `services/edit.py`, `services/extract.py`, `services/census.py` | the three writers; a torn write must not produce a half archive, `.krig` or census |

Adding a third import — anywhere, including a different file for one of these two — fails
the gate. That is the point: it forces the widening to be a decision, made in the same
commit, rather than something that arrives with a patch.

## What NOT to adopt, and why

| Tempting | Don't, because |
|---|---|
| `pf_core.exceptions` | Its hierarchy carries HTTP status semantics. There is no web layer here; the boundary catches builtins and prints one line (`error-handling.md`). |
| `pf_core.log` / `setup_logging` | The package has no logging at all, deliberately (`logging.md`). |
| `pf_core.output.ConsoleReporter` | Pulls Rich into a package that promises stdlib-only, to replace `print()` from one file. |
| `pf_core.utils.json.safe_json_loads` | It returns a *fallback* on bad input. This project wants a hard, named error — `load_criteria` validates shape and raises. |
| `pf_core.db`, `alembic`, `web`, `jobs` | Out of scope (`scope.md`). |

`pf_core.utils.io.atomic_write_json` and `pf_core.utils.config_path.resolve_config_path`
are plausible future fits — the first if anything ever writes a JSON sidecar, the second if
the criteria file grows a bundled-default lookup. Neither is used today. Adopting either is
a `test_dependencies.py` change plus a line here.

## Where the boundary sits

The library (`model.py`, `_tables.py`, `_sysex.py`, `records.py`, `services/`) raises plain
builtins and does no logging. A bare `ValueError` in a service is correct, not a violation.

`print()` belongs in the `cli/` package, `_views/`, and `_json/` only.
