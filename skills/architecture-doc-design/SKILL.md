---
name: architecture-doc-design
description: Create, simplify, and maintain implementation-ready architecture design documents from iterative technical discussions. Use when Codex needs to turn evolving product/system design conversations into concise docs, preserve user-confirmed decisions, label confidence/review levels, split or consolidate design docs, define module boundaries, produce implementation prompts, or prevent architecture docs from becoming verbose and redundant.
---

# Architecture Doc Design

Convert architecture discussions into concise docs that another engineer or AI agent can implement from.

## Core Workflow

1. Capture decisions, not transcript.
2. Separate confirmed constraints from derived design.
3. Keep docs short enough to maintain.
4. Prefer fewer docs with clear ownership over many narrow docs.
5. End with `implementation-prompt.md` when the design is stable enough to build.

## Reference Routing

Read `references/design-doc-rules.md` when creating or revising architecture docs, especially when you need:

- Review/confidence levels.
- Recommended document structure.
- Module boundary patterns.
- Project script naming rules.
- SemVer and compatibility rules.
- Final consistency checks.

## Operating Rules

- Put the conclusion first.
- Ask for confirmation only when a decision changes implementation cost, deployability, security, or data ownership.
- If the user corrects a term, update all references immediately.
- If a new constraint supersedes earlier docs, search for stale terms and remove them.
- Commit only the relevant docs when working in a repo with unrelated dirty files.
- Summarize breaking changes and compatibility/configuration decisions separately before finishing.
