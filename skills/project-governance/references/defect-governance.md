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

## Detect Recurrence

Treat repository history as diagnostic evidence, not optional background.

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

Perform this section whenever a new product defect is established.

1. Inspect relevant unit and integration tests, fixtures, mocks, and actual assertions. Do not infer coverage from filenames or a green run.
2. Inspect the applicable E2E or cross-service scenario, harness, seeded state, and acceptance assertions.
3. Explain focused and E2E escape separately: absent scenario, unexecuted branch, unrealistic mock, incomplete state combination, weak assertion, swallowed failure, environment divergence, or missing traceability.
4. Name the smallest test layer that should own the invariant. Prefer a class-level or property-style regression over a test recognizing only the latest concrete example.
5. When E2E is not the correct owner, explain why and identify the focused, UI, browser, or operational layer that is.

## Design the Repair

1. Define corrected externally observable behavior and the invariant that must hold afterward.
2. Propose the smallest design that fixes the supported root cause. Do not add unrelated cleanup, refactors, instrumentation, fallback behavior, or auxiliary features.
3. For confirmed recurrence, compare a leaf patch with responsibility correction, delegation, or removal. Reject the leaf patch when it leaves the same failure generator active.
4. Identify exact components, data paths, interfaces, tests, compatibility effects, security boundaries, and validation steps.
5. Surface unresolved decisions that materially change product behavior before implementation.

## Maintain Repair History

For every established product defect, produce a compact record with:

- failure family and decision point;
- observed behavior and affected scope;
- proximate and systemic cause;
- recurrence classification and prior occurrences;
- repair shape and ownership verdict;
- related requirements, commits, tests, and evidence;
- whether recurrence is eliminated and how the next unseen case behaves.

Persist the record only through a project-approved issue, pull request, commit, or defect ledger. Do not create a tracking system or mutate the repository during diagnosis-only work. For an implemented repair, make the durable change record and regression-test name identify the failure family rather than only the concrete example.

## Review Repair History

1. Freeze the review range and enumerate defect-related changes from the project-configured history sources.
2. Cluster by decision mechanism, external trigger, code ownership, and repair shape rather than commit wording alone.
3. Identify repeated leaf patches, fast-growing compatibility tables, repeated changes to the same validator or error path, and migration-era modules that remain active.
4. Audit the highest-signal clusters for systemic cause and responsibility drift.
5. Recommend a governance or architectural correction only when evidence supports it; otherwise report the hotspot and next evidence needed.
6. Record reviewed range, families, confidence, open recurrence, verification gaps, and the next review boundary.

## Deliver

Lead with the diagnosis or highest-signal recurring family. Report evidence, confidence, classification, recurrence, proximate and systemic cause, ownership verdict, repair plan when requested, history record, next-unseen-case result, validation, breaking changes, compatibility, and unresolved blockers. When a new product defect is established, make `Test escape analysis` the final analytical section.
