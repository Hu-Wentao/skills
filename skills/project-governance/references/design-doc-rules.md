# Project Design Documentation Rules

Use these details when creating, simplifying, or maintaining implementation-ready architecture docs.

## Contents

- Review Levels
- Document Shape
- Writing Rules
- Boundary Design Pattern
- Versioning And Compatibility Rules
- Implementation Prompt
- Consistency Checks

## Review Levels

Use explicit review levels when a design mixes user decisions and AI-derived details.

Recommended scale:

```text
L0: AI-designed, not human-reviewed
L3: AI-designed, internally reviewed against project constraints
L6: Agent-derived or user-accepted
L9: Human-specified
```

Rules:

- Mark user-authored or specially requested constraints as `L9`.
- Mark AI proposals that the user merely accepts with "agree", "ok", or equivalent as `L6`.
- Mark internally checked AI design as `L3` only when the agent has actually reconciled it against project constraints.
- Mark unreviewed AI implementation details as `L0`.
- Add a default level near the top of each document.
- When later implementing code, annotate important modules or boundaries with the same level, e.g. `// [L9] Control APIs are intended for private-network access only.`

## Document Shape

Prefer this compact set unless the user asks for more:

```text
README.md              # scope, key decisions, module map, doc index
review-levels.md       # review/confidence level definitions
modules.md             # app/package responsibilities and boundaries
storage.md             # persistence ownership and schema
strategy-or-domain.md  # domain-specific algorithms/rules, if relevant
ops.md                 # auth, config, ports, deployment, jobs, testing
implementation-prompt.md
```

Do not create one document per minor topic by default. Consolidate when separate files create repeated explanations.

## Writing Rules

- Prefer bullets and short tables over paragraphs.
- Keep reasons to one sentence unless the decision is risky or counterintuitive.
- Delete naming essays. Write the chosen name and, at most, one reason.
- Avoid repeating the same boundary in every doc. Put it in one canonical place and link or reference it.
- If a document grows because of examples, keep only the minimum example needed to implement.
- If a user says "too verbose", reduce document count and remove explanations before removing decisions.

## Boundary Design Pattern

When separating modules, capture four things:

```text
owner        # who owns the state/resource
executor     # who performs long-running or side-effectful work
API boundary # how others interact with the owner/executor
anti-boundary # what must not bypass the owner
```

Example:

```text
data-srv = market data owner / database authority
worker   = async execution engine / artifact owner
worker may fetch data but must persist market data through data-srv ingest API
UI must read job state through worker API, not worker SQLite
```

## Versioning And Compatibility Rules

When documenting project versioning:

- Use SemVer in `MAJOR.MINOR.PATCH` form for every independently versioned first-party project and first-party submodule. Do not apply this project's release policy to third-party dependency versions.
- Treat APIs, CLIs, configuration, persistent payloads, stored-data semantics, and database schemas as public compatibility surfaces.
- Use `0.0.1` as the initial project version and treat major version `0` as unstable:
  - Use `PATCH` for backward-compatible fixes.
  - An incompatible `0.x` change may use a `MINOR` bump, but explicitly document the breaking change, migration, and rollback path.
- At or after `1.0.0`, apply the following rules:
  - Use `PATCH` only for backward-compatible fixes.
  - Use `MINOR` only for backward-compatible functionality, additive schema evolution, and deprecation.
  - Use `MAJOR` for incompatible API, configuration, behavior, data-semantics, or schema changes.
  - Treat every `PATCH` or `MINOR` change as compatible with supported earlier versions in the same major version unless the user explicitly authorizes incompatibility before implementation. An authorized incompatible change must use a `MAJOR` bump, never `PATCH` or `MINOR`.
  - Introduce deprecation in a `MINOR` release and remove the deprecated surface only in a later `MAJOR` release.
- Limit the default compatibility promise to versions within the same major version. Declare any broader promise separately.

For database schema evolution:

- Require new code to open and losslessly upgrade databases created by supported earlier versions in the same major version.
- Prefer additive schema changes and use an explicit schema version with idempotent migrations.
- Do not silently discard data, reinterpret existing values, or change persisted ownership.
- Treat primary-key changes, field or table removal or rename, stored-value semantic changes, table split or merge, and persistence-ownership changes as incompatible by default.
- Require explicit user authorization and a `MAJOR` bump for an incompatible schema change at or after `1.0.0`.
- Provide migration verification, a backup step, and failure recovery or rollback instructions.
- Interpret database backward compatibility as new code opening and upgrading an old database. Do not promise that old code can open the upgraded database or that mixed-version rolling operation is supported unless separately declared and verified.

After every change, list breaking changes and compatibility/configuration decisions explicitly, including when there are none.

## Implementation Prompt

When the design is ready, create `implementation-prompt.md` containing:

- Required docs to read first.
- Review-level rules.
- Directory layout.
- Project scaffolding and script rules.
- Versioning and compatibility rules.
- Non-negotiable boundaries.
- Storage/config/deployment constraints.
- Minimal APIs.
- Safety rules.
- Testing requirements.
- Implementation order.
- Explicit "do not do" list.

The prompt should be directly usable by another AI agent without requiring the original conversation.

## Consistency Checks

Useful commands:

```bash
rg -n "old-name|old-port|old-db|secrets.json|TODO" docs/
rg -n "\\[L0\\]|\\[L3\\]|\\[L6\\]|\\[L9\\]" docs/
wc -l docs/**/*.md
```

Before finishing:

- Verify links point only to existing docs.
- Search for stale names, stale ports, stale database filenames, and old auth/config terms.
- Confirm every document has a default review level or per-item levels.
- Summarize breaking changes and compatibility/configuration decisions separately.
