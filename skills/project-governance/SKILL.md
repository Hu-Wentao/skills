---
name: project-governance
description: Establish, review, and maintain project governance through durable requirements, current baselines, future plans, archived decisions, verification traceability, and project-specific operational skills. Use when bootstrapping or reorganizing project documentation; adding, changing, activating, deprecating, or auditing REQ-* requirements; reconciling docs with code and tests; promoting completed plans into baselines; archiving superseded designs; reviewing acceptance coverage; or deciding whether a repeated, specialized, or high-risk workflow should become a project-level skill.
---

# Project Governance

## Establish Context

1. Read every applicable repository instruction file before inspecting or changing the project.
2. Check the worktree state and obey the project's dirty-worktree and approval rules.
3. Discover existing documentation, requirements, plans, tests, operational procedures, and project-level skills. Prefer `rg --files` and targeted reads.
4. Identify the project's current terminology and source-of-truth hierarchy. Preserve them unless the user approves a migration.
5. Separate reusable governance method from project-specific product facts. Never import another project's business decisions as defaults.

For a read-only review, inspect and report without editing. For a change, explain the intended scope or implementation plan before editing when repository instructions require it.

## Classify Each Fact

Assign every material statement to exactly one primary authority layer:

- **Requirement**: durable user outcome or product constraint, with stable identity and observable acceptance.
- **Baseline**: current, already-effective rule that constrains future implementation or review.
- **Plan**: target design or transition that is not fully current fact.
- **Code and test fact**: current schema, API shape, file location, algorithm, or runtime behavior.
- **Archive**: historical context that no longer governs new work.
- **Operational workflow**: repeatable execution knowledge, possibly suitable for a project-level skill.

Do not duplicate the same authority across layers. Link to the authoritative source instead. Read [document-lifecycle.md](references/document-lifecycle.md) when creating, reorganizing, promoting, or archiving documents.

## Select the Workflow

### Bootstrap or Reorganize Governance

1. Inventory current sources before proposing a structure.
2. Infer the smallest useful governance system from project risk and complexity; do not create empty categories for symmetry.
3. Define source authority, document lifecycle, stable requirement identity, and verification ownership.
4. Present a migration plan before broad restructuring unless the user explicitly requested direct implementation.
5. Preserve valuable history and links. Avoid wholesale rewrites when incremental classification is sufficient.

Read [baseline-design.md](references/baseline-design.md) and [requirements-governance.md](references/requirements-governance.md).

### Govern a Requirement

1. Locate the affected stable ids and all references.
2. Distinguish clarification from a semantic change. Preserve the id only when the durable outcome remains the same.
3. Update requirement, linked baseline, implementation evidence, and verification ownership consistently.
4. Do not infer status or priority solely from test results, implementation effort, or document age.
5. Report unresolved product decisions rather than silently selecting an interpretation.

Read [requirements-governance.md](references/requirements-governance.md) and [verification-traceability.md](references/verification-traceability.md).

### Govern a Baseline or Plan

1. Verify whether the statement describes current behavior or a future target.
2. Keep durable constraints in baselines; keep implementation phases, temporary migrations, and unresolved target decisions in plans.
3. When a plan completes, merge only lasting rules into the baseline, verify implementation evidence, and archive the superseded plan.
4. Do not treat partial implementation as a current baseline unless the exact effective subset is stated.

Read [document-lifecycle.md](references/document-lifecycle.md) and [baseline-design.md](references/baseline-design.md).

### Review Traceability

1. Map each in-scope requirement to the smallest appropriate verification owner.
2. Use cross-service E2E for user-visible integration acceptance, focused tests for detailed invariants, browser tests for UI-only behavior, and operational checks for deployment or runtime controls.
3. Treat passing evidence as one input to status review, not automatic proof that a requirement is Active.
4. Report missing, excessive, duplicated, or misplaced coverage.

Read [verification-traceability.md](references/verification-traceability.md).

### Extract or Review a Project Skill

1. Confirm that the workflow is repeated, specialized, high-risk, or expensive to rediscover.
2. Keep universal governance here and project-specific commands, topology, terminology, and safety boundaries in the project skill.
3. Prefer a concise procedural `SKILL.md`; move detailed knowledge to references and deterministic operations to tested scripts.
4. Use the system `skill-creator` skill when creating or materially revising the project skill.
5. Do not turn one-time plans, ordinary coding conventions, or unstable product proposals into skills.

Read [project-skill-design.md](references/project-skill-design.md).

## Resolve Conflicts

When requirements, baselines, plans, code, or tests disagree:

1. State the conflicting claims and cite their sources.
2. Identify the authority layer of each claim.
3. Determine whether the mismatch is stale documentation, incomplete implementation, insufficient evidence, or an unresolved product decision.
4. Repair mechanical drift only when semantics are unambiguous and editing is authorized.
5. Stop and request a product decision when resolving the conflict would change user outcomes, permissions, data guarantees, compatibility, priority, or acceptance semantics.

Never make all sources appear consistent by silently rewriting one layer to match another.

## Validate Deterministic Structure

Run the bundled validator when the project uses Markdown governance documents:

```bash
node <skill-directory>/scripts/validate-governance.mjs --root <project-root>
```

Use `--docs <relative-path>` when governance documents are not under `docs/`. Treat script errors as structural defects and warnings as review prompts. The validator must not decide product semantics, priority, or completion status.

Also run project-specific documentation, test, and repository checks appropriate to the change, including a whitespace check when Git is available.

## Deliver

Report:

- authority layers and files created or changed;
- requirement ids and semantic or status decisions;
- verification ownership and remaining gaps;
- conflicts that still require product decisions;
- project skills created, changed, or recommended;
- structural validation and relevant project checks;
- breaking changes and compatibility provisions, explicitly stating when there are none.

Do not release, deploy, publish, migrate live state, or perform other external mutations unless the user explicitly authorizes that action in the current request.
