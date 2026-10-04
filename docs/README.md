# kemperrig documentation

The index of every doc in this folder. Start with [capabilities.md](capabilities.md) for what
kemperrig does, [installation.md](installation.md) to set it up, and [cli.md](cli.md) for
the exact flags.

For AI assistants: the `kemper-rmbackup` skill (in `.ai/skills/`) condenses the format traps
these docs describe; `AGENTS.md` at the repository root is the guide for working on the code.

---

## Table of Contents

- [The docs](#the-docs)
- [Adding a doc](#adding-a-doc)

## The docs

| Doc | What it covers |
|---|---|
| [installation.md](installation.md) | Installing from PyPI or a clone, pointing kemperrig at a library, effect names, platforms |
| [capabilities.md](capabilities.md) | Everything kemperrig does, by the question you are asking: browse, decode, select by effect or IR, analyze, doctor, packs, diff and history, the writers, and what it does not do |
| [cli.md](cli.md) | Every command, flag, environment variable and exit code |
| [json.md](json.md) | Every `--json` document and shared shape, key by key |
| [python-api.md](python-api.md) | Using the library from a script: the layers, the records, the services, errors, writing, and adding a command |
| [criteria.md](criteria.md) | The `shortlist` criteria file: keys and what is refused |
| [census.md](census.md) | The census `summary --write-golden` writes, and the opt-in golden test |
| [format.md](format.md) | The `.rmbackup` container, snapshots, packs, and the SysEx inside rig and performance payloads |

`pf-core/`, when present, is a gitignored link to the installed pf-core's own docs, made by
`bin/run setup`.

## Adding a doc

Give it the structure the others share — a one-line purpose, the skill pointer where one
applies, a table of contents, and an "Adding a …" section where the system is extended —
and add its row above in the same change. `tests/test_docs.py` fails the build when a doc
is missing from this index or a link or anchor in `docs/` does not resolve.
