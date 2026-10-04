# Scope

kemperrig reads Kemper Rig Manager `.rmbackup` archives and the live Rig Manager library,
decodes their SQLite metadata and SysEx blobs, and diffs two of them. One library, one CLI.

It must NEVER contain:

- A web layer, a database, or an LLM call — none are in scope, and adding one changes
  what this project is
- Generic infrastructure any project would want (logging setup, env resolution, atomic
  writes) — that belongs in pf-core; see `framework-first.md`
- Talking to the Profiler hardware, or modifying the live library in place
- Format knowledge outside the domain modules (`model.py`, `_archive.py`, `_tables.py`,
  `_packs.py`, `_sysex.py`, `_sysex_effects.py`, `_sysex_edit.py`)
- Anything that only makes sense for one player's library — criteria are caller-supplied
  JSON, not code; that is a config file against this library, not part of it
