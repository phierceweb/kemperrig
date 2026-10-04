# Docs Sync

**Code and docs travel together.** A change that alters something a user or contributor
relies on is incomplete without the matching doc update.

## Substantive (needs a doc update)

- New CLI subcommand, flag, or `KEMPERRIG_*` environment variable → `README.md` and `.env.example`
- Public function/class added, removed, renamed, or signature changed → its docstring,
  and `README.md` if it appears in the Library section
- Behaviour change in an existing command, even if the vocabulary stays the same
- Anything a release note would mention → `CHANGELOG.md`, under the newest version not yet
  released (add `## Unreleased` above the latest release once one is tagged)

## Not substantive

- Internal refactors with no public API or behaviour change
- Test-only changes, comment/docstring polish, dependency bumps

## Checklist

- [ ] New subcommand or flag: its row in `docs/cli.md` (`tests/test_docs.py` fails without
      it), what it does in `docs/capabilities.md`, and — for a new command — a line in the
      `## Commands` block of `README.md`, in the same shape as its neighbours
- [ ] New or changed `--json` key: its row in `docs/json.md` (`tests/test_docs.py` checks
      every table against the sample library)
- [ ] New format fact, enum, or field layout learned: `docs/format.md`, and the
      `kemper-rmbackup` skill if it is a trap
- [ ] New doc under `docs/`: add its row to `docs/README.md`. The index must list **every**
      doc (`tests/test_docs.py` checks); a silently partial index is worse than none
- [ ] New env var: the help epilog in `cli/__init__.py`, `docs/cli.md`, `.env.example`
      (`tests/test_cli_settings.py` and `tests/test_docs.py` check the first two)
- [ ] `README.md` is also the PyPI page: every link in it is absolute
- [ ] New rule file here: create `<name>.md`, then `ln -sf <name>.md <name>.mdc`
      (Cursor reads `.mdc`)
- [ ] Plans live in `.ai/plans/`, never the repo root, under a descriptive ALL_CAPS name
      (`BACKLOG.md`, not `PLAN2.md`)

## Public-repo rule

This repo is public. Before writing an example, a fixture, or a doc line, check it
carries no personal name, no `/Users/` path, no library statistics, and no link to a doc
that does not ship — `docs/` ships, `.ai/docs/` does not, and a tracked file must never
link into `.ai/`. A dead link to a private doc is itself a leak signal.
