---
name: queryable-markdown
description: Create, maintain, edit, and query Markdown documents governed by a persistent mdq query contract, and query ordinary Markdown read-only without requiring or adding metadata. Use for exact or text lookups in semi-structured Markdown; creating a new contracted Markdown document; converting a document into a persistently queryable document; adding, updating, deleting, or renaming records in a contracted document; maintaining an mdq YAML profile, stable markers, or sidecar index; diagnosing contract drift; or restoring queryability. Ordinary Markdown without a contract is read-only unless the user explicitly requests conversion to a contracted document.
---

# Queryable Markdown

Work with imperfect Markdown according to both its current state and the requested operation. A persistent `mdq` query contract makes record identity, boundaries, fields, recovery, and optional indexing deterministic. It does not make the index authoritative and does not by itself authorize a write.

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
- Treat successful parsing and validation as structural evidence, not proof that authored content is correct or complete.
- Keep document mechanics separate from domain authority. When requirements, baselines, plans, archives, or other governed sources are involved, let the applicable governance workflow decide their semantics.

## Query Any Markdown Read-Only

Resolve `SKILL_DIR` to this skill directory. Use the same commands whether or not the document has a valid contract:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <exact-id>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --text <term>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --field <field> --text <term>
```

With a valid contract, the CLI applies declared boundaries, keys, fields, recovery, and index policy. Without one, it infers conservative temporary selectors in memory. Interpret `count`, `confidence`, source ranges, candidates, and diagnostics together.

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

Read [protocol.md](references/protocol.md) before creating or changing a contract.

For a new document:

1. Derive the smallest record shape from the user's requested content and identity convention.
2. Create a declarative profile and the authored records in one minimal document.
3. Do not create placeholder records, fields, or categories not requested by the user.
4. Validate, diagnose, and query representative records before handoff.

For an existing ordinary document:

1. Run `inspect` and examine several representative records, including an incomplete or irregular one when present.
2. Infer the smallest stable boundary, key, and field mapping that preserves current authored structure.
3. If competing interpretations produce different identities, ask the user to choose. Resolve lesser ambiguity conservatively and report it.
4. Add only the contract control block and strictly necessary stable record markers. Do not rewrite business content merely to normalize it.

Place every contract in YAML Front Matter at byte zero, delimited by `---`, with the profile nested under the top-level `mdq` key. Merge `mdq` into an existing complete YAML Front Matter block. If the document has no YAML Front Matter, create one; do not use HTML comments, TOML, or JSON for the contract header. A damaged, unclosed, or non-YAML header requires an explicitly authorized conversion or repair before the document can become contracted. Add `<!-- mdq:record id="..." -->` only when authored headings cannot provide stable record boundaries; record markers are not contract headers.

## Edit a Contracted Document

Use [editing-workflow.md](references/editing-workflow.md) for every authored-record write. The required transaction is:

1. Validate and diagnose the current contract before editing.
2. Resolve the exact target and reject ambiguous identity.
3. Read only the target range and the minimum neighboring style evidence.
4. Classify the mutation and its authorization.
5. Apply a minimal source patch within the authorized range.
6. Revalidate, diagnose, and rerun exact and negative queries.
7. Rebuild a declared index after the source edit succeeds.
8. Inspect the final diff for out-of-scope changes.

Do not use a generic serializer to edit records. Fields backed by `regex` are query-only selectors unless the authored source can be safely patched using an independently located record boundary. Renaming an identity requires checking every in-document reference and reporting external-reference limits.

## Maintain or Repair a Contract

Inspect before changing profile rules, markers, or index policy. Keep the contract minimal and declarative. Preserve an existing valid YAML Front Matter block and its `---` delimiters; never create a second frontmatter block or silently convert another header format without authorization.

After any contract or contracted-record write, run:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" validate <document.md>
uv run "$SKILL_DIR/scripts/mdq.py" diagnose <document.md>
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <representative-id>
```

Check at least the edited or created record, one unaffected record when present, an absent ID, and a phrase that appears only in another record's prose. Review duplicate keys, missing fields, conflicts, orphan markers, heading drift, fallback recovery, and profile errors separately from query matches.

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
- validation diagnostics separately from business content;
- whether markers or an index were created or changed;
- compatibility limits and external references not verified;
- whether any business content outside the requested mutation changed;
- breaking changes and compatibility provisions, explicitly stating when there are none.

## Resources

- `scripts/mdq.py`: inspect, query, search, validate, diagnose, and index Markdown with or without a persistent contract.
- `references/protocol.md`: contract schema, extraction semantics, lifecycle, result contract, diagnostics, compatibility, and security limits.
- `references/editing-workflow.md`: transactional creation, record-editing, contract-maintenance, and verification procedures.
