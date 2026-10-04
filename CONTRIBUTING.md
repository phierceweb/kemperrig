# Contributing to kemperrig

Bug reports, format findings, and fixes verified against real files are all welcome.

## The property that matters

kemperrig only reads. `.rmbackup` archives are the only copy of a profile library many people
have, so nothing here modifies a source file. The three writers build new files — `rename` a
new archive, `extract` standalone `.krig` files, `summary --write-golden` a JSON census —
outside the source and any Rig Manager library, each behind a guard that starts from
`model.write_refusal`. A change that writes in place will not be merged.

## Setting up

```bash
git clone https://github.com/phierceweb/kemperrig && cd kemperrig
bin/run setup               # venv + editable install with the dev tools
bin/run pytest              # the suite
bin/run lint                # ruff + the pf-core file-size gate
.venv/bin/pre-commit install   # optional: run ruff and the gate on every commit
```

`bin/run` reads a gitignored `.env` for your own `KEMPERRIG_*` settings; see `.env.example`.

## How the tests work

Every test is hermetic. `tests/_payloads.py` builds real Kemper SysEx in KThd/KTrk chunks,
`tests/_fixture.py` real `.rmbackup` archives and snapshots from them, and
`tests/_pack_fixture.py` real packs — so nothing depends on a personal library, and nothing
from one is ever committed.

`tests/_sample.py` writes a whole synthetic library to disk: a backup, a live directory with
two dated snapshots, a rig pack and a preset pack, and one of each thing `analyze` and
`doctor` report. `tests/test_smoke.py` runs every command against it, and

```bash
bin/run sample /tmp/sample
```

writes one for you to try commands on by hand. When a change needs a case the sample lacks,
extend the sample rather than reaching for a real file.

One check is opt-in. With `KEMPERRIG_GOLDEN` naming a census written by
`summary --write-golden` and `KEMPERRIG_LIBRARY` the library it describes,
`tests/test_golden.py` compares the two field by field. Without both it skips; `bin/run
pytest -rs` says why. See `docs/census.md`.

`tests/test_docs.py` checks `docs/cli.md` and `docs/json.md` against the code, so a new
command, flag or `--json` key needs its documentation in the same change.

## Reporting a decode bug

Rig Manager writes several generations of payload, and not all of them are understood. If
a rig or performance decodes wrongly, please include the Rig Manager version, the Profiler
model and OS version, the command you ran, and the value Rig Manager or the Profiler shows.
**Do not attach the backup, a pack or a `.krig`** — they usually hold commercially licensed
profiles, and an issue is public.

## House rules

- **Verify against a real file.** A decoding claim needs evidence: a value Rig Manager
  displays, or a Profiler that agrees. A plausible-looking offset is not a finding; an
  unverified value decodes to `None`.
- **Keep the core dependency-light.** The standard library plus two pf-core helpers,
  enforced by `tests/test_dependencies.py`. A new dependency needs a reason.
- **Fixtures stay synthetic.** Never commit a real `.rmbackup` or pack, and never commit
  identifying details from one — rig names, author handles, library counts.
- **One-line errors.** Every CLI failure is one line on stderr and a non-zero exit, never a
  traceback.
- **File-size target 300 lines, hard limit 500**, one concern per file.
- The rules behind these, and the layering they protect, are in `.ai/rules/`; `AGENTS.md`
  is the short version.

## License

kemperrig is licensed under the Apache License, Version 2.0. By contributing, you agree
that your contributions are licensed under the same terms.
