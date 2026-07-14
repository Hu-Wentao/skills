# Document Lifecycle

## Define Authority

Use this default hierarchy only when the project has no stronger existing convention:

1. Product goals and status: stable requirements.
2. Current durable constraints: baselines.
3. Not-yet-current targets: plans.
4. Current implementation details: code and tests.
5. Historical background: archive.

Document this hierarchy in the project. When the project already has another workable hierarchy, preserve it or propose an explicit migration.

## Separate Responsibilities

### Requirements

Store durable user outcomes, product constraints, status, priority when product-owned, sources, and observable acceptance. Exclude detailed implementation steps, file-line references, transient test results, and delivery logs.

### Baselines

Store rules that are currently effective and expected to constrain future implementation or review. Prefer decisions and invariants over schema dumps, endpoint inventories, and file locations. Link to code for replaceable technical details.

### Plans

Store target behavior, current gaps, decisions, implementation phases, compatibility strategy, completion conditions, and unresolved questions. Declare status such as `Planned` or `Partially implemented`. Never present a target as current fact.

### Archive

Store superseded, rejected, or fully delivered design material that remains useful for history. Archived documents do not override requirements, baselines, code, or tests.

## Move Documents by Meaning

Do not archive by age. Archive only when a document no longer constrains future work.

When a plan completes:

1. Verify the implementation and acceptance evidence.
2. Extract durable rules into the relevant baseline.
3. Update requirement status only after a separate status review.
4. Move or mark the implementation plan as archived.
5. Repair inbound links and indexes.

For partial delivery, keep the plan active and state which subset is current. Do not move the whole target into a baseline.

## Handle Conflict

Classify disagreements before editing:

- requirement versus baseline: likely a product decision or stale baseline;
- baseline versus code: possible implementation defect or stale baseline;
- plan versus code: possible partial delivery, not necessarily a conflict;
- requirement versus tests: missing evidence or outdated acceptance;
- archive versus current sources: archive loses authority.

Report ambiguity. Do not manufacture consistency by choosing the most convenient source.

## Keep the System Small

Create only documents that carry durable decisions. Avoid empty directories, duplicate summaries, generated inventories, meeting notes, release logs, and operational runbooks in governance docs unless they directly constrain future product or implementation choices.
