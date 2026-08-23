# Query-First Design and Adaptive Repair

Use this reference when creating or converting a contracted document, declaring reusable query intents, diagnosing excessive or oversized results, or refining the `mdq` control block. Read [protocol.md](protocol.md) for the schema and [editing-workflow.md](editing-workflow.md) for source transactions.

## Contents

1. Design the access contract first
2. Choose the physical representation
3. Declare reusable queries and quality limits
4. Verify a new or converted document
5. Classify query-quality failures
6. Generate and prove a repair
7. Apply bounded adaptive maintenance

## 1. Design the Access Contract First

Do not start with headings, tables, or markers. First identify:

- the repeated domain entity;
- its stable, source-located key;
- high-frequency exact and field queries;
- the fields each query should return;
- expected match semantics and maximum result size;
- fields that must be safely writable;
- primary read and write actors.

Treat a document heading as a container, not a record, when stable inner entities are independently queried. Requirements, tickets, scenarios, controls, and catalog entries normally form records even when presented in one table under one heading.

Persist only reusable access paths. Do not add a named query for a single literal lookup or create fields that no expected query consumes.

## 2. Choose the Physical Representation

Use the query and write shape to choose the source form:

For new AI-generated or AI-maintained authored content, use a heading hierarchy with nested sections or labels by default. Do not add a Markdown table only for compactness. Preserve an existing table unless the user explicitly authorizes conversion; choose a table for new content only when the user requests it or a flat matrix is essential to the document's intended representation.

| Shape | Preferred representation |
| --- | --- |
| Prose-rich records, frequent machine edits | One heading or marker per record with stable labels |
| Flat repeated rows, human or mixed readers | GFM table with `table-row` boundaries and `column` keys and fields |
| Machine-only read and write | Prefer heading-based record blocks over wide tables unless an existing flat table must be preserved |
| Narrative document with no repeated identity | Heading records only when headings are truly independently addressed |

`actors.read` and `actors.write` accept `human`, `machine`, or `mixed`. `machine` includes deterministic scripts and AI agents. Actor metadata guides representation; it never grants write authority.

## 3. Declare Reusable Queries and Quality Limits

An mdq v2 named query declares input routing, matching, projection, and expected quality:

```yaml
queries:
  requirement_by_id:
    when:
      pattern: '^REQ-[A-Z0-9-]+$'
    match:
      source: key
      operator: eq
    select: [title, coverage, e2e_scenarios]
    expect:
      max_record_lines: 1
      max_record_bytes: 16384
      structured: true
```

Use `source: key` for identity. Use `source: field` with a declared `field` for reusable filters. Use `operator: eq` when the domain has exact values and `contains` only when substring behavior is intended.

Quality limits have distinct meanings:

- `max_record_lines`: maximum source span for one result;
- `max_record_bytes`: maximum source bytes for one result;
- `max_total_bytes`: maximum source bytes across all results;
- `structured`: require source-located record identity rather than candidate evidence;
- `min_confidence`: minimum structural confidence.

Do not repair ambiguous identity with output truncation. `limit: 1`, first-match selection, or a smaller projection can reduce output but cannot resolve duplicate keys. Projection repairs payload size only; selector or boundary repairs precision.

## 4. Verify a New or Converted Document

Run one composed contract check, passing representative identities when known:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" check <document.md> \
  --tier contract \
  --id <first-id> \
  --id <middle-id> \
  --id <last-id> \
  --absent-id <absent-id>
```

Then exercise:

1. known first, middle, and last identities;
2. an absent identity matching the key syntax;
3. text that mentions another record ID only in prose;
4. each named query with representative low- and high-frequency values;
5. an incomplete or irregular record when present.

Reject the initial design when repeated stable inner identities substantially outnumber extracted records, exact keys resolve through body text, duplicate keys exist, or result spans exceed declared budgets.

## 5. Classify Query-Quality Failures

Use these repair classes in order:

| Failure | Evidence | Candidate repair |
| --- | --- | --- |
| Exact ID missing but unique table column contains it | Consistent header, unique patterned values, one matching table | Refine to `table-row` boundary and `column` key |
| Total payload is too large because a broad field matches irrelevant records | One declared field produces a smaller result satisfying the same input semantics and expectations | Persist that field selector |
| One match covers a giant wrapper | Stable nested headings, markers, or table rows | Refine the record boundary |
| Payload too large but identity and boundary are correct | Query consumes fewer declared fields | Narrow `select` only |
| Duplicate exact keys | Multiple source identities | Do not choose one; require a deterministic scope or user decision |
| Many results are allowed by `expect` | No quality violation | Do not repair |

Treat a zero-result exact query and a one-result giant body as different failures. Inspect candidate distribution and source spans before proposing a change.

## 6. Generate and Prove a Repair

Run `optimize` without `--apply` first. A deterministic repair must:

1. derive from observable headings, labels, markers, table headers, column values, and declared fields;
2. generalize to a stable pattern rather than embed the current literal value;
3. be the only candidate with the best valid selectivity;
4. validate as a complete profile in memory;
5. make the triggering query satisfy every declared quality limit;
6. preserve every previously structured key unless the authorized migration explicitly breaks identity;
7. introduce no duplicate or overlapping record ranges;
8. leave every byte outside the top-level `mdq:` control block unchanged.

For a boundary repair, query another unaffected identity and an absent identity. For a selector repair, confirm the new field is declared and the same operator semantics remain valid. Refuse automatic repair when multiple tables, columns, fields, or scopes are equally plausible.

## 7. Apply Bounded Adaptive Maintenance

Declare durable maintenance separately from actor metadata:

```yaml
maintenance:
  query_contract:
    mode: auto
    allow: [queries, fields, records]
    max_changes_per_run: 1
```

Modes:

- `locked`: never apply adaptive contract changes;
- `propose`: return a verified candidate profile without writing; default when absent;
- `auto`: allow the skill to apply one verified repair within the required explicit
  `allow` scopes.

An explicit user request to repair the query contract may apply a preview under `propose`. `locked` remains a document-owned prohibition. `auto` does not authorize authored-content edits, marker changes, index-path changes, or business-value changes.

Apply the control-block patch through an atomic same-directory replacement after confirming the source hash is unchanged. Reparse the written source, rerun the triggering query, run `verify`, rebuild an already-declared index, and inspect the diff. Roll back the control block when post-write validation fails. Report the old and new query behavior, changed scopes, compatibility impact, and whether authored content remained byte-identical.
