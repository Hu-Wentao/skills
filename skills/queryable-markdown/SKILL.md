---
name: queryable-markdown
description: Design, create, maintain, edit, batch-update, verify, optimize, and query Markdown through a persistent mdq query contract, including heading records, GFM table-row records, named query intents, result-quality limits, deterministic query-contract repair, and multi-path collection queries. Use for exact, text, field, directory, or glob lookups; creating or converting persistently queryable documents; preventing over-broad record models; diagnosing excessive or oversized results; safely refining embedded query parameters; setting existing label-backed fields; editing records; maintaining profiles, markers, or indexes; and restoring queryability. Ordinary Markdown without a contract remains read-only unless conversion is explicitly authorized.
---

# Queryable Markdown

Work with imperfect Markdown according to both its current state and the requested operation. A persistent `mdq` query contract makes record identity, boundaries, fields, recovery, and optional indexing deterministic. It does not make the index authoritative and does not by itself authorize a write.

## Default Authoring Representation for AI-Maintained Documents

When creating new Markdown content or materially extending a document that an AI will maintain, default to a heading hierarchy for records and nested sections or fields. Do not introduce Markdown tables merely to make repeated content compact; headings keep records easier to retrieve and edit independently.

Use `table-row` and `column` only when preserving an existing authored table, when the user explicitly requests a table, or when a flat matrix is essential to the document's intended representation. When maintaining an existing table, preserve it unless conversion is explicitly authorized; this preference does not by itself authorize structural rewrites.

## Classify Document State and Operation

Use this matrix before acting:

| Document state | Requested operation | Allowed behavior |
| --- | --- | --- |
| No valid `mdq` contract | Query, find, read, or summarize | Query read-only with inferred or explicit temporary selectors. Do not add metadata, markers, or indexes. |
| No valid `mdq` contract | Ordinary content edit | Treat as outside this skill unless an applicable governance workflow requires a persistent contract for the authorized document edit. |
| No valid `mdq` contract | Create or convert to a contracted document | Write when explicitly requested or when an applicable governance workflow requires a persistent contract for the authorized document creation or edit; inspect existing content before conversion. |
| Valid `mdq` contract | Query, find, read, or summarize | Apply the contract read-only. Do not edit merely because the document has a contract. |
| Valid `mdq` contract | Add, update, delete, rename, or reorganize records | Use the contracted-document edit transaction in [editing-workflow.md](references/editing-workflow.md). |
| Drifted but valid `mdq` contract | Query or edit | Report recovery diagnostics; edit only when drift does not affect the target identity or boundary. |
| Declared but invalid contract | Query | Report the contract error; use bounded inspection only if the user still needs a one-off answer. |
| Declared but invalid contract | Repair or maintain | Repair only when explicitly requested, then validate representative operations. |

Creating a new contracted document, converting an existing document, editing authored records, repairing a contract, and rebuilding an index are distinct write operations. Infer only the minimum write authority needed from the user's request and any applicable upstream governance workflow. A governance workflow may make a minimal persistent contract part of an authorized governed-document creation or edit; it does not authorize unrelated content changes, bulk migration, index creation, or contract repair outside that document.

## Core Invariants

- Treat Markdown source bytes as authoritative and any sidecar index as disposable derived cache.
- Preserve authored bytes outside the authorized record or contract control region. Never round-trip the document through a Markdown renderer.
- Keep contract declarations as data. Never put shell, Python, dynamic imports, URLs to follow, or executable code in the document.
- Return missing values as `null`. Never invent IDs, titles, fields, closing sections, repaired prose, or business decisions.
- Return every duplicate or ambiguous match with diagnostics. Never silently choose the first result or edit an ambiguous target.
- Prefer exact IDs and declared fields. Use text search only for candidate discovery.
- Treat excessive count, oversized record spans, oversized payloads, low confidence, and candidate-only evidence as separate query-quality failures. Never simulate precision by truncating results or choosing the first match.
- Preflight every selected document before a batch write. If any selected document is invalid or any write location is unsafe, write none of them.
- Treat successful parsing and validation as structural evidence, not proof that authored content is correct or complete.
- Keep document mechanics separate from domain authority. When requirements, baselines, plans, archives, or other governed sources are involved, let the applicable governance workflow decide their semantics.

## Query Any Markdown Read-Only

Resolve `SKILL_DIR` to this skill directory. Use the same commands whether or not the document has a valid contract:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <exact-id>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --text <term>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --field <field> --text <term>
uv run "$SKILL_DIR/scripts/mdq.py" run <document.md> --query <name> --value <value>
uv run "$SKILL_DIR/scripts/mdq.py" verify <document.md>
```

With a valid contract, the CLI applies declared boundaries, keys, fields, recovery, query intents, quality limits, and index policy. Without one, it infers conservative temporary selectors in memory. Interpret `count`, payload size, confidence, source ranges, candidates, quality, and diagnostics together. A single giant record can be a failed query even when `count` is one.

For a deterministic collection query, scan one or more Markdown files or directories:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" scan <directory> \
  --glob '**/*.md' \
  --field status \
  --require-contract

uv run "$SKILL_DIR/scripts/mdq.py" scan <first.md> <second.md> \
  --id <first-id> \
  --id <second-id> \
  --require-contract
```

The default glob is `**/*.md`; repeat `--glob` to combine bounded patterns. Explicit file paths are always included, while globs apply to directory paths. Use `--require-contract` for governed collections so every profile-free or invalid document is reported as an error without hiding valid matches from other documents. When `--field` is present, every processed contract must declare that field. Collection results retain the absolute document path, root-relative path, source range, confidence, per-document summary, and source-located diagnostics. A collection scan is read-only: it never adds contracts, writes indexes, or repairs drift.

For a recognizable non-generic convention, pass temporary selectors without persisting them:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> \
  --id <exact-id> \
  --record-level 3 \
  --key-label Ref \
  --key-pattern '^(?P<id>ticket_[0-9]+)$' \
  --key-group id
```

Use the read-only inspector when results are ambiguous or structure is unfamiliar:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" inspect <document.md>
```

When no safe boundary exists, accept line-local evidence rather than fabricating a record. A prose mention is a candidate, not a structured identity match. Confirm in the handoff that no metadata, markers, records, or index changed.

## Create or Convert a Contracted Document

Read [protocol.md](references/protocol.md) and [query-design-and-repair.md](references/query-design-and-repair.md) before creating or changing a contract.

For a new document:

1. Name the repeated domain entity before choosing Markdown syntax. A document title is not the record when the body contains repeated requirements, tickets, scenarios, or other independently queried entities.
2. Define the stable key, the minimum reusable query intents, expected result cardinality, bounded projection, payload limits, and source-located writable fields.
3. Choose the representation from the access pattern: for new AI-generated or AI-maintained content, default to heading records with nested sections or labels; use `table-row` and `column` only for existing, explicitly requested, or essential flat GFM matrices.
4. Create the profile and authored records together. Do not add speculative fields or one-off query values.
5. Run `validate`, `diagnose`, and `verify`; query known first, middle, last, absent, and prose-only identities. Do not hand off a contract that exposes one wrapper record around multiple stable inner identities.

For an existing ordinary document:

1. Run `inspect` and examine several representative records, including an incomplete or irregular one when present.
2. Inventory repeated identities, common filters, expected projections, and current result sizes. Infer the smallest stable boundary that makes those entities independently addressable.
3. If competing interpretations produce different identities, ask the user to choose. Resolve lesser ambiguity conservatively and report it.
4. Add only the contract control block and strictly necessary stable record markers. Do not rewrite business content merely to normalize it.

Place every contract in YAML Front Matter at byte zero, delimited by `---`, with the profile nested under the top-level `mdq` key. Merge `mdq` into an existing complete YAML Front Matter block. If the document has no YAML Front Matter, create one; do not use HTML comments, TOML, or JSON for the contract header. A damaged, unclosed, or non-YAML header requires an explicitly authorized conversion or repair before the document can become contracted. Add `<!-- mdq:record id="..." -->` only when authored headings cannot provide stable record boundaries; record markers are not contract headers.

## Edit a Contracted Document

Use [editing-workflow.md](references/editing-workflow.md) for every authored-record write. The required transaction is:

1. Validate the current contract before editing; diagnose before editing only when the document already reports drift or the mutation can change identity, boundaries, contract rules, markers, fields, or index behavior.
2. Resolve the exact target and reject ambiguous identity.
3. Read only the target range and the minimum neighboring style evidence.
4. Classify the mutation and its authorization.
5. Apply a minimal source patch within the authorized range.
6. Apply the smallest verification tier below and escalate when results are unexpected.
7. Rebuild a declared index after the source edit succeeds.
8. Inspect the final diff for out-of-scope changes.

Do not use a generic serializer to edit records. Fields backed by `regex` are query-only selectors unless the authored source can be safely patched using an independently located record boundary. Renaming an identity requires checking every in-document reference and reporting external-reference limits.

For a batch update of one existing untransformed `source: label` scalar, use `set`. It is read-only unless `--apply` is present:

```bash
# Preview every matching record under a directory.
uv run "$SKILL_DIR/scripts/mdq.py" set <directory> \
  --field foo \
  --value false

# Apply exact conditions with AND semantics.
uv run "$SKILL_DIR/scripts/mdq.py" set <directory> \
  --where status=draft \
  --where owner=wyatt \
  --field foo \
  --value false \
  --apply

# Limit the batch to explicit files and exact record IDs.
uv run "$SKILL_DIR/scripts/mdq.py" set <first.md> <second.md> \
  --id <first-id> \
  --id <second-id> \
  --field foo \
  --value false \
  --apply
```

`set` requires a valid persistent contract in every processed document. It refuses missing or conflicting target values, duplicate record IDs within a document, transformed label fields, and fields sourced from `heading`, `section`, `body`, or `regex`. It preserves the label, whitespace, inline comments, and all bytes outside the exact value span. It prevalidates the complete batch, verifies every patched document in memory, writes only with `--apply`, revalidates written source, and rebuilds every declared sidecar index for a changed document. Do not use it to create missing fields or convert ordinary Markdown.

## Maintain or Repair a Contract

Inspect before changing profile rules, markers, or index policy. Keep the contract minimal and declarative. Preserve an existing valid YAML Front Matter block and its `---` delimiters; never create a second frontmatter block or silently convert another header format without authorization.

When an exact query misses a unique table-row identity, a named query exceeds its declared cardinality, or one returned record exceeds its span or payload budget, preview one deterministic repair:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" optimize <document.md> --id <exact-id>
uv run "$SKILL_DIR/scripts/mdq.py" optimize <document.md> --query <name> --value <value>
```

Apply only a unique in-memory-verified candidate and only when the current request authorizes contract repair or `maintenance.query_contract.mode: auto` durably delegates it:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" optimize <document.md> --id <exact-id> --apply
```

`actors.write: machine` describes authorship; it does not authorize maintenance. `locked` prevents automatic changes, absent policy defaults to proposal, and `auto` permits only declared scopes. Never rewrite authored content during query-contract optimization.

Use risk-proportional verification after a contracted write:

- **Tier 1 — stable record content:** For prose or an existing field value changed without touching its key, heading, marker, field label, boundary, Front Matter, contract, or index policy, run `validate` and query the affected exact record. Do not require `diagnose`, unaffected-record queries, or an absent-key matrix when validation and the exact query remain clean.
- **Tier 2 — record structure or identity:** For add, delete, rename, reorder, heading-level, marker, field-label, or boundary changes, run `validate` and `diagnose`; query every affected identity, one adjacent or unaffected record when present, and the expected absent or old identity. Use a prose-only search when candidate-vs-identity behavior could change.
- **Tier 3 — contract or collection semantics:** For creation, conversion, contract repair, profile/query/index-policy changes, batch writes, or changes that can reinterpret many records, run `validate`, `diagnose`, and `verify`; query representative first, middle, last, incomplete, and irregular records when present, plus an absent identity and a prose-only mention. Rebuild and recheck a declared index.

Always escalate to the next tier when validation reports new diagnostics, a source range moves unexpectedly, or the requested governance workflow explicitly requires stronger evidence. Do not run the full matrix merely because authored bytes changed.

The common Tier 1 commands are:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" validate <document.md>
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <affected-id>
```

Build or rebuild a declared sidecar index only during an authorized contracted-document write or explicit index-maintenance request:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" index <document.md>
```

Queries may use an index candidate only after source/profile hashes and extracted records agree with fresh parsing. A stale or corrupt cache never overrides current Markdown.

## Handoff

For read-only work, report matches, source locations, ambiguity, whether a persistent or temporary contract was used, and that nothing changed.

For writes, report:

- whether the document was created, converted, edited, or repaired;
- record boundaries, key rules, field mappings, and fallback behavior;
- record IDs added, changed, renamed, or removed;
- for collection operations, selected paths, selectors, matched and changed counts, and whether a preview or applied write ran;
- validation diagnostics separately from business content;
- the verification tier used and why it was sufficient;
- whether markers or an index were created or changed;
- compatibility limits and external references not verified;
- whether any business content outside the requested mutation changed;
- breaking changes and compatibility provisions, explicitly stating when there are none.

## Resources

- `scripts/mdq.py`: inspect, query, search, scan collections, safely set existing label fields, validate, diagnose, and index Markdown.
- `references/protocol.md`: contract schema, extraction semantics, lifecycle, result contract, diagnostics, compatibility, and security limits.
- `references/editing-workflow.md`: transactional creation, record-editing, contract-maintenance, and verification procedures.
- `references/query-design-and-repair.md`: query-first document design, result-quality gates, repair classification, and bounded adaptive maintenance.
