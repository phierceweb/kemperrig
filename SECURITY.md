# Security Policy

## Supported versions

The latest release on PyPI. This is a small project; fixes land in the next release rather
than in backports.

## Reporting a vulnerability

Email **oss@phierceweb.com** with a description and, where possible, steps to reproduce.
Please do not open a public issue for a vulnerability.

## Scope

kemperrig opens archives and database files that a user may have downloaded from a
profile marketplace or received from someone else, and it can be pointed at an arbitrary
directory. Relevant classes of issue include:

- A crafted `.rmbackup` that causes extraction to write outside the destination
  (path traversal / zip-slip), or that exhausts memory or disk.
- A malformed embedded SQLite database that causes a crash or unexpected file access when
  deserialized.
- A crafted rig or performance blob that causes the SysEx decoder to hang, allocate
  without bound, or read out of range.
- Anything that causes a write to a source archive, which is meant to be read-only.
- Text in a file that reaches the terminal as an escape sequence.

What is meant to hold today: nothing is extracted to disk; an archive entry that would
inflate past 1 GiB, or past 100:1 beyond 16 MiB, is refused before it is read; a damaged
entry is a one-line error; and text output shows control characters from a file as `\xNN`.
A way around any of these is a vulnerability.

Not in scope: Rig Manager itself, the Profiler hardware or its firmware, and the contents
of third-party commercial profiles.
