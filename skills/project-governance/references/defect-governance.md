# Defect Governance

Use this workflow for one defect diagnosis, an implementation-ready repair plan, or a repair-history review. Keep diagnosis read-only unless the user explicitly authorizes implementation.

## Select the Task

- For `defect-diagnosis`, establish the narrowest defensible diagnosis, detect recurrence, analyze test escape for product defects, and design the smallest recurrence-ending repair when requested.
- For `defect-history-review`, inspect the requested commit, release, or time range; group fixes by failure mechanism and repair shape; and audit the highest-signal recurring families. Treat frequent change as a trigger for investigation, not proof of an architectural defect.

## Establish Context and Evidence

1. Read applicable repository instructions and current requirements, baselines, plans, and project profile instructions.
2. Check worktree and version state before any potential edit. Preserve unrelated work and obey repository approval, commit, release, and deployment rules.
3. Define observed versus expected behavior, affected scope, environment, version or commit, and earliest known occurrence. Do not convert a symptom into a root-cause claim.
4. Reproduce safely when proportionate. Otherwise correlate identifiers, timestamps, logs, persisted state, tests, and execution paths. Stop at a verified evidence gap instead of searching unrelated systems.
5. Build an evidence chain from the entry point to the first incorrect state or decision. Separate facts, hypotheses, and user-provided assumptions; test competing hypotheses; and report remaining uncertainty.
6. Classify the result as product defect, expected configuration or policy result, external dependency failure, invalid or damaged data, infrastructure or test failure, or insufficient observability.
7. Claim a product root cause only when evidence explains both the observed behavior and why the relevant code path produced it.

## Calibrate Repair and Verification

Classify the repair by the highest applicable impact and risk tier before
selecting history depth, evidence collection, documentation, or tests:

| Tier | Repair scope | Minimum verification support |
| --- | --- | --- |
| `L1` local presentation | Copy, style, formatting, or one field binding without new business logic or a runtime contract change | Relevant formatting or static check plus the nearest component, snapshot, or widget regression when behavior can regress |
| `L2` module behavior | Mapping, date generation, dictionary display, validation, or local state inside one owned module | `L1` support plus focused unit, module, service, view-model, or widget tests that own the changed invariant |
| `L3` boundary or contract | Runtime API, DTO, BFF semantics, persistence, navigation, generated interface, or cross-module behavior | `L2` support plus the affected contract or generation check and the narrowest related integration test |
| `L4` high risk | Authentication, authorization, money, destructive data handling, migration, release or deployment control, or platform resource safety | `L3` support plus the key E2E, platform, migration rehearsal, or operational check required by the specific risk |

Choose the tier from user-visible impact, the boundary crossed, compatibility,
data, security, and operational risk. Do not choose it from line count, file
count, code generation, or the presence of a governed document. Correcting only
a description or example in a contract document does not create an `L3`
runtime contract change; validate that document in addition to the actual code
tier.

Start with the smallest deterministic check that owns the invariant. Add a
higher layer only when a shared consumer or runtime boundary is affected, a
generated artifact participates in the behavior, a focused check exposes a
broader regression, recurrence is suspected or confirmed, or the resolved
project contract explicitly requires that check for the affected surface. Do
not run a full suite, E2E, every-platform test, or create a standalone defect
document by default for `L1` or `L2` work. If an unrelated check fails, report
it separately and do not expand the repair unless evidence connects it to the
change.

## Detect Recurrence

Treat repository history as diagnostic evidence and scale the search to the
selected tier. For an apparently first-occurrence `L1` or `L2` repair, start
with the affected file or symbol and direct issue or commit matches. Expand to
repository-wide, release, or architectural history for `L3` or `L4`, a
recurrence signal, responsibility drift, or an unresolved root cause.

1. Define a failure-family signature from the decision point or symbol, error mechanism, external trigger, and repair shape. Do not distinguish incidents only by the newest parameter, enum member, input value, or message.
2. Inspect relevant file and symbol history, blame context, introducing commits, later migrations, archived plans, earlier fixes, and regression tests. Search especially when a proposed repair adds another allowlist or enum member, mapping, branch, retry, fallback, or compatibility exception.
3. Classify recurrence as `first`, `suspected`, or `confirmed`. Mark it `confirmed` when an earlier fix addressed the same decision mechanism or used the same repair shape, even when the concrete symptom differed.
4. For suspected or confirmed recurrence, identify both the proximate cause of this occurrence and the systemic cause that keeps generating the family.

## Audit Module Ownership

Before preserving the responsible module or decision:

1. Identify the current requirement or baseline authorizing the decision.
2. Identify every production consumer of its output.
3. Determine whether the maintained fact belongs to this component, another component, or an external dependency.
4. Inspect whether a migration transferred responsibility while leaving policy code behind.
5. State which current invariant would break if the module or decision were removed.
6. Test the repair against a hypothetical next unseen input from the same family.

If the next input would require another local patch, the repair has not removed the recurrence mechanism unless the project explicitly owns the enforced invariant and has an authoritative maintenance source. Do not close a confirmed recurrence only by adding another list member, mapping, branch, retry, fallback, or exception.

## Analyze Test Escape

Perform this section whenever a new product defect is established, but bound it
to the selected tier and the layer that owns the invariant.

1. Inspect relevant unit and integration tests, fixtures, mocks, and actual assertions. Do not infer coverage from filenames or a green run.
2. Inspect E2E or cross-service scenarios only for `L3` or `L4`, when that layer owns the invariant, or when focused evidence indicates a cross-boundary escape.
3. Explain escape only for layers actually in scope: absent scenario, unexecuted branch, unrealistic mock, incomplete state combination, weak assertion, swallowed failure, environment divergence, or missing traceability.
4. Name the smallest test layer that should own the invariant. Prefer a class-level or property-style regression over a test recognizing only the latest concrete example.
5. State why broader layers were not required when that choice would otherwise be ambiguous; do not manufacture an E2E gap for a focused invariant.

## Design the Repair

1. Define corrected externally observable behavior and the invariant that must hold afterward.
2. Propose the smallest design that fixes the supported root cause. Do not add unrelated cleanup, refactors, instrumentation, fallback behavior, or auxiliary features.
3. For confirmed recurrence, compare a leaf patch with responsibility correction, delegation, or removal. Reject the leaf patch when it leaves the same failure generator active.
4. Identify exact components, data paths, interfaces, tests, compatibility effects, security boundaries, and validation steps.
5. Surface unresolved decisions that materially change product behavior before implementation.

## Maintain Repair History

Before editing an established product defect, identify the project-approved repair-history owner and include it in the repair scope. A commit body, issue, pull request, or repository defect ledger is sufficient only when project instructions approve that owner. For a first-occurrence `L1` or `L2` repair, prefer an existing commit, pull request, or task record; do not create a standalone governed defect document unless project instructions explicitly require one. If the project requires such a document, treat it as a completion gate; a commit body cannot replace it.

For a first-occurrence `L1` or `L2` repair, keep the record to observed versus
expected behavior, the repaired invariant, affected scope, verification, and
compatibility. For `L3`, `L4`, suspected or confirmed recurrence, or a
project-required defect ledger, produce a compact record with:

- failure family and decision point;
- observed behavior and affected scope;
- proximate and systemic cause;
- recurrence classification and prior occurrences;
- repair shape and ownership verdict;
- related requirements, commits, tests, and evidence;
- whether recurrence is eliminated and how the next unseen case behaves.

Persist the record only through a project-approved issue, pull request, commit, or defect ledger. Do not create a tracking system or mutate the repository during diagnosis-only work. For an implemented repair, make the durable change record and regression-test name identify the failure family rather than only the concrete example.

When a project uses a repository defect ledger, prefer one compact file per defect over one ever-growing shared file. Use a stable collision-resistant id such as `DEF-YYYYMMDD-slug`, reference that id from the repair commit, and keep the record with the code and regression test in the same change when practical. Record current durable invariants separately in the appropriate baseline; the ledger is repair history and does not govern current behavior. Do not change requirement status merely because a defect repair passes.

## Review Repair History

1. Freeze the review range and enumerate defect-related changes from the project-configured history sources.
2. Cluster by decision mechanism, external trigger, code ownership, and repair shape rather than commit wording alone.
3. Identify repeated leaf patches, fast-growing compatibility tables, repeated changes to the same validator or error path, and migration-era modules that remain active.
4. Audit the highest-signal clusters for systemic cause and responsibility drift.
5. Recommend a governance or architectural correction only when evidence supports it; otherwise report the hotspot and next evidence needed.
6. Record reviewed range, families, confidence, open recurrence, verification gaps, and the next review boundary.

## Deliver

Lead with the diagnosis or highest-signal recurring family. Report the selected
tier, evidence, confidence, applicable cause and recurrence findings, repair
plan when requested, verification at that tier, escalation triggers, breaking
changes, compatibility, and unresolved blockers. Include test escape analysis
only to the depth actually inspected; do not make a simple repair report carry
fields that are immaterial at its tier.
