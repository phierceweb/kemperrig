# Error Handling

**Every CLI failure is one line on stderr and a non-zero exit. Never a traceback.** That is
the promise in `CONTRIBUTING.md` and `CLAUDE.md`, and it is what these rules exist to keep.

The library raises **builtins**. It does not use `pf_core.exceptions` — those carry HTTP
semantics this project has no use for, and `tests/test_dependencies.py` pins the pf_core
surface to two symbols, so importing them turns the suite red.

---

## In the library — plain builtins

`model.py`, `_tables.py`, `_sysex.py`, `records.py` and `services/` raise builtins so the
package stays importable without adopting a framework hierarchy.

| Raise | When |
|---|---|
| `ValueError` | A value or file is malformed — an unreadable db, criteria of the wrong shape, an archive whose dbs are not where the layout expects |
| `KeyError` | A required table or column is absent |
| `FileNotFoundError` | A path is not a Rig Manager library (a subclass of `OSError`) |
| `OSError` | File I/O failed — let it propagate, don't wrap it |

The message is the whole user-facing error; the CLI prints it verbatim after `kemperrig: `.
Write it for the person holding the file — name the archive, the rig, or the criteria file
that failed, and where it can be, say what to do instead. `_mis_rooted` in `model.py` is the
model: it names the path, says what was wrong, and points at the fix.

There is no `errors.py` and no project-wide hierarchy. Define an exception only when a
caller must distinguish it from a builtin — nothing does today.

---

## The boundary

`main()` in `cli/__init__.py` is the only handler:

- `BrokenPipeError` → redirect stdout to devnull, return **0**. Piping into `head` is not
  an error.
- `(OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile, sqlite3.DatabaseError,
  ET.ParseError)` → print `kemperrig: {e}` to stderr, return **1**.
- `ap.error(...)` for a bad invocation (argparse exits **2**).
- A refused `rename`, `extract` or `summary --write-golden` returns **2** — the guard fired,
  nothing was attempted. `summary --force` without `--write-golden` is also a one-line exit 2.
  `extract` also exits 2 with no selection flags (a one-line message, not argparse usage).

`TypeError` and `AttributeError` are deliberately **not** caught: they mean a bug, and a
traceback is the right output for a bug. **The consequence is the rule that matters:**
anything the user authors — a criteria file above all — must be shape-checked where it is
read, so a wrong shape becomes a `ValueError` instead of a `TypeError` two layers down.
`load_criteria` is the worked example; it validates the top level, `amp_patterns`, and
`gain_min` before any of them reach `matches_amp`.

Don't widen the catch tuple to paper over a missing check.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Worked. Also `diff` on identical inputs, and `analyze`/`doctor` without `--strict`. |
| 1 | A failure, or a finding: `diff` differs, `analyze --strict` found something, `doctor --strict` found a definite defect. |
| 2 | Bad invocation, or a `rename`/`extract`/`--write-golden` guard refused. |

`diff`, `analyze --strict` and `doctor --strict` are meant to gate scripts. Don't add a new meaning to 1
without checking what it does to those.

---

## Catch patterns

### Pattern 1 — let it bubble (the default)
No `try` in services. `main()` handles it.

### Pattern 2 — convert at the layer that has the context
When the raw error would not name what failed, or is the wrong type for the boundary:

```python
except (MemoryError, sqlite3.Error) as e:
    con.close()
    raise ValueError(f"unreadable repositoryR2.db ({len(blob)} bytes): {e}")
```

A zero-byte db raises `MemoryError` out of `sqlite3.deserialize` — outside the tuple, so it
escaped as a traceback until `_load_db` converted it. Close what you opened first.

### Pattern 2b — one bad payload never ends a library-wide command
`_sysex.parse_tracks` / `parse_messages` / `parse_performance` catch the decoder's
`ValueError` and return None. A performance payload goes through `parse_performance`, which
also rejects any track count but six. `services/doctor.py` reports such a payload as broken;
`analyze`, `pages --all` and the census skip it and list it (`analyze --strict` fails on
it), `performances` shows no locked share for it, `rigs --decode` gives it a null `decode`,
`--effect` / `--ir` list it as unchecked (`services/select.py`, through
`decode.try_rig_detail`), and `extract` skips it with a note. A command about one rig (`rig`, `pages RIG`) lets the `ValueError` through
`services/decode.rig_messages`, which names the rig. Beyond those, `_packs` keeps a pack rig
whose payload does not parse undecoded, `rename` leaves such a payload as it is, and `doctor`
catches it to quote the error. Catch it nowhere else — and never with a bare `except`.

A track whose events stop before its end is not an error — a delta time cut off at the end
included: `_sysex.tracks` returns what it read, and `_sysex.walk` / `doctor`'s informational `unread_payloads` say where it stopped.
One real snapshot holds slot tracks like that (an encoded `.krig` body), so do not make
that strict without deciding what those are.

### Pattern 3 — never
```python
except Exception:
    pass
```
Silent swallowing turns a corrupt archive into a confident wrong answer. `None` beats a
guess, but only when the caller can tell it apart from a real value.
