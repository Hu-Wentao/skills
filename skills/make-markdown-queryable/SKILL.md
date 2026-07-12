---
name: make-markdown-queryable
description: Transform manually maintained, incomplete, semi-structured Markdown into a fault-tolerant queryable document, and query it without loading the whole file into model context. Use when Codex needs to add or maintain an mdq query profile, infer record boundaries and fields, index requirement catalogs or similar Markdown, perform exact or text lookups, diagnose structure drift after manual edits, or restore queryability without rewriting authored content.
---

# Make Markdown Queryable

Add a small declarative `mdq` profile near the document header. Use the bundled parser to turn that profile into deterministic, source-located query results while tolerating missing fields, duplicate IDs, heading drift, and stale indexes.

## Core Rules

- Treat the Markdown file as the source of truth and the index as disposable cache.
- Preserve authored bytes outside the inserted profile and any explicitly necessary record markers. Never round-trip the document through a Markdown renderer.
- Put declarations in the profile; never put shell, Python, dynamic imports, or other executable code in the document.
- Return missing values as `null`. Never invent IDs, titles, field values, closing sections, or repaired prose.
- Return every duplicate or ambiguous match with diagnostics. Never silently select the first result.
- Prefer exact IDs and declared fields. Use text search only for candidate discovery.
- Treat a successful Markdown parse as syntax evidence, not proof that business records are complete.

## Workflow

### 1. Inspect Before Editing

Resolve `SKILL_DIR` to the directory containing this file, then run:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" inspect <document.md>
```

Inspect existing frontmatter, heading levels, likely record boundaries, ID shapes, repeated labels, code fences, and custom syntax such as MDX or Hugo shortcodes. Read `references/protocol.md` when creating or changing a profile.

Infer the smallest useful profile from several representative records, including at least one incomplete or irregular record when present. If two interpretations would produce different record identities, show the competing mappings and ask the user to choose. Resolve lesser ambiguity with a conservative profile and report it.

### 2. Add the Query Profile

Use one of these locations:

1. Merge an `mdq` key into complete YAML frontmatter.
2. Insert an `<!-- mdq ... -->` YAML block at byte zero when there is no frontmatter, or immediately after complete YAML/TOML/JSON frontmatter.
3. For damaged/unclosed frontmatter, insert the comment profile at byte zero so the engine never guesses a metadata boundary.
4. Use `<!-- mdq:record id="..." -->` markers only when headings cannot reliably separate records.

Apply a minimal patch. Preserve existing YAML/TOML/JSON delimiters and never convert one frontmatter format into another. When frontmatter is incomplete or ambiguous, put the HTML comment profile before it instead of repairing unrelated metadata.

### 3. Validate Recovery

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

### 4. Build an Optional Index

Build an index only when the profile declares an index path and the document is large or queried repeatedly:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" index <document.md>
```

On query, accept an index candidate only when its source/profile hashes and records agree with a fresh deterministic extraction. If a user edit makes it stale or cache contents are corrupt, use the parser result returned by the command; rebuild the index only when writes are in scope. Treat the v1 sidecar as verified location cache, never as an authority that bypasses current source parsing.

### 5. Query Existing Documents

Invoke the bundled command directly instead of reading the entire Markdown into context. Interpret its JSON result using `count`, `confidence`, source ranges, and `diagnostics` together.

If the profile is missing or invalid, run `inspect`; do not improvise a fragile one-off regex unless the user requests an ad hoc search. If structure has drifted, adjust the profile or add the smallest stable marker, rerun validation, and show the document diff.

## Recovery Policy

Use recovery in this order:

1. Explicit record markers and declared selectors.
2. Markdown token structure with source maps.
3. Tolerant source-line scanning outside known code blocks.
4. Candidate-only text search.

Lower confidence and emit a diagnostic whenever a lower recovery layer is used. A record that reaches EOF without another boundary is still queryable. A record without a recoverable key is diagnostic evidence, not an addressable record.

## Verification and Handoff

- Keep the body diff empty unless stable markers were necessary.
- Report the chosen record boundary, key rule, field mappings, and fallback behavior.
- Report validation diagnostics separately from query matches.
- List compatibility limits for the document dialect and any index path created.
- State explicitly whether any body markers were inserted and whether any business content was changed.

## Resources

- `scripts/mdq.py`: inspect, validate, diagnose, query, search, and index a profiled Markdown document.
- `references/protocol.md`: profile schema, extraction semantics, result contract, diagnostics, compatibility, and security limits.
