# Testing

## The anchor

**Nothing modifies a source archive.** A `.rmbackup` is often the only copy of a library
someone has. Every writer test asserts the source is byte-identical afterwards, and the
alias cases (case-variant path, symlink) are covered because a plain string compare misses
them. A change that lets a write reach the source is a bug no matter what else it fixes.

## Fixtures, not the author's machine

Tests must pass on a fresh clone with no hardware and no user files. `tests/_payloads.py`
builds real KThd/KTrk SysEx and `tests/_fixture.py` a real `.rmbackup` from it — real SQLite
tables — so the suite is fully hermetic. `tests/_sample.py` writes a whole library to disk
(backup, live tree, snapshots, packs, one of each finding); `tests/test_smoke.py` runs every
command against it, and `bin/run sample DIR` writes one to try by hand. `tests/conftest.py`
pins the effect-name table, so the results do not depend on Rig Manager being installed. Never commit a real `.rmbackup`, and never commit a detail
taken from one (library counts, rig or performance names, author handles, pack names).

Anything needing a real library is **opt-in** behind `KEMPERRIG_LIBRARY` and must skip
cleanly without it. A test that reads `~/Library` unguarded is the failure mode to watch
for — it passes for one person and hard-fails for everyone else.

The one such test is `tests/test_golden.py`: it compares `KEMPERRIG_LIBRARY` with the census
`KEMPERRIG_GOLDEN` names (written by `summary --write-golden`), one subtest per field, and
skips unless both are set and exist. It decides the skip at run time, so hermetic tests in
the same file drive it against fixtures (pass, fail, skip). `bin/run` sources `.env`, so it
runs there; to see the skip, call `.venv/bin/pytest` with both variables unset. A mismatch
after an intended library change means regenerate the census — never relax a field.

## Silent skips are worse than failures

A `skipIf` that fires on a fresh clone reads as green while proving nothing. Every skip
must be deliberate and named. Check with:

```bash
bin/run pytest -rs
```

## The error paths are the point

This tool gets pointed at files it did not write. A malformed archive, a corrupt database,
a directory that is not a Rig Manager tree, and bad criteria JSON each have a test
asserting a **one-line message and a non-zero exit** — never a traceback. Coverage that is
high because the happy path is thorough and the error paths are dead is not coverage.

## Synthetic truth has a ceiling

The fixture writes every byte the tests read, so a wrong assumption baked into it is
invisible. Decoding claims need a real file or Rig Manager agreeing; `None` beats a guess.
