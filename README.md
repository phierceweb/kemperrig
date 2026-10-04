# kemperrig

[![PyPI](https://img.shields.io/pypi/v/kemperrig)](https://pypi.org/project/kemperrig/)

Read a Kemper Profiler **Rig Manager** library — a `.rmbackup` backup, the live Rig Manager
directory, its dated snapshots, or a rig or preset pack — and get at what is actually in it:
rigs and their amp metadata, performances and their slots, effect and cab-IR presets, and
the SysEx payload inside every rig.

## Why kemperrig

Rig Manager shows one rig at a time. A library grows pack by pack and download by download,
and questions about the whole of it — which rigs are dead weight, which performance slots
point at rigs that are gone, which rigs carry a delay — mean opening rigs one by one.
kemperrig reads the whole library at once and answers them:

- **Which rigs no performance uses.** `analyze` lists orphans, amps with no clean or no
  high-gain rig, byte-identical duplicates, and performances whose slots do not climb in
  gain.
- **Which performance slots point at a rig that is gone.** A slot keeps its own copy of the
  rig it was built from, so it still plays after the rig is renamed or deleted. `doctor`
  finds those slots, and payloads that are damaged.
- **Which rigs carry a delay, or load a given cab IR.** `rigs --effect delay` and
  `rigs --ir V30` read the decoded payload, not just the metadata columns.
- **Which snapshot still holds the version before an edit.** `history --rig NAME` walks Rig
  Manager's dated snapshots and numbers each distinct version of the rig.
- **Which rigs in a pack the library already has.** `pack --against` compares payloads, so a
  renamed copy is still recognized.
- **What changed between two backups.** `diff` lists rigs, performances and presets added,
  removed and changed, field by field, and exits 1 when they differ.

This is `doctor` on the synthetic library `bin/run sample` writes, which holds one of each
problem on purpose:

```text
$ kemperrig doctor Library.rmbackup
doctor: 8 rigs · 3 performances, 7 slots · 2 cab IRs
definite (--strict exits 1 on any)
  dangling slots: 1  (no library rig has the name)
    Mixed Set · slot 3 · 'Gone Rig'
  ambiguous slots: 0  (rigs with different payloads share the name)
  broken payloads: 1
    rig Amps/Recto/Broken Rig — truncated blob: a KTrk chunk declares 71 bytes, 67 present
informational
  payloads with bytes nothing reads: 0  (damage, or an encoding not decoded)
  amp gain differs from the payload: 0
  name differs from the payload: 0
  unused cab IRs: 1 of 2  (no rig or slot loads them)
    Local Library/Cab Greenback
```

## What it is

A `.rmbackup` is a zip of SQLite databases, and every rig in it carries a binary payload —
the `.krig` the Profiler loads, a stream of Kemper SysEx messages. kemperrig reads the
databases for the metadata Rig Manager shows, and decodes the payloads for what it does not:
the amp gain as stored in the amp block, the effect in each module slot, the cab IR a rig
loads, and every string inside. Kemper publishes no specification for either layer, so
everything decoded was established from real files, and a value that has not been decodes to
`null` rather than a guess.

| Source | Read by |
|---|---|
| `.rmbackup` | every read command, `diff`, `history`, and the writers |
| the live Rig Manager directory | every read command, `diff`, `extract`; `history` reads its `Backups/` |
| a dated snapshot (`Backups/*R2.db`) | every read command, `diff`, `history`, `extract` |
| a rig or preset pack | every read command, `pack`, `diff`, `extract` |

Every read command takes `--json`. Its documents are specified key by key in
[docs/json.md](https://github.com/phierceweb/kemperrig/blob/main/docs/json.md), and a test
keeps that page in step with the code.

## Safety

A backup is often the only copy of someone's profile library, so kemperrig only reads. Three
commands write, and each writes **new** files only: `rename` writes a new archive, `extract`
writes `.krig` files, and `summary --write-golden` writes a census. Each refuses, before
writing anything, an output that is the source — case variants, symlinks, hardlinks and `..`
included — or that lies inside any Rig Manager library, and an existing file without
`--force`. Databases are read into memory from the file's bytes; nothing is extracted beside
a live library.

## Scope

- **Reads** `.rmbackup` archives, the live Rig Manager directory, its dated snapshots, and
  rig and preset packs.
- **Decodes** rig, performance and preset metadata, and rig payloads: amp gain, effect
  chains, cab IRs, strings.
- **Writes** only through `rename`, `extract` and `summary --write-golden`, never inside a
  source or a Rig Manager library.
- **Does not** talk to the Profiler, change a library in place, or decode the profile's DSP
  model or knob values beyond the amp gain.

## How it relates to Rig Manager

| Tool | What it is | How kemperrig relates |
|---|---|---|
| Rig Manager | Kemper's library editor; it writes every file kemperrig reads | kemperrig reads its backups and its library folder, never changes them, and reads its `Stomps.xml` for effect names |
| Rig Exchange | Kemper's rig-sharing service, browsed from Rig Manager | rigs downloaded from it are ordinary library rigs to kemperrig |
| The Profiler | The hardware the rigs play on | kemperrig never talks to it; `doctor --device-backup` reads a backup of what is on it |

## Install

```bash
pipx install kemperrig
```

Or `pip install kemperrig` into a virtual environment. Python 3.12 or newer, one dependency
([pf-core](https://pypi.org/project/pf-core/)). Tested on macOS and Linux; Windows is
untested. Effect names are read at runtime from your own Rig Manager install, so nothing of
Kemper's ships here. Setup, settings and platforms:
[docs/installation.md](https://github.com/phierceweb/kemperrig/blob/main/docs/installation.md).

## Commands

```bash
kemperrig summary      [SOURCE]                       # counts, gain bands, amps, authors
kemperrig rigs         [SOURCE] [filters] [--decode]  # filter by metadata, --effect, --ir
kemperrig rig          [SOURCE] NAME                  # one rig's metadata and decoded payload
kemperrig presets      [SOURCE]                       # effect and cab-IR presets
kemperrig performances [SOURCE]                       # slots, gain ladders, locked effects
kemperrig pages        [SOURCE] (RIG | --all)         # raw parameter blocks
kemperrig analyze      [SOURCE] [--strict]            # orphans, coverage, duplicates
kemperrig doctor       [SOURCE] [--strict]            # dangling slots, broken payloads
kemperrig shortlist    [SOURCE] --criteria FILE       # rigs on chosen amps above a gain floor
kemperrig pack         PACKFILE [--against [LIBRARY]] # a pack, and what you already have
kemperrig diff         BEFORE AFTER                   # what changed between two sources
kemperrig history      [SOURCE ...] [--rig NAME]      # a library across dated snapshots
kemperrig rename       [SOURCE] OLD NEW -o NEW.rmbackup     # a renamed copy
kemperrig extract      [SOURCE] -o DIR (--all | filters)    # rigs as .krig files
kemperrig summary      [SOURCE] --write-golden census.json  # a census to test against
```

Set `KEMPERRIG_LIBRARY` and `SOURCE` becomes optional. Every flag, environment variable and
exit code is in [docs/cli.md](https://github.com/phierceweb/kemperrig/blob/main/docs/cli.md);
what each command reports, by job, is in
[docs/capabilities.md](https://github.com/phierceweb/kemperrig/blob/main/docs/capabilities.md).

## Use it from Python

```python
from kemperrig import Backup
from kemperrig.services.select import select_rigs

lib = Backup.open("2026-06-03 - Library.rmbackup")
picked = select_rigs(lib.rigs, effect="delay", gain_min=6.0)
for rig in picked.rigs:
    print(rig.path, rig.gain)
print("not checked:", [r.path for r in picked.unparsed])
```

The library is standard-library only, prints nothing, and raises plain builtins. The map:
[docs/python-api.md](https://github.com/phierceweb/kemperrig/blob/main/docs/python-api.md).

## Working from a checkout

```bash
git clone https://github.com/phierceweb/kemperrig && cd kemperrig
bin/run setup               # venv, editable install
bin/run pytest              # the suite — hermetic, needs no library
bin/run lint                # ruff + the pf-core file-size gate
bin/run sample /tmp/sample  # a synthetic library to try every command on
```

The tests build every file they read — real SQLite tables and real SysEx framing — so no
test needs a personal library. One check is opt-in: with `KEMPERRIG_GOLDEN` naming a census
and `KEMPERRIG_LIBRARY` the library it describes, the suite compares the two field by field
([docs/census.md](https://github.com/phierceweb/kemperrig/blob/main/docs/census.md)).

## Docs

[docs/README.md](https://github.com/phierceweb/kemperrig/blob/main/docs/README.md) is the
index.

- [installation.md](https://github.com/phierceweb/kemperrig/blob/main/docs/installation.md) — installing, pointing it at a library, effect names, platforms
- [capabilities.md](https://github.com/phierceweb/kemperrig/blob/main/docs/capabilities.md) — everything it does, by the question you are asking
- [cli.md](https://github.com/phierceweb/kemperrig/blob/main/docs/cli.md) — every command, flag, environment variable and exit code
- [json.md](https://github.com/phierceweb/kemperrig/blob/main/docs/json.md) — every `--json` document, key by key
- [python-api.md](https://github.com/phierceweb/kemperrig/blob/main/docs/python-api.md) — the library from a script
- [criteria.md](https://github.com/phierceweb/kemperrig/blob/main/docs/criteria.md) — the `shortlist` criteria file
- [census.md](https://github.com/phierceweb/kemperrig/blob/main/docs/census.md) — the library census and the golden test
- [format.md](https://github.com/phierceweb/kemperrig/blob/main/docs/format.md) — the container, the tables, and the SysEx inside a payload

## Status

The decodes were established on one maintainer's library — its backups, dated snapshots and
installed packs — and on rigs published through Rig Exchange, each checked against the
metadata Rig Manager stores or the values it shows. Libraries from other Rig Manager versions, or built differently, may hold
layouts nobody has seen yet; those decode to `null`, and a bug report saying what Rig
Manager shows is the most useful thing to send.

Not yet established:

- the layout of function-`08` effect blocks — such slots are reported as undecoded;
- whether an archive written by `rename` restores into Rig Manager;
- Windows: kemperrig is untested there — see
  [Platforms](https://github.com/phierceweb/kemperrig/blob/main/docs/installation.md#platforms).

## Built on pf-core

kemperrig is built on [pf-core](https://github.com/phierceweb/pf-core)
([PyPI](https://pypi.org/project/pf-core/)), a Python foundation for LLM-facing
applications. kemperrig uses two of its utilities — atomic file writes and
environment-variable resolution — and its structural gate, which fails the build when a file
outgrows its line budget.

For other phierceweb projects, see [github.com/phierceweb](https://github.com/phierceweb).

## Contributing

[CONTRIBUTING.md](https://github.com/phierceweb/kemperrig/blob/main/CONTRIBUTING.md): nothing
may write to a source file, decodes need a real file or Rig Manager agreeing, and a decode bug
report needs the Rig Manager version and the value Rig Manager shows — never the backup
itself, which usually holds commercially licensed profiles.

## Security

[SECURITY.md](https://github.com/phierceweb/kemperrig/blob/main/SECURITY.md). kemperrig opens
files a user may have received from someone else; it reads them into memory, never extracts
them, and makes no network connections. It refuses an archive entry that would inflate
implausibly, and its text output escapes control characters from those files.

## License

Apache-2.0 — see [LICENSE](https://github.com/phierceweb/kemperrig/blob/main/LICENSE) and
[NOTICE](https://github.com/phierceweb/kemperrig/blob/main/NOTICE).

Not affiliated with, endorsed by, or sponsored by Kemper GmbH. KEMPER, KEMPER PROFILER and RIG
MANAGER are trademarks of Kemper GmbH. See
[TRADEMARKS.md](https://github.com/phierceweb/kemperrig/blob/main/TRADEMARKS.md).
