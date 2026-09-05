---
mdq:
  version: 1
  records:
    boundary: {levels: [1], pattern: '^Shared MDQ Profile$'}
    key: {source: marker}
  fields:
    title: {source: heading}
    raw: {source: body}
  tolerance: {incomplete: true}
---
<!-- mdq:record id="GOV-SHARED-MDQ-PROFILE" -->
# Shared MDQ Profile

Use the versioned shared profile for project-governed documents that represent
records as level-2 headings with structured IDs such as `REQ-001`, `PLAN-001`,
`Q-001`, or `DECISION-001`. The profile exposes the title, status, review
level, source, and raw record body.

## Profile Identity

- Reference: `project-governance/governed-document-v1`
- Asset: `assets/mdq-profiles/governed-document-v1.yaml`
- Profile version: `1`
- mdq protocol version: `1`

Reference it from YAML Front Matter instead of copying the complete extraction
contract into every document:

```yaml
---
mdq:
  profile: project-governance/governed-document-v1
---
```

A reference is the complete `mdq` declaration. Do not combine it with inline
`version`, `records`, `fields`, tolerance, query, maintenance, or index keys.
Use a normal inline contract when the document has a different boundary, key
scheme, field vocabulary, or query requirement. `README.md` remains ordinary
and must not reference the profile.

## Resolution and Safety

`queryable-markdown` resolves the namespace only to the sibling skill asset at
`<skills-root>/project-governance/assets/mdq-profiles/`. A document cannot
supply a filesystem path, URL, import, command, or plugin. Missing, malformed,
ambiguous, unversioned, or metadata-mismatched references are invalid and must
not fall back to temporary selectors for a write.

The resolved profile participates in the normal profile hash. A profile change
therefore invalidates an older derived index. Document mutations may update
only authored record bytes; the mdq optimizer must not rewrite a shared profile
through one consuming document.

## Version Policy

Treat `governed-document-v1` as immutable after publication. Any change to
record identity, boundaries, field extraction, tolerance, or compatibility
semantics creates a new asset and reference such as `governed-document-v2`.
Keep the old asset while documents still reference it. The filename suffix,
`x-profile-id`, `x-profile-version`, and mdq `version` must agree.

Changing a document from one profile version to another is a contract migration,
not an incidental content edit. Inspect the document first, compare exact keys
and representative fields before and after the migration, then run:

```bash
uv run <queryable-markdown-root>/scripts/mdq.py check <document.md> \
  --tier contract
```

Preserve existing inline contracts unless migration is explicitly authorized.
