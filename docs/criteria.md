# Shortlist criteria

The JSON file `shortlist` reads: which amps you care about, and the gain floor.

---

## Table of Contents

- [What shortlist does](#what-shortlist-does)
- [The file](#the-file)
- [Keys](#keys)
- [What is refused](#what-is-refused)
- [Adding a key](#adding-a-key)

## What shortlist does

`shortlist` narrows a library to rigs on matching amps at or above a gain floor, DI
profiles only unless `--include-studio` is given — with the cab held constant, comparing
the shortlist is a comparison of the profile alone. The criteria live in a file so the
tool carries no opinion about anyone's rig.

```bash
kemperrig shortlist "<backup>" --criteria my-criteria.json
kemperrig shortlist "<backup>" --criteria my-criteria.json --gain-min 6 --include-studio
```

Set `KEMPERRIG_CRITERIA` to the file's path to drop `--criteria`.

## The file

Start from [config/example-shortlist.json](https://github.com/phierceweb/kemperrig/blob/main/config/example-shortlist.json):

```json
{
  "label": "high-gain shortlist",
  "context": "cab held constant",
  "gain_min": 5.0,
  "amp_patterns": {
    "Mesa Rectifier": ["Rectifier", "Recto"],
    "Diezel": ["VH4", "Einstein"]
  }
}
```

## Keys

| Key | Required | Holds |
|---|---|---|
| `amp_patterns` | yes | case-insensitive substrings of the rig's amp model. Either a flat list, or an object grouping lists by amp family — the grouping is for whoever reads the file; matching flattens it |
| `gain_min` | no | the gain floor, inclusive; `--gain-min` overrides it; default `5.0` |
| `label` | no | the heading the text view prints |
| `context` | no | a note printed beside the heading |

Any other key, such as `_comment`, is ignored.

## What is refused

The file is the one thing a user writes by hand, so its shape is checked where it is read,
and a wrong shape is a one-line error naming the file, exit 1 — never a silently wrong
shortlist:

- a top level that is not an object;
- no `amp_patterns`, or an empty one;
- `amp_patterns` as a bare string — it would otherwise match character by character;
- a pattern that is not a string, or is empty or blank — it would match every amp;
- a `gain_min` that is not a number, or is not finite.

## Adding a key

Read and shape-check it in `load_criteria` (`services/shortlist.py`), raising `ValueError`
with the file's path for a wrong shape; use it in `shortlist` or the CLI's `cmd_shortlist`;
add its row to [Keys](#keys); cover the accepted and refused shapes in
`tests/test_shortlist.py`.
