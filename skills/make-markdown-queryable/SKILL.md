---
name: make-markdown-queryable
description: Query specific information from manually maintained, incomplete, semi-structured Markdown without loading the whole file into model context, with or without mdq metadata. Use for exact or text lookups in requirement catalogs and similar Markdown, or when the user explicitly asks to make a document persistently queryable, add or maintain an mdq YAML profile, diagnose profile drift, or restore queryability. Ordinary queries are read-only; add or change mdq metadata, record markers, or indexes only when the user explicitly requests a persistent queryability change.
---

# Make Markdown Queryable

Query imperfect Markdown in one of two modes:

- **Read-only query:** Query a document with or without an `mdq` profile. Use existing metadata when valid; otherwise let the CLI infer temporary in-memory selectors and return source-located evidence.
- **Persistent query contract:** On an explicit user request, add or repair a small declarative YAML `mdq` profile and optionally stable markers or a sidecar index.

The profile is a reusable optimization and contract for deterministic, source-located queries. It is not a prerequisite for answering a one-off question.

## Core Rules

- Treat the Markdown file as the source of truth and the index as disposable cache.
- Keep ordinary lookups read-only. A request to find, retrieve, summarize, or check specific information does not authorize document preparation.
- Add or change an `mdq` profile, record markers, or an index only when the user explicitly asks to make, persist, update, or repair the document's queryability.
- Preserve authored bytes outside the inserted profile and any explicitly necessary record markers. Never round-trip the document through a Markdown renderer.
- Put declarations in the profile; never put shell, Python, dynamic imports, or other executable code in the document.
- Return missing values as `null`. Never invent IDs, titles, field values, closing sections, or repaired prose.
- Return every duplicate or ambiguous match with diagnostics. Never silently select the first result.
- Prefer exact IDs and declared fields. Use text search only for candidate discovery.
- Treat a successful Markdown parse as syntax evidence, not proof that business records are complete.

## Workflow

### 1. Classify the Request

Default to **read-only query**. Examples include “find REQ-123,” “what is this requirement's status?”, and “search this Markdown for login requirements.” Do not add metadata merely because a durable profile would improve later queries.

Enter **persistent query contract** mode only when the user explicitly asks to make the document queryable, save or add query metadata, create an index, update an existing query contract, or repair broken queryability. An explicit invocation of the skill alone does not authorize writes when the requested action is only a lookup.

### 2. Answer a Read-Only Query

Resolve `SKILL_DIR` to the directory containing this file. Invoke the same commands whether or not the document has a profile:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <exact-id>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --text <term>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --field <field> --text <term>
```

With a valid profile, the CLI applies its declared boundaries, keys, fields, and index policy. Without a profile, it infers temporary selectors from generic ID headings, conservative ID labels, and heading structure. Those selectors exist only in memory; `query` and `search` never persist them or create a sidecar. Interpret JSON using `count`, `confidence`, source ranges, and `diagnostics` together.

Automatic inference is conservative. A key declared by a heading or accepted identity label may be a structured match; an ID mentioned only in prose remains a low-confidence candidate. When no safe section boundary exists, the CLI returns line-local evidence instead of inventing a record.

When the document uses a recognizable but non-generic convention, pass temporary selectors explicitly:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> \
  --id <exact-id> \
  --record-level 3 \
  --key-label Ref \
  --key-pattern '^(?P<id>ticket_[0-9]+)$' \
  --key-group id
```

`--record-level` and `--key-label` are repeatable. The CLI applies regex length, group, and timeout checks to temporary patterns just as it does to persisted patterns. Explicit temporary selectors still do not authorize or perform writes.

If automatic results are ambiguous, run the read-only inspector:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" inspect <document.md>
```

Use its headings, labels, IDs, code regions, and suggested profile to choose temporary selector arguments or to read only the returned source ranges. Never silently choose the first hit or infer missing values.

An invalid or conflicting declared profile is different from an absent profile: report the error instead of silently ignoring the document's contract. Use `inspect` and bounded manual reads only if the user still needs the one-off answer; do not repair metadata without explicit authorization.

### 3. Inspect for Persistent Preparation

In persistent query contract mode, run `inspect` before editing. Inspect existing frontmatter, heading levels, likely record boundaries, ID shapes, repeated labels, code fences, and custom syntax such as MDX or Hugo shortcodes. Read `references/protocol.md` before creating or changing a profile.

Infer the smallest useful profile from several representative records, including at least one incomplete or irregular record when present. If two interpretations would produce different record identities, show the competing mappings and ask the user to choose. Resolve lesser ambiguity with a conservative profile and report it.

### 4. Add or Repair a Persistent Query Profile

Perform this step only in persistent query contract mode.

Use one of these locations:

1. Merge an `mdq` key into complete YAML frontmatter.
2. Insert an `<!-- mdq ... -->` YAML block at byte zero when there is no frontmatter, or immediately after complete YAML/TOML/JSON frontmatter.
3. For damaged/unclosed frontmatter, insert the comment profile at byte zero so the engine never guesses a metadata boundary.
4. Use `<!-- mdq:record id="..." -->` markers only when headings cannot reliably separate records and the persistent queryability request authorizes the change.

Apply a minimal patch. Preserve existing YAML/TOML/JSON delimiters and never convert one frontmatter format into another. When frontmatter is incomplete or ambiguous, put the HTML comment profile before it instead of repairing unrelated metadata.

The profile must contain only declarative YAML data describing boundaries, keys, fields, tolerance, and an optional index path. Never embed commands or code to be evaluated.

### 5. Validate Persistent Recovery

Run both commands after changing a profile:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" validate <document.md>
uv run "$SKILL_DIR/scripts/mdq.py" diagnose <document.md>
```

Review duplicate keys, missing fields, orphan markers, unmatched headings, fallback recovery, and profile errors. Warnings are expected for intentionally incomplete documents; distinguish recoverable warnings from failures that prevent record identity.

Verify representative lookups:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <exact-id>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --text <term>
uv run "$SKILL_DIR/scripts/mdq.py" search <document.md> --field <field> --text <term>
```

Check at least one exact record, one incomplete record, one ambiguous or absent query, and one phrase that appears inside another record's prose. Confirm line and byte ranges against the source.

### 6. Build an Optional Index

Build an index only during an explicitly authorized persistent queryability change, when the profile declares an index path and the document is large or queried repeatedly:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" index <document.md>
```

On query, accept an index candidate only when its source/profile hashes and records agree with a fresh deterministic extraction. If a user edit makes it stale or cache contents are corrupt, use the parser result returned by the command. Never rebuild or rewrite the index during an ordinary query. Treat the v1 sidecar as verified location cache, never as an authority that bypasses current source parsing.

## Recovery Policy

Use recovery in this order:

1. Explicit record markers and declared selectors.
2. Markdown token structure with source maps.
3. Tolerant source-line scanning outside known code blocks.
4. Candidate-only text search.

Lower confidence and emit a diagnostic whenever a lower recovery layer is used. A record that reaches EOF without another boundary is still queryable. A record without a recoverable key is diagnostic evidence, not an addressable record.

## Verification and Handoff

- For a read-only query, report matches, source locations, ambiguity, and whether an existing profile or profile-free inspection was used. Confirm that no document metadata, markers, or index was changed.
- For a persistent queryability change, keep the body diff empty unless stable markers were necessary.
- For a persistent queryability change, report the chosen record boundary, key rule, field mappings, and fallback behavior.
- Report validation diagnostics separately from query matches.
- List compatibility limits for the document dialect and any index path created.
- State explicitly whether any body markers were inserted and whether any business content was changed.

## Resources

- `scripts/mdq.py`: inspect, query, and search Markdown with or without a profile; validate, diagnose, and index a profiled document.
- `references/protocol.md`: profile schema, extraction semantics, result contract, diagnostics, compatibility, and security limits.
