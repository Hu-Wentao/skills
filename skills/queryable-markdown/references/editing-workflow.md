# Contracted Markdown Editing Workflow

Use this workflow only for a document with a valid persistent `mdq` contract, or while completing an explicitly requested creation, conversion, or repair. The contract provides structural evidence; the user's request provides write authority.

## Contents

1. Transaction invariants
2. Preflight
3. Create a contracted document
4. Add a record
5. Update a record
6. Rename a record identity
7. Delete a record
8. Change the contract
9. Verify and hand off

## 1. Transaction Invariants

- Refuse an authored-record edit when the declared contract is invalid, conflicting, or unsupported. Repair it first only when repair is authorized.
- Resolve an existing target by exact, case-sensitive identity. Do not edit candidates, duplicate matches, line-local fallbacks, or confidence below the structured-match threshold.
- Preserve source formatting and bytes outside the authorized control or record range.
- Never infer missing business values. Ask for material content decisions or leave the source unchanged.
- Treat profile validation as structure validation, not content approval.
- Update a declared sidecar index only after the Markdown write passes source validation.
- Inspect the final diff even when all commands succeed.

## 2. Preflight

For an existing contracted document, run:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" validate <document.md>
uv run "$SKILL_DIR/scripts/mdq.py" diagnose <document.md>
```

Stop the record edit if either command reports an error that prevents reliable identity or boundaries. Warnings about deliberately absent optional fields may be acceptable; record them for the handoff.

For an update, rename, or delete, query the exact ID and require one structured match:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <exact-id>
```

Use the returned line and byte range to read the target. Read one adjacent record only when needed to preserve authored layout. Before adding or renaming, query the proposed ID and require `not_found`; a case-insensitive candidate still requires review.

Classify requested writes independently:

- authored record content;
- record identity;
- contract profile;
- stable marker;
- sidecar index.

Do not broaden permission from one class to another. For example, permission to update a record does not authorize changing its key pattern or normalizing every record.

## 3. Create a Contracted Document

When creating a new document:

1. Select an explicit record key convention from the user's domain.
2. Choose the simplest authored boundary, normally headings.
3. Map only fields required for expected deterministic queries.
4. Write the contract and requested authored content together.
5. Avoid empty example records, speculative fields, and generated indexes unless repeated or large-document queries justify one.
6. Validate and query every initial record when the document is small; otherwise sample the first, last, incomplete, and irregular records.

When converting an existing ordinary document, run `inspect` first. Prefer a profile that describes the existing document. Add markers only when its authored structure cannot delimit records reliably. Conversion does not authorize rewriting prose, headings, labels, or frontmatter for cosmetic consistency.

## 4. Add a Record

1. Query the proposed exact key and review case-insensitive candidates.
2. Locate the insertion point from authored ordering or an explicit user instruction. Do not invent chronological, priority, or status ordering.
3. Copy only structural style from a neighboring record; do not copy its business values.
4. Include the minimum fields supplied or required by the requested record shape. Leave absent declared fields absent rather than writing guessed placeholders.
5. Apply one bounded source patch.
6. Query the new key and verify its extracted fields and source range.
7. Query a neighboring unaffected record to ensure boundaries did not merge or split.

## 5. Update a Record

1. Require exactly one structured match for the current key.
2. Read the target record and identify the smallest authored span containing the requested field or prose.
3. Preserve labels, heading level, whitespace style, and unrelated fields unless the request changes them.
4. For a missing field, insert it in the document's established location and style. Do not create a new style solely for normalization.
5. If the source contains conflicting values for a scalar field, do not silently select one. Show the conflict or resolve all conflicting authored locations only when the requested value is unambiguous.
6. Requery the record and compare every requested value with extracted output.

A `regex` field declaration is an extraction rule, not a safe write address. Patch its containing record only when the authored source location is independently clear and bounded.

## 6. Rename a Record Identity

Treat an identity rename as a higher-risk edit:

1. Require one exact match for the old key and no exact match for the new key.
2. Search the complete document for both keys outside the target record.
3. Update the identity source: heading, identity label, or marker.
4. Update in-document references only when the user's request includes the rename's references and each occurrence is semantically a reference rather than example text.
5. Requery both keys: the new key must match once and the old key must not match.
6. Report that references outside the document were not verified unless a broader repository search was explicitly in scope.

Never reuse a removed key when the document's domain forbids identity reuse. That rule belongs to the domain or governance source, not to the generic query contract.

## 7. Delete a Record

1. Require one exact structured match.
2. Confirm the requested operation is deletion rather than deprecation, archival, or status change; do not choose a lifecycle policy for the user.
3. Delete exactly the record range, including its immediately associated marker when present.
4. Preserve surrounding blank-line style without reformatting neighboring records.
5. Verify the deleted key is absent and both neighboring records retain their original boundaries.
6. Search for remaining in-document references and report them. Remove them only when authorized and semantically unambiguous.

## 8. Change the Contract

Run `inspect` before changing boundaries, key rules, field mappings, tolerance, markers, or index paths. A contract change can reinterpret every record even when the body diff is empty.

Apply the smallest profile patch and then verify:

- every previously addressable representative key remains addressable unless the change intentionally migrates it;
- no new duplicate or orphan identities appear;
- field conflicts and missing fields are visible rather than normalized away;
- supported fallback confidence does not hide a boundary regression;
- the index path remains contained, distinct from the source, and non-symlinked.

When a contract migration changes record identity or extracted semantics, report it as a breaking change even if the Markdown body is unchanged.

## 9. Verify and Hand Off

After any successful source or contract patch, run:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" validate <document.md>
uv run "$SKILL_DIR/scripts/mdq.py" diagnose <document.md>
uv run "$SKILL_DIR/scripts/mdq.py" query <document.md> --id <affected-id>
```

Also query an unaffected record and an absent key, and run a literal search whose text appears in a different record. For deletion or rename, query the old identity as the negative case.

If the profile declares an index, rebuild it only after these checks pass:

```bash
uv run "$SKILL_DIR/scripts/mdq.py" index <document.md>
```

Then rerun the affected exact query and confirm the index is verified against fresh parsing. Inspect the final diff for unauthorized control-region, record, or formatting changes.

Report the operation type, affected keys, contract changes, markers, index changes, diagnostics, compatibility limits, unresolved references, and whether any unrelated authored content changed.
