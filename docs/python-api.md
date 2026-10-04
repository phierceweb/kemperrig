# Using kemperrig from Python

The library behind the CLI. Every command is a thin presentation layer over these calls, so
anything the CLI does is available in a script — and some things only make sense there,
like running one query across a folder of backups.

This page is the map, not an inventory: the modules' docstrings and type hints are the
reference for exact signatures. Before 1.0, pin the release you build against.

For AI assistants: the `kemper-rmbackup` skill covers the format traps the decode functions
guard against; `.ai/rules/layering.md` is the binding version of the layer rules below.

---

## Table of Contents

- [The layers](#the-layers)
- [Opening a library](#opening-a-library)
- [The records](#the-records)
- [Services](#services)
- [Errors](#errors)
- [Writing](#writing)
- [Worked examples](#worked-examples)
- [Adding a command](#adding-a-command)

## The layers

| Layer | Import | Holds |
|---|---|---|
| Model | `from kemperrig import Backup` | opening a source; the records |
| Records | `from kemperrig import Rig, Performance, Slot, Preset, Info` | frozen dataclasses with a few derived properties |
| Effect names | `from kemperrig import use_effect_names, DEFAULT_STOMPS_XML` | name effects from Rig Manager's own table |
| Decode | `kemperrig._sysex`, `kemperrig._sysex_effects` | the SysEx inside a payload (private: reach it through `services.decode`) |
| Services | `kemperrig.services.<name>` | one concern each; take records, return plain values |
| Presentation | `kemperrig._views`, `kemperrig._json`, `kemperrig.cli` | text, `--json`, argparse — not for scripts |

Calls go one way: presentation → services → model and decode → records. The library is
standard-library only, prints nothing and logs nothing; it returns values or raises.

## Opening a library

```python
from kemperrig import Backup

lib = Backup.open("2026-06-03 - Library.rmbackup")   # or a live directory, a snapshot, a pack
lib.rigs, lib.performances, lib.presets, lib.info
```

`Backup.open` tells the source apart by its content. Every database is deserialized from
bytes into an in-memory SQLite connection: nothing is extracted, nothing is written.

## The records

- `Rig` — the metadata row (`name`, `folder`, `gain`, `amp_model`, `cabinet_name`, …) and
  `blob`, the payload. `path` is `folder/name` (the bare name without a folder), `is_di`
  reads the cab columns, and `is_boosted` reads `amp_comment` — `None` when the text says
  nothing about drive.
- `Performance` — `name`, `tempo`, five `Slot`s (`rig_name`, `amp_name`, `cab_name`, …) and
  `blob`.
- `Preset` — `name`, `folder`, `preset_class` and the rest of the row; `is_cab_ir`.
- `Info` — the `version` and `user` a backup records.

Records never change: a service that needs a different view builds a new value.

## Services

| Module | Use it to |
|---|---|
| `report` | build the `summary` numbers (`build_report`) |
| `filter` | filter rigs by metadata (`filter_rigs`), find one rig by name (`find_rig`) |
| `select` | filter by metadata and by decoded effect or cab IR, with the rigs it could not judge (`select_rigs`) |
| `decode` | decode one rig's payload (`rig_detail`, or `try_rig_detail`, which returns `None` for a payload that does not parse) |
| `shortlist` | load a criteria file (`load_criteria`) and shortlist (`shortlist`) |
| `analyze` | orphans, coverage, duplicates and the rest (`analysis`, or each check alone) |
| `doctor` | slot and payload integrity (`checkup`) |
| `performance` | slot gain ladders and locked-effects shares |
| `pages` | raw parameter blocks for one rig, or counted across the library |
| `pack` | place a pack's items against a library (`placements`) |
| `diff` | compare two sources (`diff_rigs`, `diff_performances`, `diff_presets`); payload digests (`digest`) |
| `history` | a library across dated snapshots (`history`) |
| `census` | take a census (`take`), and write one behind its guard (`refusal`, `write`) |
| `edit` | `rename_rig`, behind its guard (`refusal`) |
| `extract` | plan and write `.krig` files, behind their guard (`plan`, `refusal`, `write`) |

## Errors

The library raises builtins and nothing else:

- `ValueError` — a malformed file (a damaged, encrypted or oversized archive entry among
  them), a payload that does not parse (`rig_detail` names the rig), criteria of the wrong
  shape;
- `KeyError` — a required table or column is missing;
- `FileNotFoundError` — a path that is not a Rig Manager library;
- `OSError`, `sqlite3.DatabaseError` — passed through from the file.

Every message names the file or record that failed. Library-wide services do not raise for
one bad payload: they skip it and report it (`analysis(...).unparsed`,
`select_rigs(...).unparsed`), as the CLI does.

## Writing

Only `edit.rename_rig`, `extract.write` and `census.write` write files, and each re-runs its
`refusal` before writing, so a direct caller is guarded too: an output that is or aliases
the source, or lies inside a Rig Manager library, raises `ValueError` and nothing is
written. Call `refusal` first if you want the reason without the exception.

## Worked examples

Which rigs in a library carry a delay, and which could not be checked:

```python
from kemperrig import Backup
from kemperrig.services.select import select_rigs

picked = select_rigs(Backup.open("lib.rmbackup").rigs, effect="delay", gain_min=6.0)
for rig in picked.rigs:
    print(rig.path)
print("not checked:", [r.path for r in picked.unparsed])
print("not ruled out:", [r.path for r in picked.undecoded])
```

The decoded effect chain of one rig:

```python
from kemperrig import Backup
from kemperrig.services.decode import rig_detail
from kemperrig.services.filter import find_rig

lib = Backup.open("lib.rmbackup")
detail = rig_detail(find_rig(lib.rigs, "Rhythm"))
print(detail.amp_gain, detail.cab_ir)
for e in detail.effects:
    print(e.slot, e.type_name if e.decoded else "undecoded")
```

Every backup in a folder, with its rig count:

```python
from pathlib import Path
from kemperrig import Backup

for path in sorted(Path("backups").glob("*.rmbackup")):
    print(path.name, len(Backup.open(str(path)).rigs))
```

Effect names come from the active table, which starts as a small built-in set. To name
effects from Rig Manager's own table, load it first; it returns how many types are named,
and an absent file leaves the built-in set:

```python
import kemperrig

kemperrig.use_effect_names()                       # kemperrig.DEFAULT_STOMPS_XML
kemperrig.use_effect_names("/elsewhere/Stomps.xml")
```

## Adding a command

1. **Service** — put the logic in one module under `src/kemperrig/services/`: take records
   (or a `Backup`) and return plain values or a frozen dataclass. No `print`, no
   `os.environ`, no imports from `cli`, `_views` or `_json`.
2. **Presentation** — a text renderer in the matching `src/kemperrig/_views/` module and a
   document builder in the matching `src/kemperrig/_json/` module, carrying the same data.
3. **CLI** — a `cmd_<name>` and `register_<name>` in the matching `src/kemperrig/cli/` module,
   and a slot in `_COMMANDS`. The handler is one service call plus a render; settings
   resolve there and reach the service as parameters.
4. **Tests** — the service against fixtures built in `tests/` (never a real library), the
   error paths as one-line messages with a non-zero exit, and the new command in
   `tests/test_smoke.py`.
5. **Docs** — [cli.md](cli.md), [json.md](json.md), [capabilities.md](capabilities.md), the
   README and the CHANGELOG. `tests/test_docs.py` checks the first two against the code.
