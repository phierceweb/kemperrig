---
description: Plan and tracking documents live in .ai/plans/
alwaysApply: true
---

# Plans

All plan and tracking documents go in `.ai/plans/`. Never create plan files in the project root.

Plans include: implementation plans, migration tracking, standardization docs, refactor
checklists, and any other multi-step tracking documents.

## Naming

- Use descriptive names: `STANDARDIZATION.md`, `MIGRATION_AUTH.md`, not `PLAN.md` or `PLAN2.md`.
- All caps with underscores for the filename.

## Symlinks

`.claude/plans` and `.cursor/plans` are symlinks to `.ai/plans/` (`pw-setup` creates them). Do
not create plans directly in those directories.
