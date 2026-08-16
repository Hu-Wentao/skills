---
status: active
authority_level: operational_workflow
lifecycle: active
verification_owner: project-governance-test-suite
mdq:
  version: 2
  dialect: gfm
  actors:
    read: mixed
    write: mixed
  records:
    boundary:
      source: heading
      levels: [1]
      pattern: '^Test-Case Development$'
    key:
      source: marker
  fields:
    title:
      source: heading
    status:
      source: label
      labels: [Status]
    authority_level:
      source: label
      labels: [Authority Level]
    lifecycle:
      source: label
      labels: [Lifecycle]
    verification_owner:
      source: label
      labels: [Verification Owner]
    raw:
      source: body
  queries:
    record_by_id:
      when:
        pattern: '^GOV-TEST-CASE-DEVELOPMENT$'
      match:
        source: key
        operator: eq
      select: [title, status, authority_level, lifecycle, verification_owner, raw]
      expect:
        max_record_lines: 120
        max_record_bytes: 16384
        structured: true
  tolerance:
    incomplete: true
---
<!-- mdq:record id="GOV-TEST-CASE-DEVELOPMENT" -->
# Test-Case Development

- Status: active
- Authority Level: operational_workflow
- Lifecycle: active
- Verification Owner: project-governance-test-suite

This record is the active operational workflow for selecting governed test
cases as implementation and verification inputs. Product requirements,
accepted baselines, API or UI contracts, and explicit product decisions remain
higher authorities. A test case never creates or changes product semantics.

## Resolve the Workflow

Resolve the managed `test-case-development` task, then use `testcases inspect`,
`testcases plan`, or `testcases verify`. The repository owns catalog paths,
governance-document status gates, requirement-authority state, and CSV column
mapping in `.agents/skills-config/project-governance/test-case-workflow.json`.
The skill owns invariant result vocabulary and read-only operation behavior.

`inspect` reports catalog structure, source identity, review status, and
eligibility. `plan` selects one stable case ID and fails closed unless its
governance document is eligible, requirement authority is resolved, the case
exists, and its requirement, title, steps, and expected result are present.
`verify` reads the selected case's latest result snapshot. None of these
operations edits code, test artifacts, requirements, lifecycle status, or
release evidence.

## Apply a Case to Development

1. Start from a requirement, accepted plan, defect, or explicitly selected case
   and use impact analysis to choose the smallest relevant case set. Do not run
   the full catalog by default.
2. Run `testcases plan --catalog <catalog> --case-id <id>`. Treat
   `decision_required` as a hard stop for implementation from that case.
3. Compare the selected case with requirements, baselines, contracts, current
   code, and existing executable tests. Resolve every semantic conflict in
   favor of the applicable higher authority or obtain a product decision.
4. When the case is structurally eligible and semantically consistent, use the
   repository's normal implementation workflow, including `git-worktree`
   ownership when implementing a plan or specification. Keep the case ID in the
   implementation and verification handoff.
5. Assign the smallest effective verification owner. Automate stable behavior
   at the focused, UI, API, integration, or E2E layer that directly proves it;
   leave environment or operational guarantees with their named manual owner.
6. Run the affected checks and `testcases verify`. A PASS result is evidence
   only for the behavior and environment recorded by that case. It does not
   activate a requirement, complete a plan, prove all acceptance clauses, or
   authorize release.

## Handle Ineligible or Conflicting Cases

`draft_unreviewed`, missing requirement authority, incomplete case content,
duplicate IDs, or conflicts with higher-authority sources require a decision.
The implementation may still use the case as non-authoritative review material,
but must not claim that development was driven by an eligible governed case.

FAIL and BLOCKED results hand off to defect governance or the named blocker
owner. NOT_RUN and blank results are incomplete verification. Recording a new
result is a separate repository write that requires current authorization and
the project's evidence rules; the managed workflow intentionally does not
provide a result-writing operation.
