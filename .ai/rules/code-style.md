# Code Style

## General

- Python 3.12+ — use modern syntax (type unions with `|`, `match` where clearer).
- No star imports (`from x import *`).
- Imports grouped: stdlib → third-party → pf_core → project. One blank line between groups.
- Use `from __future__ import annotations` in files with forward references.

## File size

File-size budgets — a flat soft-WARN/hard-FAIL across `src` and `tests` — are enforced by the `pf_core.guards` build gate (`bin/run lint` + CI); the canonical limit values live in `pf_core/guards/config.py`, not in prose. Split past the soft target by concern. Per-directory guidance: `project-structure.md`. Gate mechanics: `docs/pf-core/guards.md` (symlink `bin/run setup` creates).

## Naming

- Files: `snake_case.py`. Private modules prefixed with `_` (e.g. `_sysex.py`).
- Classes: `PascalCase`. Exceptions end with `Error` or `Exception`.
- Functions/methods: `snake_case`. Private prefixed with `_`.
- Constants: `UPPER_SNAKE_CASE`.

## Functions

- A service function takes a `Backup` (or the decoded messages) first and returns plain dicts, lists, dataclasses, or primitives. The reader never mutates what it read; the three writers build new files (`rename` an archive, `extract` `.krig` files, `census.write` a JSON census); the first two return a count.
- Use keyword-only arguments for functions with more than 2 parameters.

## Type hints

- All public function signatures must have type hints.
- Use `dict`, `list`, `tuple` (lowercase) not `Dict`, `List`, `Tuple`.
- Use `X | None` not `Optional[X]`.

## Docstrings and comments

- Required on: modules, public classes, public functions with non-obvious behaviour.
- Not required on: private helpers, obvious getters/setters, test functions.
- **Terse prose, not Google-style sections.** No `Args:`/`Returns:`/`Raises:` blocks — the
  signature and the type hints already say that. One or two lines carrying what the code
  cannot: the non-obvious why, an invariant, a trap.
- Default is **no comment**. Never dev history (`Phase 3`, `moved from`, `previously`),
  never a justification essay, never a calibration war story — see `anti-patterns.md`.

## Error handling

- See `error-handling.md` — everything raises plain builtins; `main()` in the `cli/` package is the only handler. Never raise bare `Exception` anywhere.
- Never swallow exceptions silently (`except Exception: pass`).

## Logging and output

- Nothing logs — see `logging.md`. There is no logger in this package.
- User-facing `print()` belongs in the `cli/` package, `_views/`, and `_json/` only.
