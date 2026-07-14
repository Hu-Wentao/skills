# Baseline Design

## Extract Durable Decisions

Build baselines from decisions that must remain true across future implementations. Prefer statements such as:

- which component owns a responsibility;
- who may perform an action;
- which data is immutable or append-only;
- where secrets may and may not flow;
- which compatibility promise clients may rely on;
- which trust boundary applies to a network surface;
- which terminology has product meaning.

Avoid turning the baseline into a snapshot of every table, endpoint, package, or file. Refer to code and tests for current implementation details.

## Investigate Relevant Domains

Select only domains that matter to the project:

- architecture and service boundaries;
- identity, roles, ownership, and permissions;
- data lifecycle, deletion, retention, and historical facts;
- credentials, secrets, encryption, and rotation;
- audit, logging, metrics, traces, and sensitive metadata;
- public, internal, and administrative network exposure;
- billing, pricing, balances, settlement, and financial history;
- external integrations and failure boundaries;
- UI state ownership and sensitive client caches;
- compatibility, migrations, and deprecation.

Ask project-specific questions. Never import another project's answers as defaults.

## Write Effective Rules

For each rule, make clear:

1. scope and actors;
2. required behavior;
3. prohibited behavior;
4. compatibility or migration boundary;
5. authoritative implementation or test entry when useful.

Use normative language only for accepted current constraints. Label examples as examples so they do not become accidental requirements.

## Separate Baseline from Plan

Place a statement in a baseline only when it is already effective. If implementation is partial:

- describe the exact current subset in the baseline only if that subset is durable;
- keep the remaining target and transition in a plan;
- link both sources without blending their authority.

Keep rollout phases, one-time migrations, temporary flags, unresolved alternatives, task lists, and delivery sequencing in plans.

## Review for Risk

Flag baseline content that:

- contradicts code without explaining whether code or docs are stale;
- exposes secrets or copies live credentials;
- depends on an archived design;
- states a future target as current fact;
- specifies replaceable implementation details without a durable reason;
- duplicates another baseline with subtly different wording;
- lacks a clear scope or owner;
- changes a product guarantee without a linked requirement decision.
