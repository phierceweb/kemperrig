---
description: Operational tunables live in .env and config/, read through the env resolvers
alwaysApply: true
---

# Config-Driven Design

> **In kemperrig, `layering.md` wins where this rule disagrees.** The environment is read in
> the `cli/` package only, through `resolve_str`; a service takes the resolved value as a
> parameter (`analyze`'s `rack_folder`) and never calls a `resolve_*` wrapper of its own.
> `tests/test_dependencies.py` pins that surface. Below is pw-foundation's general guidance:
> the `.env` and "When NOT to use" parts apply at the boundary; `AppConfig`, `config/*.yaml`
> and the module-level wrapper recipe do not.

Code reads operational tunables from the environment through the config layer — callers never
pass config values as parameters. Web apps centralize this in an `AppConfig` subclass; CLIs and
libraries use the wrapper-function recipe below.

## Principle

Tunable values belong in `.env`, not in function calls. Operators change behavior without code
changes, and every call site agrees.

## The layering

User-tunable operational values are configuration; internal constants are code.

| Lives in | What |
|---|---|
| `.env.example` (copied to `.env`) | **Operational tunables**: timeouts, retry counts, thresholds whose right value depends on the run, concurrency knobs, host/port, log level, backend selection. |
| `config/*.yaml` | Structured project configuration an operator edits — read through `pw_foundation.utils.yaml.safe_load`, which refuses a repeated key. |
| Code | Internal constants — regex patterns, schema versions, math, dataclass field defaults, cache key formats, loop guards. |

If you find yourself adding a `_FOO_TIMEOUT_S = 600`, `_BAR_THRESHOLD = 1000`, or
`_RETRY_LIMIT = 3` to a `.py` file, **stop**: it belongs in `.env.example`. If you are tempted to
bump the constant for a specific run, that is the litmus — it is operational.

## Pattern

```python
# WRONG — caller computes and passes the limit
def paginate_params(page, per_page, max_per_page=200): ...


# RIGHT — reads MAX_PER_PAGE from env, with per-call override
from pw_foundation.utils.env import resolve_int


def paginate_params(page, per_page, max_per_page=None):
    max_per_page = resolve_int(max_per_page, "MAX_PER_PAGE", default=200)
```

`pw_foundation.utils.env.resolve_int` / `resolve_str` / `resolve_bool` handle malformed env values
(warn + fall back to the default rather than crash) and strip whitespace. See
`docs/pw-foundation/env.md`.

## When to use

- The value is a tunable an operator might adjust per environment (dev vs prod).
- The value has a sensible default that works for most cases.
- Multiple call sites would pass the same value.

## When NOT to use

- The value is inherently per-call (e.g. `allowed_sorts` differs per endpoint).
- The value is a structural choice, not a tunable (e.g. a template directory path).
- Regex group indices, dataclass field defaults, cache key formats, schema versions, math
  constants, internal loop guards — anything that is part of the type system or wire format.

## How to wire a new env var (non-AppConfig projects)

Module-level constants plus a tiny wrapper that calls a resolver, read at call time so a
long-lived process picks up `.env` changes between calls:

```python
from pw_foundation.utils.env import resolve_int

_FOO_TIMEOUT_S_DEFAULT = 600
_FOO_TIMEOUT_ENV_VAR = "MYPROJ_FOO_TIMEOUT_S"


def _foo_timeout_s() -> int:
    return resolve_int(None, _FOO_TIMEOUT_ENV_VAR, default=_FOO_TIMEOUT_S_DEFAULT)
```

When the value is also a function kwarg, take `int | None` and pass the caller's value through as
the first argument so the precedence stays **kwarg > env > default**.

**Project prefix.** Each project owns its own env-var prefix (`MYAPP_*`), except the API-key
variables and `DATABASE_URL`, which follow upstream conventions.

## Checklist for a new `AppConfig` setting

1. Add the setting to your `AppConfig` subclass with a default.
2. Add it to `.env.example`.
3. Document it where the project documents its settings.
