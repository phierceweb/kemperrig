# JSON output

The document every `--json` command prints, key by key — the contract a script reading
kemperrig's output can rely on.

For AI assistants: the `kemper-rmbackup` skill covers what the decoded values mean and the
format traps behind them.

---

## Table of Contents

- [Conventions](#conventions)
- [Shared shapes](#shared-shapes)
  - [Rig entry](#rig-entry)
  - [Decode object](#decode-object)
  - [Effect](#effect)
  - [Unchecked](#unchecked)
  - [Preset entry](#preset-entry)
  - [Performance entry](#performance-entry)
- [Documents](#documents)
  - [summary](#summary) · [rigs](#rigs) · [rig](#rig) · [presets](#presets) ·
    [performances](#performances) · [pages RIG](#pages-rig) · [pages --all](#pages---all) ·
    [shortlist](#shortlist) · [analyze](#analyze) · [doctor](#doctor) · [pack](#pack) ·
    [diff](#diff) · [history](#history) · [extract](#extract)
- [Adding a key](#adding-a-key)

## Conventions

- Every document is one JSON object on stdout; nothing else is printed there, so it pipes
  straight into `jq`. Diagnostics go to stderr.
- Every document is strict JSON: no `NaN` or `Infinity`. Strings are kept as stored, control
  characters included, escaped the JSON way.
- A value that could not be decoded is `null`, never a guess.
- A rig is identified by its **path** (`folder/name`) in lists, and by its **digest** — the
  first 12 hex characters of the payload's SHA-256, the value `--payload` takes.
- Sources without folders (snapshots, packs) give a rig the bare name as its path.
- `census` documents — the file `summary --write-golden` writes — are described in
  [census.md](census.md).

## Shared shapes

### Rig entry

One rig as `rigs`, `shortlist`, `rig` and `pack` print it: its metadata row, two derived
flags, and its digest.

| Key | Holds |
|---|---|
| `name` | the rig's name in the library |
| `folder` | its library folder; empty in a snapshot or pack |
| `filename` | the stored file name |
| `author` | the `Author` column |
| `date` | the `Date` column |
| `comment` | the `Comment` column |
| `gain` | the `Gain` column, a number with one decimal, or `null` — also when the column holds no finite number |
| `amp_model` | `Amp Model` |
| `amp_name` | `Amp Name` |
| `amp_channel` | `Amp Channel` |
| `amp_comment` | `Amp Comment` — where boost notes live |
| `amp_location` | `Amp Location` |
| `amp_model_year` | `Amp Model Year` |
| `amp_pickup` | `Amp Pickup` |
| `source_amp` | `Source Amp`, the maker |
| `cabinet_name` | `Cabinet Name` — `N/A`, empty or `DIRECT` on a DI profile |
| `cabinet_type` | `Cabinet Type`, raw — not a DI flag |
| `cabinet_configuration` | `Cabinet Configuration`, free text |
| `mic_type` | `Mic Type` |
| `mic_position` | `Mic Position` |
| `speaker_manufacturer` | `Speaker Manufacturer` |
| `speaker_model` | `Speaker Model` |
| `profile_type` | `Profile Type`, raw; `null` where the source has no such column |
| `profile_revision` | `Profile Revision`, raw |
| `is_di` | `true` for a DI profile (no baked-in cab) |
| `is_boosted` | `true`/`false` from the `Amp Comment` text; `null` when it says nothing about drive |
| `digest` | the payload digest; `null` for an empty payload |
| `decode` | only from `rig` and `rigs --decode`: a [decode object](#decode-object), or `null` when the payload does not parse |

### Decode object

What a rig's payload decodes to.

| Key | Holds |
|---|---|
| `amp_gain` | the amp's Gain knob, 0.0–10.0, from the amp block; `null` for an unverified block shape |
| `cab_ir` | the first cab-IR `.wav` name among the strings, or `null` |
| `effects` | the loaded module slots in signal-flow order, each an [effect](#effect) |
| `strings` | every decoded string, in payload order |

### Effect

| Key | Holds |
|---|---|
| `slot` | `A`, `B`, `C`, `D`, `X`, `MOD`, `DLY` or `REV` |
| `type_value` | the raw type number; `null` for an undecoded slot |
| `type_name` | the type's name from Rig Manager's table, or `null` when the table does not name it |
| `category` | Kemper's category for the type, when the table supplies one |
| `on` | the slot's on/off; `null` where the block carries none |
| `decoded` | `false` for a slot present only in the function-`08` framing: its type — and whether it holds an effect at all — is unknown |

### Unchecked

Present whenever `--effect` or `--ir` is given (`rigs`, `extract`): the rigs the filter
could not judge, by path. Both keys are always there.

| Key | Holds |
|---|---|
| `unparsed` | rigs whose payload does not parse |
| `undecoded` | rigs that missed `--effect` but have an undecoded slot, so the effect may be there; empty when only `--ir` is given |

### Preset entry

| Key | Holds |
|---|---|
| `name` | the preset's name |
| `folder` | its library folder |
| `filename` | the stored file name |
| `preset_class` | `Preset Class`: `6` is a cab IR, `3` an effect module |
| `preset_category` | `Preset Category` |
| `preset_type` | `Preset Type` |
| `is_cab_ir` | `true` for a cab-IR preset |

### Performance entry

| Key | Holds |
|---|---|
| `name` | the performance's name |
| `tempo` | the `Tempo` column, raw |
| `slots` | five slots, each `index`, `name`, `enable`, `rig_name`, `amp_name`, `cab_name` |
| `gain_ladder` | each slot's gain, read from the rig it names; `null` where that rig is missing or ambiguous |
| `locked_ratio` | the share of effect slots identical across the slots in use; `null` when fewer than two can be compared |

## Documents

### summary

| Key | Holds |
|---|---|
| `user` | the user name the backup records, or `null` |
| `rigs` | how many rigs |
| `di` | how many DI profiles |
| `studio` | how many studio profiles |
| `performances` | how many performances |
| `gain` | `min`, `max`, `mean` of the `Gain` column, and `bands` — rigs per whole gain number |
| `amp_models` | `{name, count}` per amp model, most rigs first |
| `authors` | `{name, count}` per author, most rigs first |

### rigs

| Key | Holds |
|---|---|
| `count` | how many rigs matched |
| `rigs` | each a [rig entry](#rig-entry) |
| `unparsed` | only with `--decode`: paths of matched rigs whose payload does not parse |
| `unchecked` | only with `--effect` or `--ir`: an [unchecked](#unchecked) object |

### rig

One [rig entry](#rig-entry), always carrying `decode`. A payload that does not parse is a
one-line error and exit 1 instead.

### presets

| Key | Holds |
|---|---|
| `count` | how many presets |
| `presets` | each a [preset entry](#preset-entry) |

### performances

| Key | Holds |
|---|---|
| `count` | how many performances |
| `performances` | each a [performance entry](#performance-entry) |

### pages RIG

| Key | Holds |
|---|---|
| `rig` | the rig's name |
| `folder` | its folder |
| `blocks` | each 14-bit block: `page`, `page_hex`, `label` (the slot name, or `null` for an unread page), `start`, `count`, `values` |
| `other` | messages in other framings: `header` (first six body bytes, hex) and `bytes` |

### pages --all

| Key | Holds |
|---|---|
| `rigs` | how many rigs were read |
| `pages` | per page: `page`, `page_hex`, `label`, `rigs` carrying it, `starts`, `param_counts` |
| `other` | per other-framing header: `header`, `rigs`, `bytes` (the lengths seen) |
| `unparsed` | paths of rigs whose payload does not parse |

### shortlist

| Key | Holds |
|---|---|
| `count` | how many rigs made the shortlist |
| `rigs` | each a [rig entry](#rig-entry), highest gain first |

### analyze

| Key | Holds |
|---|---|
| `orphaned_rigs` | paths of rigs no performance uses (outside `--rack-folder`) |
| `amp_coverage` | per amp model: `amp`, `count`, `gain_min`, `gain_max`, `has_clean`, `has_mid`, `has_high` |
| `similar_groups` | groups of rig paths sharing author, amp, gain and boost |
| `identical_amp_groups` | groups of rig paths with byte-identical amp blocks |
| `identical_profiles` | groups of rig paths with byte-identical payloads |
| `drive` | `boosted`, `unboosted`, `unknown` counts |
| `effect_categories` | `{category, slots}`, most-used first; empty without Rig Manager's table |
| `ir_inventory` | `{name, count}` per cab-IR file in use |
| `non_monotonic_performances` | `{name, gain_ladder}` for performances whose slots do not climb in gain |
| `unparsed` | `rigs` (paths) and `performances` (names) whose payload does not parse |

### doctor

| Key | Holds |
|---|---|
| `defective` | `true` when any definite finding exists — what `--strict` fails on |
| `rigs` | how many rigs were checked |
| `performances` | how many performances |
| `slots` | how many performance slots |
| `cab_irs` | how many cab-IR presets |
| `definite` | `dangling_slots` and `ambiguous_slots` (each `performance`, `slot`, `rig_name`; ambiguous ones add the competing `rigs`), and `broken_payloads` (`kind`, `name`, `folder`, `problem`) |
| `informational` | `device_only_slots` (`null` without `--device-backup`), `unread_payloads`, `gain_mismatches`, `name_mismatches`, `unused_cab_irs` |

### pack

| Key | Holds |
|---|---|
| `pack` | `name`, `author` (the vendor), `copyright`, `released`, `content` (`rigs` or `presets`) |
| `against` | the library compared with, or `null` |
| `counts` | with `--against`: `in_library`, `name_taken`, `new`; otherwise `null` |
| `count` | how many items |
| `rigs` | in a rig pack: each a [rig entry](#rig-entry), plus `status` and `library` (`{folder, name}` matches) with `--against` |
| `presets` | in a preset pack: each a [preset entry](#preset-entry) plus `digest`, and `status` / `library` with `--against` |

### diff

| Key | Holds |
|---|---|
| `identical` | `true` when nothing differs — the case that exits 0 |
| `rigs` | `added`, `removed` (keys) and `changed` (`{key, changes: [{field, before, after}]}`) |
| `performances` | the same, keyed by name |
| `presets` | the same, keyed by path |

### history

| Key | Holds |
|---|---|
| `order` | `name` or `mtime` |
| `files` | how many files were read |
| `skipped` | `{path, reason}` per file that could not be read |
| `timeline` | without `--rig`: per file, `path`, `label`, `device`, the `rigs` / `performances` / `presets` counts, `empty`, and `since` — the previous file of the same device and what was added, removed and changed since |
| `rig` | with `--rig`: `name`, `first` and `last` sighting, `versions` (`version`, `digest`, `files`, `first`, `last`) and `sightings` (per file: `versions` held, `changed`) |

### extract

| Key | Holds |
|---|---|
| `out` | the folder written into |
| `count` | `written` and `skipped` |
| `written` | `{folder, name, file, digest}` per file written |
| `skipped` | `{folder, name, reason}` per selected rig not written |
| `unchecked` | only with `--effect` or `--ir`: an [unchecked](#unchecked) object |

## Adding a key

1. Add it in the document's builder under `src/kemperrig/_json/`, and decide deliberately
   whether the text view in `src/kemperrig/_views/` shows it too.
2. Add its row to the matching table here. `tests/test_docs.py` runs every documented
   command against the synthetic sample library and fails when a table and a document
   disagree, either way.
3. If the sample does not produce the key (a key only some sources have), extend
   `tests/_sample.py` so it does.
4. Note it in `CHANGELOG.md`.
