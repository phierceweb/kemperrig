# The library census

What `summary --write-golden` writes, and how the opt-in golden test uses it to catch a
decode that breaks against your own library.

For AI assistants: the `kemper-rmbackup` skill says how to read a census diff after a
decode change — a moved field is a regression or an intended change, never a reason to
relax the test.

---

## Table of Contents

- [Why it exists](#why-it-exists)
- [Writing one](#writing-one)
- [Keys](#keys)
- [The golden test](#the-golden-test)
- [Keep it private](#keep-it-private)
- [Adding a census field](#adding-a-census-field)

## Why it exists

The test suite is hermetic: it builds every file it reads, so a wrong assumption baked
into those fixtures is invisible to it. A census is a snapshot of what kemperrig reads
from a **real** library — the totals and the numbers that move when a decode breaks. Write
one while you trust the output; after a Rig Manager update or a kemperrig upgrade, the
golden test compares the library with it field by field.

## Writing one

```bash
kemperrig summary "<backup or live directory>" --write-golden census.json
kemperrig summary --write-golden census.json --force    # replace it, KEMPERRIG_LIBRARY as the source
```

Keys are sorted and floats rounded, so the same library always writes the same bytes and
two censuses diff cleanly. Missing folders on the way to the path are created.

Do not point it at anything precious: the write is refused, exit 2, for the source itself
(even with `--force`), a path inside the source or any Rig Manager library, a folder, and an
existing file without `--force`.

## Keys

| Key | Holds |
|---|---|
| `_comment` | what the file is and who writes it |
| `census` | the census format number, `1` |
| `user` | the user the backup records; `null` for a live directory |
| `totals` | rigs, DI, studio, performances, slots, presets, cab IRs, distinct amp models and authors |
| `gain` | `summary`'s `min`, `max`, `mean` and `bands`, plus how many rigs' amp gain `decoded` and how many did not |
| `profile_types` | per Profile Type: rigs, amp-gain decodes, and — for every type but the most common — the folders they are filed in |
| `effects` | per module slot, how many rigs have a decoded effect loaded there |
| `effects_undecoded` | per module slot, how many rigs hold that slot only in the undecoded function-`08` framing |
| `doctor` | the count of each `doctor` finding |
| `rig` | a sample rig — the first by name, then folder, whose payload parses: its first decoded strings, gain, amp gain and effects |
| `performance` | a sample performance: its slots, tracks, locked-effects share, cab IR and gain ladder |

## The golden test

`tests/test_golden.py` runs when two settings name real files:

```bash
KEMPERRIG_GOLDEN=/path/to/census.json
KEMPERRIG_LIBRARY="/path/to/your/library"
```

It compares the library with the census one field at a time, so a failure names what
moved. Without both settings it skips, and `bin/run pytest -rs` says why — a fresh clone
always skips it. Put both in a gitignored `.env`; `bin/run` reads it.

When it fails:

- If the library changed on purpose, rewrite the census with `--force` and review the diff.
- If kemperrig changed, decide from the diff whether the change is intended. A census
  written by an older census format fails on its `census` key: regenerate it.
- Never loosen a comparison to make it pass.

## Keep it private

A census names your rigs and counts your library. Keep it with your own files, never in
a public repository — the file's own `_comment` says so.

## Adding a census field

1. Compute it in `services/census.py` (`take`) from what the library already decodes.
2. Write it in `src/kemperrig/_json/_census.py`; bump `CENSUS_FORMAT` if an existing
   census would no longer compare cleanly.
3. Add a row to [Keys](#keys) — `tests/test_docs.py` checks this table against a real census
   of the sample library.
4. Cover it in `tests/test_census.py`, and let `tests/test_golden.py` compare it field by
   field like the rest.
