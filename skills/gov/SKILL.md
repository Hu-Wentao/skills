---
name: gov
description: Query and change the status of governed project documents (plans, defects) and their checklist tasks; run the governance check. Use when asked to list, update or verify a plan/defect status or task.
metadata:
  context-budget: router
---
# gov

Use the tool, not hand edits, for status and task changes; the tool enforces the vocabulary and allowed transitions.

```bash
node <skill-root>/scripts/gov.mjs ls [--kind plan|defect] [--status S]
node <skill-root>/scripts/gov.mjs show <ID>
node <skill-root>/scripts/gov.mjs set <ID> <status> [--apply]      # dry run unless --apply
node <skill-root>/scripts/gov.mjs task <ID> [<n|Tn> <todo|doing|done|dropped>] [--apply]
node <skill-root>/scripts/gov.mjs check [--level error]            # exit 1 on errors
```
Run from the project root (or pass `--root`). Config: `.agents/skills-config/gov/config.yaml` (`gov init --apply` creates it plus a CI workflow).

- Defect status lives in the YAML front matter `status:`; that is the single authority.
- A rejected transition means the lifecycle was skipped: do the missing step, do not pass `--force` unless the user says so.
- Contract or vocabulary changes go in the config, never in the document.
- Reinstall skills from `skills-lock.json` with `node <skill-root>/scripts/restore-skills.mjs` (`--pin` records commit SHAs).
