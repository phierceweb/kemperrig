# Logging

**There is none, and that is deliberate.** The package has no `import logging`, no
`pf_core.log`, no structlog, no logger anywhere. A read-only CLI that prints its result has
nothing to log, and `tests/test_dependencies.py` pins the pf_core surface to
`resolve_str` + `atomic_write_bytes` — adding `setup_logging` or `get_logger` turns the
suite red.

`model.py`, `_tables.py`, `_sysex.py`, `records.py` and `services/` neither log nor
`print()`. They return values or raise; the `cli/` package decides what the user sees
(`layering.md`, `error-handling.md`).

## What to do instead

| You want to | Do this |
|---|---|
| Tell the user something | `print()` from the `cli/` package, via `_views/` / `_json/` |
| Report a failure | Raise a builtin with a message that names the file; the boundary prints one line |
| Say a value could not be decoded | Return `None` and let the renderer show `-` or `?` — never invent a value |
| Debug a decode | A throwaway script against `tests/_fixture.py`, not a log line left behind |

## stdout stays clean

`--json` output must be parseable, so nothing may write to stdout except the document
itself. Diagnostics go to stderr. This is why `BrokenPipeError` is handled rather than
allowed to print a shutdown message.

## If logging ever becomes necessary

It would be a deliberate widening of `test_dependencies.py` in the same commit, plus a
reason recorded here — not a line added in passing. The bar: something happens that the
user cannot see and cannot reproduce. Nothing in a read-only reader clears it.
