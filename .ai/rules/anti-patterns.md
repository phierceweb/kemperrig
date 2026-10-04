# Anti-Patterns

Concrete examples of what NOT to do, each paired with the focused alternative. Each names the rule it violates; see that rule for the full standard.

---

## No write that can reach a source path

The invariant. There are three writers and all write **new** files: `services/edit.py`
builds a new archive, `services/extract.py` writes `.krig` files, `services/census.py` a JSON
census. A `.rmbackup` is often the
only copy of a library someone has. `cli/_write.py` refuses a rename output that aliases the
source — case variants, symlinks, hardlinks, `..` — and an existing output without
`--force`; `extract.refusal` (which `extract.write` re-checks itself) refuses a folder that
is or lies inside the source or any Rig Manager tree (`model.library_root`), an output file
that is the source even with `--force`, and existing files without it; `census.refusal`
does the same for its one file, and refuses a folder.

```python
# WRONG — a string compare misses every alias; on a case-insensitive filesystem
# `lib.rmbackup` and `Lib.rmbackup` are one file, and the source is destroyed
if os.path.abspath(out) == os.path.abspath(src):

# RIGHT — identity, not spelling
os.path.samefile(a, b)                       # and Path.resolve() when b does not exist yet
```

Reading is safe by construction too: every db is `sqlite3.deserialize`d from bytes into
`:memory:`, so nothing is extracted, no `-wal`/`-shm` sidecar lands beside a live library,
and zip-slip is impossible. Don't introduce a code path that extracts to disk.

---

## No guessed decode

A plausible-looking offset is not a finding. If a value cannot be established from a real
file or confirmed in Rig Manager, decode it as `None`.

```python
# WRONG — an unlisted reverb type named from the stomp enum. Different namespace,
# so this confidently prints the wrong effect.
name = EFFECT_TYPES.get(type_value, "Unknown")

# RIGHT — None, and the renderer shows the raw number
name = REVERB_TYPES.get(type_value)
```

The same applies to a docstring: don't claim a decode "matches exactly" unless it does.

---

## No format constants outside `_tables.py` / `_sysex*.py`

`Local Library/`, `/repositoryR2.db`, Preset Class `6`, page `0x4b`, the amp-block shapes
and the 14-bit gain scale have exactly one home. (Preset Class `6` lives in `records.py`, beside the
`is_cab_ir` property that reads it — records import nothing from the package.) A service that hardcodes one drifts the
moment the format detail moves. (See `layering.md`.)

**The converse matters as much:** anything about *one person's* rig is not a format
constant. A library path, a criteria file, a folder name someone can rename in Rig Manager
— those resolve at the CLI boundary from a flag or a `KEMPERRIG_*` env var.

```python
# WRONG — one person's folder name, baked in, silently mis-counting for everyone else
_ON_DEVICE_FOLDER = "On Device"

# ALSO WRONG — same name, now merely the default. It still ships in a public repo and
# still mis-counts for anyone who filed their rigs differently.
def orphaned_rigs(backup, *, rack_folder=DEFAULT_RACK_FOLDER): ...

# RIGHT — no default. The caller names it, or nothing is exempt.
def orphaned_rigs(backup, *, rack_folder: str | None = None): ...
```

When you catch yourself picking a default, ask where the value came from. If the answer is
"this machine's library", there is no honest default — only a setting.

---

## No silent fallback on user-authored input

The criteria file is the one thing the user writes by hand, and the boundary catches
format errors, not type errors. Validate the shape where you read it.

```python
# WRONG — a bare string passes the truthiness check, then matches character by character,
# so "Recto" matches any amp containing r, e, c, t or o. No error, wrong answer.
if not crit.get("amp_patterns"):
    raise ValueError(...)

# RIGHT — reject the shape, name the file, say what was expected
raise ValueError(f"{path}: amp_patterns must be a list of strings, got a string")
```

An empty result the user asked for is fine. An empty result caused by a silently
misread config is not.

---

## No drift between `_views/` and `_json/`

They are two renderings of the same data. When a field appears in one, decide deliberately
whether it belongs in the other — `--json` is how a whole library leaves the terminal, and
a field only the text view has is invisible to every script.

---

## No logging or `print()` in the library

`records.py`, `_tables.py`, `model.py`, `_sysex.py` and `services/` stay quiet and
importable — no `setup_logging`, no `get_logger`, no `print()`. Return a value or raise; the
CLI decides how it reaches the user. (See `framework-first.md`, `logging.md`.)

---

## No `pf_core.exceptions` raised anywhere

The library *and* the CLI raise plain builtins. `tests/test_dependencies.py` pins the
pf-core surface to `resolve_str` in the `cli/` package and `atomic_write_bytes` in
the three writers (`services/edit.py`, `services/extract.py`, `services/census.py`); importing an exception class fails the gate. (See `error-handling.md`.)

---

## No personal detail in a tracked file

This repo is public. A library count, a rig or pack name, an author handle, an absolute
path — none of it belongs in source, a docstring, a comment, a test fixture, or the
CHANGELOG. "Verified across N rigs" is a leak wearing a lab coat.

```python
# WRONG — a library size and a commercial pack, in a shipping docstring
"""Empirically verified r=1.0000 across 1,234 rigs ... e.g. the Acme Lead type-20 pack"""

# RIGHT — the rule, without the private calibration data
"""Returns None for rigs on non-standard profile formats (Profile Type != 1)."""
```

---

## No dev history in comments

No `Phase 3`, no `moved from`, no `previously`, no `as of v2`, no session anecdotes. Current
behaviour only; the changelog is the changelog.

---

## No project exception hierarchy

There is no `errors.py`, and no service defines its own exception today. Add one only when
a caller must distinguish it from a builtin — nothing does. Don't add a parallel hierarchy
for errors the CLI already handles by type.

---

## No hand-edited fixtures

`tests/_fixture.py` builds archives byte by byte — real SQLite tables, real KThd/KTrk
framing. Committing a real `.rmbackup` leaks someone's library and usually licensed
commercial profiles. Extend the fixture instead. (See `testing.md`.)

---

## No god-module in `_views/`

`_views/` formats read-only output and nothing else. It carries the same size budget as
every other file (`project-structure.md`), and the gate warns long before it becomes a
problem — but the tell is content, not line count. Decoding, database lookups, or branching
on library state appearing there means a service's job leaked upward.

```
# WRONG — one module doing formatting, decoding, and analysis
src/kemperrig/_views/_library.py

# RIGHT — each part sits in the layer that owns it
src/kemperrig/_views/*.py          (formatting only)
src/kemperrig/_sysex.py            (decode_* helpers)
src/kemperrig/services/analyze.py  (what counts as an orphan)
```

---

## No business logic in utility files

If a function makes decisions, transforms library data, or coordinates multiple operations,
it belongs in a service — not in `_views/` or a `_helpers.py`.

---

## No copy-pasting between files

If two services need the same logic, extract it into the service that owns that concern
and import it. Don't duplicate.

---

## Also forbidden — full standard in the cross-referenced rule

- `os.environ` reads outside the `cli/` package → `framework-first.md` (use `pf_core.utils.env`, at the CLI boundary only).
- Files over the size limits ("monster files") → `project-structure.md` (split by concern; enforced by the `pf_core.guards` gate).
- A code change that leaves `README.md` or `CHANGELOG.md` describing the old behaviour → `docs-sync.md`.
