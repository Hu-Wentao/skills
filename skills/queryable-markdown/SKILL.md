---
name: queryable-markdown
description: Query, create, edit, batch-update, validate, and repair Markdown through persistent or temporary mdq contracts. Use for exact record lookup, bounded collection search, source-located edits, safe scalar updates, post-write verification, contract conversion, query diagnosis, or deterministic repair.
---

# Queryable Markdown

Use compact agent commands for normal work and stable JSON only for automation or requested details. Resolve `<skill-root>` from this active skill.

## Route

| Need | Command |
| --- | --- |
| Exact record | `get <document> --id <id>` |
| Collection lookup | `find <path>... --id <id>` or `--text <text>` |
| Declared query | `run <document> --query <name> --value <value> --output compact` |
| Existing label scalar update | `set` preview, then exact repeat with `--apply` |
| Verify edit | `check <document> --tier content|structure|contract` |
| Programmatic JSON | `query`, `search`, `scan`, or `run` |

## Preserve Authority

- Markdown bytes are authoritative; sidecar indexes are cache.
- Contracts are data, never executable commands, imports, URLs, or plugins.
- A contract provides addressing, not write authority.
- Preserve bytes outside the authorized record or mdq control range; never renderer-round-trip.
- Match exact case-sensitive identity. Refuse absent, duplicate, candidate, ambiguous, or guessed boundaries.
- Return absent values as `null`; never invent IDs, fields, prose, or domain decisions.
- Preflight an entire batch before writing any target.
- Keep parsing checks separate from domain approval.
- Keep project `README.md` ordinary: never add, repair, or write persistent mdq metadata there.

## Read Compactly

```bash
uv run <skill-root>/scripts/mdq.py get <document.md> --id <id> --select <field>
uv run <skill-root>/scripts/mdq.py find <path> --glob '**/*.md' \
  --text <term> --select <field> [--require-contract]
```

Repeat `--select` as needed. Compact output omits large raw/body/context fields when smaller declared fields exist. Rerun with `--output json` only when compact output requests details or another program needs the envelope.

Without a persistent contract, conservative temporary selectors may support read-only `get` and `find`. A prose mention remains candidate evidence, not identity.

## Write and Verify

Preview scalar batches, inspect, then repeat exactly with `--apply`:

```bash
uv run <skill-root>/scripts/mdq.py set <path>... \
  --where status=draft --field reviewed --value true
```

For manual record edits, read [editing-workflow.md](references/editing-workflow.md), patch one bounded source range, then run one tier:

```bash
uv run <skill-root>/scripts/mdq.py check <document.md> --tier content --id <id> --select <field>
uv run <skill-root>/scripts/mdq.py check <document.md> --tier structure --id <id> --absent-id <old-id>
uv run <skill-root>/scripts/mdq.py check <document.md> --tier contract
```

Escalate when warnings, ranges, ambiguity, markers, labels, headings, boundaries, query policy, or indexes change.

## Contracts and Repair

Before creating, converting, or changing a contract, read [protocol.md](references/protocol.md) and [query-design-and-repair.md](references/query-design-and-repair.md). Default new AI-maintained records to heading blocks. Preserve tables unless conversion is authorized. Run `inspect` before conversion and preview `optimize`; apply only one authorized candidate without rewriting authored content.

## Report

Report operation, IDs and paths, diagnostics, verification tier, contract/marker/index effects, unresolved ambiguity, preserved unrelated content, and breaking impact.
