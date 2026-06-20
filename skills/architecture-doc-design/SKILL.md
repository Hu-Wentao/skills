---
name: architecture-doc-design
description: Create, simplify, and maintain implementation-ready architecture design documents from iterative technical discussions. Use when Codex needs to turn evolving product/system design conversations into concise docs, preserve user-confirmed decisions, label confidence/review levels, split or consolidate design docs, define module boundaries, produce implementation prompts, or prevent architecture docs from becoming verbose and redundant.
---

# Architecture Doc Design

Use this skill to convert architecture discussions into docs that another engineer or AI agent can implement from.

## Core Workflow

1. Capture decisions, not transcript.
2. Separate confirmed constraints from derived design.
3. Keep docs short enough to be maintained.
4. Prefer fewer docs with clear ownership over many narrow docs.
5. End with an implementation prompt when the design is stable enough to build.

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

- Put the conclusion first.
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

## Iteration Guidance

During discussion:

- Ask for confirmation only when a decision changes implementation cost, deployability, security, or data ownership.
- If the user corrects a term, update all references immediately.
- If a new constraint supersedes earlier docs, search for stale terms and remove them.
- Commit only the relevant docs when working in a repo with unrelated dirty files.

Useful consistency checks:

```bash
rg -n "old-name|old-port|old-db|secrets.json|TODO" docs/
rg -n "\\[L0\\]|\\[L3\\]|\\[L6\\]|\\[L9\\]" docs/
wc -l docs/**/*.md
```

## Project Script Rules

When documenting project scripts:

- Place all project scripts under the repository root `scripts/` directory.
- Name development runtime scripts as `dev-<module-name>.sh`.
- Name production runtime scripts and other operational scripts with the `run-` prefix.

## Versioning And Compatibility Rules

When documenting project versioning:

- Use semantic versioning in `MAJOR.MINOR.PATCH` form.
- Use `0.0.1` as the initial project version.
- Treat major version `0` as unreleased.
- For unreleased projects, do not add compatibility configuration by default; replace old configuration with the new configuration.
- Still list all breaking changes and compatibility/configuration decisions after every change.

## Implementation Prompt

When the design is ready, create `implementation-prompt.md` containing:

- Required docs to read first.
- Review-level rules.
- Directory layout.
- Project script rules.
- Versioning and compatibility rules.
- Non-negotiable boundaries.
- Storage/config/deployment constraints.
- Minimal APIs.
- Safety rules.
- Testing requirements.
- Implementation order.
- Explicit "do not do" list.

The prompt should be directly usable by another AI agent without requiring the original conversation.

## Final Check

Before finishing:

- Verify links point only to existing docs.
- Search for stale names, stale ports, stale database filenames, and old auth/config terms.
- Confirm every document has a default review level or per-item levels.
- Summarize break changes and compatibility/config decisions separately.
