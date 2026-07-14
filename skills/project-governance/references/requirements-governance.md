# Requirements Governance

## Model a Requirement

Create a requirement only for a durable user outcome or product constraint. Include:

- stable unique id;
- concise product-language title;
- status;
- product-owned priority when applicable;
- actor and goal;
- durable constraints;
- authoritative sources;
- observable acceptance rules.

Keep replaceable mechanisms, refactors, library choices, migration steps, file paths, and detailed test procedures outside the requirement.

## Preserve Identity

- Never reuse a published id.
- Preserve an id when wording changes but the durable outcome does not.
- Create a new id when actor, outcome, permission, economic meaning, data guarantee, or acceptance semantics materially change.
- Keep deprecated ids with a replacement or explicit reason.
- Check every downstream reference after a split, merge, replacement, or deprecation.

Use a project-owned prefix convention. Do not impose a universal role taxonomy. A heading such as `### REQ-USER-001 Export account data` is easy for humans and structural tools to identify.

## Distinguish Status

Use project-defined statuses. When no convention exists, prefer:

- `Planned`: acceptance is not fully implemented and evidenced;
- `Active`: current implementation and appropriate evidence satisfy the accepted semantics;
- `Deprecated`: the outcome no longer applies, with a replacement or reason.

Partial code or a passing E2E alone does not make a requirement Active. Review baseline alignment, negative constraints, compatibility, and the relevant evidence set.

Treat priority as a product decision. Do not infer Must, Should, or Could from implementation cost, test coverage, age, or developer preference.

## Apply a Change

1. Locate the requirement and every reference.
2. State whether the change is clarification, narrowing, extension, replacement, split, merge, status change, or priority change.
3. Identify affected baselines and plans.
4. Inspect implementation and acceptance evidence.
5. Make the smallest change that keeps identity and product language stable.
6. Update traceability without copying detailed test scripts into the requirement.
7. Validate uniqueness and references.

Request a product decision when multiple interpretations remain plausible or the proposed edit changes product semantics.

## Review Quality

Flag requirements that:

- describe only an implementation mechanism;
- contain no observable acceptance;
- combine unrelated actors or outcomes;
- repeat a baseline without a user outcome;
- claim Active without sufficient implementation evidence;
- encode transient file names, timestamps, or test runs;
- cite missing or archived sources as current authority;
- use an id whose historical meaning differs from the current text.
