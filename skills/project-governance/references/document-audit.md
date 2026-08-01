---
mdq:
  version: 1
  dialect: gfm
  records:
    boundary:
      source: heading
      levels: [1]
      pattern: '^Document Audit Policy$'
    key:
      source: marker
  fields:
    title:
      source: heading
    raw:
      source: body
  tolerance:
    incomplete: true
---
<!-- mdq:record id="GOV-DOCUMENT-AUDIT" -->
# Document Audit Policy

This policy is the compatibility surface for configured `document-audit`
tasks. Prefer [document-maintenance.md](document-maintenance.md) and its
`inspect`, `plan`, `maintain`, and `verify` operations for new workflows.
`docs audit` remains a read-only compatibility operation with its existing
output schema; `docs verify` adds lifecycle-field maintenance checks.

Use deterministic discovery and validation for Markdown contracts, local links,
stable requirement and defect identifiers, lifecycle indexes, and verification
references.

Require every governed requirements, baseline, plan, dependency evaluation,
defect, archive, coverage, verification, or traceability Markdown document to
have a valid persistent mdq contract. Run queryable-markdown collection
validation across the governed paths; a textual `mdq:` mention is not proof of
a valid contract. Treat a missing contract, invalid profile, unsafe index path,
ambiguous identity, or undeclared lifecycle field required by the project as
structural drift.

Treat missing or inconsistent structure as evidence, not as authority to change
product semantics. Do not infer requirement status, plan completion, priority,
or ownership from filenames, document age, or passing tests. Report semantic
drift as a decision request unless one authoritative source makes the repair
mechanical and editing is authorized.
