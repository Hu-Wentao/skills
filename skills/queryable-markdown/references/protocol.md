# MDQ Persistent Query Contract Protocol

Use this reference when creating, querying, editing, reviewing, verifying, optimizing, or repairing a Markdown document governed by an `mdq` profile. Version 1 governs heading-backed records. Version 2 preserves v1 behavior and adds GFM table-row records, actor metadata, named query intents, quality limits, and bounded adaptive maintenance. Keep contracts declarative and small. The Markdown source remains authoritative.

## Contents

1. Document states, operations, and write authority
2. Contract lifecycle
3. Profile placement
4. Complete example
5. Profile schema
6. Record and field extraction
7. Recovery and confidence
8. Result and diagnostic contract
9. Index validity
10. Compatibility and security

## 1. Document States, Operations, and Write Authority

An `mdq` profile is a persistent query contract and optimization for repeated, deterministic extraction. Its absence does not make a Markdown document unqueryable: `query` and `search` may infer temporary selectors from Markdown structure, generic ID headings, and conservative ID labels. Temporary selectors live only in memory and never modify the Markdown or create a sidecar. Report `temporary_selectors_inferred` or `temporary_selectors_applied` so callers can distinguish this mode from a persisted contract.

For non-generic conventions, callers may provide ephemeral `--record-level`, `--key-label`, `--key-pattern`, and `--key-group` arguments. `--record-level` and `--key-label` are repeatable. Apply the same regex length, group validation, and timeout limits as persistent profiles. When no safe record boundary can be recovered, return line-local evidence with `line_local_fallback`; do not fabricate a larger record.

An ordinary request to find, retrieve, summarize, or inspect specific information is read-only, whether the document has a profile or not. The presence of a valid contract enables deterministic editing but does not authorize a write.

The `scan` command applies the same query semantics across one or more explicit Markdown files or bounded directory globs. It deduplicates canonical file paths, rejects paths or globs that escape a selected directory, and reports per-document diagnostics without allowing one invalid document to hide valid matches from another. `--require-contract` makes a missing persistent contract a per-document error. Without it, temporary selectors remain read-only and in memory.

Without a valid contract, authored-content editing is outside this protocol. The only supported write is an explicitly requested creation or conversion into a contracted document. Do not treat a generic request to edit ordinary Markdown as permission to add a contract.

With a valid contract, an explicit request may authorize adding, updating, deleting, renaming, or reorganizing authored records. Resolve each existing target through the contract, reject ambiguous identity, patch only the bounded authorized source, and validate the complete contract after the write. Permission to edit authored content does not implicitly authorize changing the profile, identity scheme, markers, or index policy.

Create or change a profile, insert markers, repair invalid metadata, or change index policy only when the user explicitly requests creation, conversion, contract maintenance, or repair. Rebuilding an already-declared index is an expected derived-cache step after an authorized contracted-document write; it does not expand permission to authored content.

The profile is data, not a script. It may declare selectors, field mappings, tolerance, versioning, named queries, bounded maintenance policy, and a document-relative index path. It must never contain executable commands, code, imports, URLs to follow, or dynamic plugin names.

An ordinary query remains read-only. An mdq v2 `maintenance.query_contract.mode: auto` declaration is durable authority to modify only the declared `mdq` control scopes after deterministic in-memory verification. It does not authorize authored-content, marker, business-value, or index-path changes. Without that declaration, adaptive maintenance is a preview unless the user explicitly requests contract repair.

## 2. Contract Lifecycle

A contracted document moves through these structural states:

- **ordinary**: no declared profile; temporary read-only selectors may be inferred;
- **valid**: one supported profile deterministically resolves its declared structure;
- **drifted**: a valid profile exists but authored structure requires supported recovery or produces warnings;
- **invalid**: a declared profile is conflicting, unsafe, malformed, or unsupported and cannot govern reliable edits.

Creating a new contracted document writes the requested authored records and the smallest query-first contract that addresses them. Define the repeated entity, stable key, reusable queries, match semantics, bounded projection, and result-size limits before choosing the Markdown representation. Converting an existing document describes its current stable structure; it must not normalize or rewrite business content merely to simplify the profile.

Before an authored-record edit, require `valid` or a deliberately accepted `drifted` state whose warnings do not affect the target identity or boundary. Never edit an authored record under an `invalid` contract. Repair first only when repair is authorized.

After every authored-record or contract write, run the matching `check` tier.
The command composes validation, diagnosis, exact/absent identity checks, record
sampling, and v2 named-query verification without transferring each intermediate
JSON envelope to the caller. Rebuild a declared index only after source checks
pass, rerun the affected exact check, and inspect the source diff for changes
outside authorized ranges.

Deletion and identity rename can leave references behind. Search the document and report remaining references; update them only when the request includes reference maintenance and each occurrence is semantically unambiguous. Cross-document reference policy belongs to the calling domain, not this generic contract.

The profile describes extraction, not business validity or field editability. A field extracted by `regex` is not automatically a safe write address. Locate writes through a reliable record boundary and a source-exact span, or stop for clarification.

The `set` command is the only built-in collection mutation in v1. It updates one existing, untransformed `source: label` scalar across records selected by explicit files or directories, optional exact record IDs, and optional exact `FIELD=VALUE` conditions. Repeated IDs form a selection set; repeated conditions use AND semantics. Directory globs select files, not records. The command does not create fields, convert ordinary Markdown, repair contracts, or write fields sourced from `heading`, `section`, `body`, or `regex`.

`set` is a preview unless `--apply` is present. Preflight every processed document and every selected record before writing anything. Require a valid persistent contract, unique structured keys within each document, a declared target field, a non-conflicting existing value, and exactly one source-located label value. Validate every patched source in memory and prepare every declared index before applying the batch. If any preflight error occurs, write no source or index. Before writing, confirm source bytes have not changed since preflight.

A multi-file filesystem mutation cannot provide a portable global atomic commit. Write each source and index through an atomic same-directory replacement, revalidate the written batch, and attempt to restore every replaced path if a later write or verification fails. Report `rolled_back` when restoration succeeds and `rollback_failed` with every restoration error otherwise. Never describe this best-effort rollback as a database transaction.

## 3. Profile Placement

Store exactly one profile in YAML Front Matter at byte zero. Delimit it with `---` and nest the profile under the top-level `mdq` key. For an existing complete YAML Front Matter block, merge the namespaced key:

```yaml
---
title: Product requirements
mdq:
  version: 1
  # Remaining profile keys
---
```

For documents without Front Matter, create the YAML block at byte zero. HTML comment profiles and TOML or JSON contract headers are unsupported. Treat a legacy `<!-- mdq ... -->` declaration or a non-YAML top-level `mdq` declaration as `profile_unsupported` rather than silently falling back to temporary selectors. A damaged, unclosed, or non-YAML header requires an explicitly authorized conversion or repair before adding the contract. Do not create a second Front Matter block or repair unrelated metadata merely to add a profile.

## 4. Complete Example

```yaml
---
mdq:
  version: 1
  dialect: gfm
  records:
    boundary:
      source: heading
      levels: [2]
      level_tolerance: 1
    key:
      source: heading
      pattern: '^(?P<id>REQ-[0-9]+)(?:[ ：:-]+(?P<title>.*))?$'
      group: id
  fields:
    title:
      source: heading
      group: title
    status:
      source: label
      labels: [状态, Status]
    detail:
      source: section
      headings: [详情, Description]
    raw:
      source: body
  tolerance:
    incomplete: true
  index: .mdq/requirements.json
---
```

An mdq v2 table-backed contract may declare reusable access paths and adaptive policy:

```yaml
---
mdq:
  version: 2
  dialect: gfm
  actors:
    read: mixed
    write: machine
  records:
    boundary:
      source: table-row
      under_heading: E2E requirements coverage
      columns: [Requirement, Coverage, Scenarios]
    key:
      source: column
      column: Requirement
      pattern: '^(?P<id>REQ-[A-Z0-9-]+)(?:\s+.*)?$'
      group: id
  fields:
    title:
      source: column
      column: Requirement
      pattern: '^REQ-[A-Z0-9-]+\s+(?P<title>.*)$'
      group: title
    coverage: {source: column, column: Coverage}
    scenarios: {source: column, column: Scenarios}
  queries:
    requirement_by_id:
      when: {pattern: '^REQ-[A-Z0-9-]+$'}
      match: {source: key, operator: eq}
      select: [title, coverage, scenarios]
      expect:
        max_record_lines: 1
        max_record_bytes: 16384
        structured: true
  maintenance:
    query_contract:
      mode: propose
      allow: [queries, fields, records]
      max_changes_per_run: 1
---
```

## 5. Profile Schema

### Top Level

- `version`: Required integer. Use `1` for the frozen heading-record schema or `2` for table records, named queries, actors, and maintenance.
- `dialect`: Optional parser hint. Use `commonmark` or `gfm`; default to `commonmark`. Unknown extensions may be parsed as ordinary source, so inspect and report their compatibility explicitly.
- `records`: Required record-boundary and key declarations.
- `fields`: Optional mapping of output field names to extractors.
- `tolerance`: Optional recovery hints. Recovery must never fabricate content.
- `index`: Optional document-relative sidecar path. Keep it inside the document's project.
- `actors`: Optional in v2. Declare `read` and `write` as `human`, `machine`, or `mixed`. Omission means unspecified behavior, not machine ownership.
- `queries`: Optional v2 mapping of reusable query names to matching, projection, and quality rules. New query-first documents should declare the minimum stable access paths they are built to serve.
- `maintenance`: Optional v2 bounded query-contract maintenance policy.

Unknown non-extension keys should make the profile invalid instead of changing extraction silently. Reserve `x-*` keys for ignored, forward-compatible annotations. Reject duplicate YAML keys.

In both versions, `tolerance.incomplete` controls whether a record with a recoverable key remains queryable when its boundary or fields are incomplete; default it to `false`. All declared fields may be absent: return `null` and `missing_field` rather than inventing a separate required-field policy.

### `records.boundary`

- `source`: Use `heading` in v1. Version 2 also accepts `table-row`.
- `levels`: Expected heading levels, such as `[2]` or `[2, 3]`.
- `level_tolerance`: Optional non-negative integer, default `0`. Consider nearby heading levels only when another rule, normally the key pattern or a marker, confirms identity.
- `pattern`: Optional regex applied to heading text before treating it as a candidate record boundary.

End a record at the next accepted boundary or EOF. Do not require a closing marker.

For `source: table-row`, require `dialect: gfm` and an exact ordered `columns` list. Optionally use `under_heading` to disambiguate identical tables. Each physical data row is one record whose source range is that row only. Duplicate headers, multiple matching tables, multiline rows, or width mismatches prevent deterministic table extraction. Header and delimiter rows are never records.

An explicit `<!-- mdq:record id="..." -->` is a built-in fallback boundary and key evidence regardless of `boundary.source` or `key.source`. Its span starts at the marker and ends at the next marker, accepted record heading, or EOF. If marker and declared key evidence disagree, return both locations with `marker_conflict`; never choose one silently.

### `records.key`

- `source`: `heading`, `label`, or `marker`; v2 also accepts `column` with a `table-row` boundary.
- `pattern`: Optional regex used to extract or validate the key.
- `group`: Named or numbered capture group returned as the key. Default to the complete match. Reject a profile when the referenced group does not exist in the effective pattern.
- `labels`: Required for `source: label`; list accepted spellings such as `[ID, 编号]`.
- `column`: Required for `source: column`; it must exactly name one declared boundary column.

Normalize surrounding whitespace only. Preserve case and punctuation in returned values. Exact query matching may offer case-insensitive candidates but must not silently substitute one.

### `fields.<name>`

Each field declares one source:

- `heading`: Extract from the record heading. Use `pattern` when it differs from the key pattern and `group` for a capture.
- `label`: Extract from label/value lines. Supply `labels` and optionally `pattern`/`group` for the value.
- `section`: Extract source text below a named child heading. Supply `headings`; stop at the next heading of equal or higher level.
- `body`: Return the original Markdown after the marker/record heading through the record end, without inventing structure.
- `regex`: Apply `pattern` separately to bounded, non-code source lines in this record, never as a multiline whole-document expression. Supply `group` when needed.
- `column`: In v2 table-row records, extract the Markdown inline content of the exact declared column. Supply optional `pattern` and `group` for a capture.

Use `null` when a declared field is absent, truncated, or cannot be extracted confidently. Preserve a recovered partial value only when the source range proves it exists, and attach a diagnostic.

### `queries.<name>`

Version 2 query intents contain:

- `when.pattern`: Optional safe input-routing regex. A named `run` rejects values outside it.
- `match.source`: `key` or `field`.
- `match.field`: Required when the source is `field`; name one declared field.
- `match.operator`: `eq` for exact case-sensitive equality or `contains` for case-insensitive literal substring matching.
- `select`: Optional non-empty list of declared fields returned by the named query. Projection does not change source-span quality measurements.
- `expect`: Optional quality mapping with positive integer `max_record_lines`, `max_record_bytes`, or `max_total_bytes`; boolean `structured`; and numeric `min_confidence` from 0 through 1.

Run a named query with `run` and statically check current result sizes with `verify`. A named query returning zero records may be a legitimate absence. Quality limits reject oversized records or payloads; they never require a fabricated match.

### `maintenance.query_contract`

Version 2 accepts:

- `mode`: `locked`, `propose`, or `auto`; absence behaves as `propose`.
- `allow`: Non-empty subset of `queries`, `fields`, and `records`; required when
  `mode` is `auto`.
- `max_changes_per_run`: Positive integer; the current optimizer applies at most one refinement.

`locked` forbids adaptive writes. `propose` returns an in-memory-verified candidate unless an explicit repair request authorizes `--apply`. `auto` durably delegates application within the allowlist. None of these modes authorizes authored-content changes.

## 6. Record and Field Extraction

### Headings

Use Markdown tokens and their source maps first. Ignore heading-like text inside fenced or indented code blocks. Accept ATX and Setext headings when the parser recognizes them.

When a declared heading level drifts within tolerance, require key-pattern or marker confirmation. Lower confidence and emit `heading_level_drift`.

### Labels

Recognize conservative, source-located forms such as:

```md
- 状态：进行中
**状态**: 进行中
状态: 进行中
| 状态 | 进行中 |
```

Match normalized declared labels, not arbitrary substrings. When a scalar field has multiple distinct non-empty values, resolve it to `null` and emit `field_conflict` with every value and location in `details`; identical values may be deduplicated.

### GFM Tables

Use the GFM token structure and row source maps. Match the complete ordered header after trimming surrounding cell whitespace. Preserve inline Markdown text after GFM escape handling; do not render HTML. A pipe inside inline code must be escaped according to GFM table syntax. Keep a table row independently addressable even when the surrounding section contains prose or a document-level marker.

### Stable Markers

Use a marker only when authored structure cannot provide a stable boundary:

```md
<!-- mdq:record id="REQ-123" -->
```

Keep markers outside code blocks and immediately before their records. A marker key may recover identity when a heading or label is incomplete. Report marker/header disagreement as a conflict.

### Incomplete Records

Keep these cases queryable when identity is recoverable:

- Missing optional fields.
- A final record that reaches EOF.
- A heading with changed level but a matching key.
- Partially written prose or list items.
- Mixed supported label styles.
- A stale or missing sidecar index.

Do not address a record whose key cannot be recovered. Report its source range as an orphan candidate when possible.

## 7. Recovery and Confidence

Use these confidence bands consistently:

- `1.0`: Declared selector and expected structure agree.
- `0.9`: Explicit temporary selectors and observed structure agree.
- `0.8`: Identity is explicit but inferred from generic document structure, or persisted structure drifted in a supported way.
- `0.7`: A conservative identity label matched but no safe record boundary was available.
- `0.6`: Tolerant source scanning recovered a declared structure outside the AST baseline.
- Below `0.6`: Return only as a search candidate, not an exact structured match.

Never increase confidence because an AI-generated guess seems plausible. Confidence measures record identity and boundary evidence only. Do not lower it for missing fields or an alternate supported label style; express field absence and conflicts through diagnostics.

Use recovery layers in order:

1. Explicit marker plus declared rules.
2. Declared Markdown token structure.
3. Source-line recovery outside known code ranges.
4. Text-search candidates.

## 8. Result and Diagnostic Contract

The same top-level JSON envelope applies to persisted and temporary queries. For profile-free results, diagnostics identify the temporary selector source, confidence is capped at `0.8` for inferred selectors or `0.9` for explicit selectors, and the default extracted fields are `title` and `body`. Line-local fallback uses `context`. These results are source-located but do not claim the repeatability of a persisted field contract.

Commands emit JSON. A query result should include:

```json
{
  "status": "matched",
  "count": 1,
  "records": [
    {
      "key": "REQ-123",
      "fields": {"title": "Login", "status": null},
      "line_start": 42,
      "line_end": 51,
      "byte_start": 810,
      "byte_end": 1032,
      "confidence": 0.8
    }
  ],
  "candidates": [],
  "diagnostics": []
}
```

The exact `query` command accepts `--output json|minimal|compact|raw`. `json` is
the default and preserves the complete result contract above. The agent-facing
`get` command uses the same matching engine and defaults to `compact`; it does
not change the low-level JSON default. Repeat `--select <field>` on `query` or
`get` to project only declared fields before serialization.

`minimal` is a JSON success projection, not a different matching algorithm: for
one exact match with no candidates or warning/error diagnostics it emits
`status`, `count`, `key`, `fields`, `line_start`, `line_end`, `confidence`, and
informational diagnostic codes. It falls back to the complete JSON envelope for
every other result and remains available for compatibility.

`compact` is an Agent-readable line projection, not a machine-stable protocol.
It emits status, count, keys, source lines, requested fields, and unique
warning/error diagnostic codes. It suppresses routine informational diagnostics
except temporary-selector mode, omits `raw`, `body`, and `context` when smaller
declared fields exist, and tells the caller to rerun with `--output json` when
full ambiguity or failure detail may be required.

`raw` emits the matched record's declared string `fields.raw` followed by a newline. It succeeds only when exactly one structured record matches, no alternate candidates exist, and no warning/error diagnostic would be hidden. It never derives source text from byte ranges, substitutes another field, truncates a match, or selects the first ambiguous record. When raw output is unavailable, emit the complete JSON envelope with an added `raw_output_unavailable` error and exit nonzero. File, encoding, and invalid-profile failures remain complete diagnostic JSON regardless of the selected output format.

Line numbers are one-based and `line_end` is inclusive. Byte ranges are zero-based UTF-8 offsets with an exclusive `byte_end`.

Use top-level status values `matched`, `not_found`, `ambiguous`, or `invalid`. `count` counts structured matches only. Put evidence below confidence `0.6` in `candidates` and do not count it as a match.

Exact key lookup trims the query and remains case-sensitive. A case-insensitive key hit may be returned only as a candidate. Duplicate exact keys return every record with `status: ambiguous`; identity conflict between marker and heading/label puts both alternatives in candidates instead. Text search is a literal substring search, never a regex, and `null` is not an empty string.

Diagnostics should contain a stable `code`, `severity`, human-readable `message`, and a source location when available. Add `details` or `related_locations` when conflicts need to preserve alternatives. Reserve errors for conditions that prevent reliable use of the requested operation. Common codes include:

- `profile_missing`, `profile_invalid`, `profile_unsupported`, `profile_conflict`
- `duplicate_key`, `key_conflict`, `missing_key`, `missing_field`, `field_conflict`
- `heading_level_drift`, `fallback_scan_used`
- `marker_conflict`, `orphan_marker`
- `index_missing`, `index_stale`, `index_invalid`, `index_verified`
- `temporary_selectors_inferred`, `temporary_selectors_applied`, `temporary_selectors_unavailable`
- `temporary_selectors_ignored`, `line_local_fallback`, `body_identity_candidate`
- `ambiguous_match`, `no_match`
- `persistent_contract_required`, `unknown_field`, `field_not_writable`
- `condition_invalid`, `selector_invalid`, `mutation_value_invalid`
- `field_location_ambiguous`, `mutation_preflight_failed`, `mutation_verification_failed`
- `batch_path_conflict`, `source_changed`, `mutation_apply_failed`
- `table_identity_candidate`, `record_granularity_mismatch`, `table_header_duplicate`, `table_row_multiline`, `table_row_width_mismatch`
- `query_contract_missing`, `unknown_query`, `query_input_mismatch`
- `query_record_span_exceeded`, `query_record_payload_exceeded`, `query_total_payload_exceeded`
- `query_unstructured_result`, `query_confidence_below_minimum`
- `query_max_matches_deprecated`
- `raw_output_unavailable`
- `query_contract_repair_planned`, `query_contract_repaired`, `query_contract_repair_ambiguous`, `query_contract_repair_unavailable`
- `query_contract_locked`, `query_contract_scope_denied`, `query_contract_key_loss`

Warnings are valid output for intentionally incomplete documents. Exit nonzero only for command misuse, unreadable input, invalid profiles that block extraction, unsafe index paths, failed writes, or an explicitly requested raw projection that cannot safely be produced.

A collection query uses `schema: mdq.collection.v1` and includes the canonical common root, applied globs, scanned and matched document counts, bounded records and candidates, per-document summaries, collection diagnostics, and a `truncated` flag. Its status is `matched`, `not_found`, `partial`, or `invalid`.

`scan` keeps this JSON envelope by default. The agent-facing `find` command uses
the same collection engine with compact output by default; both accept repeated
`--select` field projections. Named `run` queries also retain JSON by default
and accept `--output compact` for Agent use.

A collection mutation uses `schema: mdq.mutation.v1`. It includes `applied`, scanned and changed document counts, selected and changed record counts, source-located before/after entries, per-document summaries, rebuilt index paths, and diagnostics. Preview status is `planned`, `unchanged`, `not_found`, or `invalid`; applied status is `updated`, `unchanged`, `rolled_back`, or `rollback_failed`.

A named query uses `schema: mdq.query.v2` and includes the query name, value, projected records, quality status, measured count and source sizes, and diagnostics. Query verification uses `schema: mdq.verify.v2` with per-query current selectivity and worst observed bucket. Adaptive repair uses `schema: mdq.optimize.v2`; it is a read-only `planned` result unless `--apply` writes a verified candidate.

Scripted edit verification uses `schema: mdq.check.v1`. Its tiers are `content`,
`structure`, and `contract`; JSON output contains each composed check and full
result, while compact output emits one pass/fail summary, affected records,
sample keys, and diagnostic codes. `--id` means exactly one match is expected;
`--absent-id` means no structured match is expected.

## 9. Index Validity

Store at least:

- Index schema, protocol, and engine versions.
- Canonical source path.
- SHA-256 of the exact source bytes.
- SHA-256 of the normalized profile.
- Extracted records, fields, confidence, diagnostics, and source ranges.

Canonicalize the parsed profile as UTF-8 JSON with sorted keys and no insignificant whitespace before hashing. Accept an index candidate only when both hashes and all supported schema/engine versions match, then compare its records with a fresh deterministic extraction before answering. On mismatch or corrupt cache data, answer from the current source, attach `index_stale` or `index_invalid`, and leave the stale file untouched during an ordinary query. Rebuild or rewrite it only as part of an authorized contracted-document write or an explicit index-maintenance request.

When `index` is absent, parse without writing. Resolve a relative index path against the Markdown file's directory. Its real path must remain inside that directory tree, must not equal or alias the source document, and must not be a symlink. Reject every other path during validation and refuse query/index operations while it is unsafe.

## 10. Compatibility and Security

- Parse CommonMark/GFM structure without rendering HTML. Mask only the content of HTML comments so surrounding headings and labels remain visible. Treat `pre`/`code`/`script`/`style` blocks, capitalized MDX component blocks whose opening tag ends on the same line, and Hugo `highlight` blocks as opaque. Multiline MDX opening tags and other extension syntax are not guaranteed opaque in v1; inspect and report them as compatibility limits before preparing such a document.
- Limit profile regex length and apply regex only to bounded heading, field, or record text. Enforce a per-match timeout and return `regex_timeout` instead of continuing after the limit.
- Reject YAML aliases and duplicate mapping keys so a small control-plane profile cannot expand into an unbounded object graph.
- Never execute commands from a profile.
- Never follow imports, URLs, symlinks, or dynamic plugin names declared by a document.
- Collection writes reject explicit or matched Markdown symlinks. Collection reads do not follow matched symlink files.
- Label-field mutation values are non-empty single-line text without surrounding whitespace. The v1 field result remains text, so writing `false` returns the string `"false"` rather than a typed YAML boolean.
- Do not store prose embeddings or external service credentials in the profile or sidecar.
- Keep the protocol versioned. New engines must preserve v1 extraction. Old engines fail closed on v2 profiles because they reject unknown versions and selectors; never downgrade or reinterpret a v2 table contract as v1.
- Accept a positive legacy v2 `expect.max_matches` value for migration, ignore it during quality evaluation, and emit `query_max_matches_deprecated`. New or rewritten contracts must omit it; duplicate exact keys remain structural `duplicate_key` ambiguity rather than a query-quality budget.
- An optimizer may replace only the source-located top-level `mdq:` block. Preserve every other Front Matter key and every authored body byte, compare the source hash immediately before apply, reparse the proposed bytes in memory, preserve existing structured keys, and refuse ambiguous candidate schemas.
