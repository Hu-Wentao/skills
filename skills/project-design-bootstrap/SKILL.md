---
name: project-design-bootstrap
description: Bootstrap a new software project from product/system discussions or an existing codebase. Use when Codex needs to extract project intent, design implementation-ready architecture docs, choose package/runtime conventions, create project scripts, define Docker/compose build patterns, or prepare a concise implementation prompt for a new project.
---

# Project Design Bootstrap

Turn project intent into a maintainable starting point: concise design docs, clear module boundaries, operational conventions, and implementation-ready scaffolding rules.

## Core Workflow

1. Capture product and system decisions, not transcript.
2. Separate confirmed constraints from inferred design.
3. Define module boundaries, data ownership, runtime surfaces, and package/tooling conventions.
4. Keep docs and scaffolding rules short enough to maintain.
5. End with `implementation-prompt.md` when the project is stable enough to build.

## Reference Routing

Read `references/design-doc-rules.md` when creating or revising architecture docs, especially for:

- Review/confidence levels.
- Recommended document structure.
- Module boundary patterns.
- SemVer and compatibility rules.
- Final consistency checks.

Read `references/project-scaffolding.md` when choosing or documenting:

- Package managers and runtime managers.
- Project script naming.
- Dockerfile and docker-compose patterns.
- Node/pnpm BuildKit dependency caching.

Read `references/legacy-extraction.md` only when the task involves an existing or old project that should inform the new project.

## Operating Rules

- Put the conclusion first.
- Ask for confirmation only when a decision changes implementation cost, deployability, security, or data ownership.
- If the user corrects a term, update all references immediately.
- If a new constraint supersedes earlier docs, search for stale terms and remove them.
- Keep legacy behavior separate from new-project decisions; label what is inherited, replaced, or intentionally dropped.
- Commit only the relevant files when working in a repo with unrelated dirty files.
- Summarize breaking changes and compatibility/configuration decisions separately before finishing.
