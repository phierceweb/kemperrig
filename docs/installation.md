# Installation

Installing kemperrig, pointing it at your library, and checking that it works — from PyPI
or from a clone of the repository.

---

## Table of Contents

- [Requirements](#requirements)
- [Install from PyPI](#install-from-pypi)
- [Install from a clone](#install-from-a-clone)
- [Check the install](#check-the-install)
- [Point it at your library](#point-it-at-your-library)
- [Effect names](#effect-names)
- [Platforms](#platforms)
- [Upgrade or remove](#upgrade-or-remove)
- [Adding a setting](#adding-a-setting)

## Requirements

- **Python 3.12 or newer.**
- **One dependency**, [pf-core](https://pypi.org/project/pf-core/), installed automatically;
  everything else is the standard library.
- **A Rig Manager library to read** — a `.rmbackup` file, or Rig Manager's own library
  directory. Rig Manager itself is optional: it only supplies effect names (see
  [Effect names](#effect-names)).

## Install from PyPI

kemperrig is a command-line tool, so install it with [pipx](https://pipx.pypa.io/), which
gives it an environment of its own:

```bash
pipx install kemperrig
```

Or into a virtual environment you manage:

```bash
python3 -m venv .venv
.venv/bin/pip install kemperrig
```

Releases are tagged; `main` is the development line. To try `main`:

```bash
pipx install git+https://github.com/phierceweb/kemperrig
```

## Install from a clone

```bash
git clone https://github.com/phierceweb/kemperrig && cd kemperrig
bin/run setup          # .venv with an editable install and the dev tools
bin/run pytest         # the suite — needs no library of yours
bin/run kemperrig --help
```

`bin/run setup` picks the newest of `python3.14`, `python3.13` and `python3.12` on your
`PATH`. Without `bin/run`: `pip install -e ".[dev]"` in a venv of your own.

## Check the install

```bash
kemperrig --version
kemperrig summary "path/to/your.rmbackup"
```

No library at hand? From a clone, write a synthetic one and try any command on it:

```bash
bin/run sample /tmp/kemper-sample
kemperrig doctor /tmp/kemper-sample/Library.rmbackup
kemperrig rigs /tmp/kemper-sample/RigManager --decode
```

## Point it at your library

Every read command takes the library as its first argument. Set `KEMPERRIG_LIBRARY` and
the argument becomes optional:

```bash
export KEMPERRIG_LIBRARY="$HOME/Library/Application Support/Kemper Amps/RigManager"
kemperrig summary
```

That path is Rig Manager's live library on macOS. kemperrig only reads it, but a backup is
still the safer thing to point it at: Rig Manager writes `.rmbackup` files, and one of those
is a snapshot that cannot change underneath you.

In a clone, put your settings in a `.env` file at the repository root — `bin/run` reads it,
and it is gitignored. [.env.example](https://github.com/phierceweb/kemperrig/blob/main/.env.example)
lists every variable; [cli.md](cli.md#environment) says what each does.

## Effect names

Effect type names belong to Kemper, so kemperrig ships none of its own beyond a small set
it verified independently. It reads the full table at runtime from the `Stomps.xml` inside
your Rig Manager installation:

```text
/Applications/Rig Manager.app/Contents/Resources/Stomps.xml
```

If yours is elsewhere, set `KEMPERRIG_STOMPS_XML` to its path. Without the file, effects
the small set does not name show their raw type number, and `analyze` lists no effect
categories. Nothing else changes.

## Platforms

kemperrig is tested on **macOS and Linux**, on Python 3.12, 3.13 and 3.14.

**Windows is untested.** The code is plain Python and should run, but the default paths
above are macOS paths, and the write guards' handling of case and links has only been
exercised on macOS and Linux. On Windows, set `KEMPERRIG_LIBRARY` and
`KEMPERRIG_STOMPS_XML` to wherever Rig Manager keeps its library and `Stomps.xml`, and
report what you find.

## Upgrade or remove

```bash
pipx upgrade kemperrig
pipx uninstall kemperrig
```

With pip: `pip install --upgrade kemperrig`, `pip uninstall kemperrig`. kemperrig keeps no
state of its own: nothing to clean up beyond any census or `.krig` files you wrote.

## Adding a setting

A new `KEMPERRIG_*` variable resolves only at the CLI boundary — `resolve_str` in
`src/kemperrig/cli/` — and reaches services as a parameter, never through `os.environ`.
Add it to the help epilog in `cli/__init__.py`, to `.env.example`, and to the environment
table in [cli.md](cli.md#environment); `tests/test_cli_settings.py` and `tests/test_docs.py`
fail until the help and the reference name it.
