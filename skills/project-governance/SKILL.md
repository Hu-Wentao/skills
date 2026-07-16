---
name: project-governance
description: "Establish, review, and maintain project governance across document governance, Git version governance, and project-skill governance. Use when creating, writing, reviewing, updating, reorganizing, completing, or archiving governed requirements, baselines, formal project plans, or verification traceability; governing branches, commits, worktrees, releases, version tags, deployment refs, or hotfix lineage; reconciling governance sources with code and tests; or deciding whether a repeated specialized workflow should become a project-level skill. Do not use solely for a transient conversational implementation outline that will not become a project authority or tracked artifact."
---

# Project Governance

## Establish Context

1. Read every applicable repository instruction file before inspecting or changing the project.
2. Check the worktree, branch, worktree topology, and upstream state. Obey the project's dirty-worktree, approval, commit, release, and deployment rules.
3. Discover existing documentation, requirements, plans, tests, Git conventions, release procedures, and project-level skills. Prefer `rg --files` and targeted reads.
4. Identify the current terminology and sources of truth. Preserve them unless the user approves a migration.
5. Separate reusable governance method from project-specific product facts and operational commands.

For a read-only review, inspect and report without editing. For a change, present the intended scope or implementation plan when repository instructions require it. Never treat release, deployment, publishing, or live migration authority from an earlier turn as current authorization.

Treat a plan as governed when it is written into the repository, referenced as an implementation authority, linked to requirements or baselines, assigned lifecycle status, or expected to be completed and archived. Do not treat a temporary pre-implementation explanation as a governed plan.

## Select a Governance Domain

Treat these as peer capabilities rather than placing Git or skill governance under documentation:

- **Document governance**: requirements, baselines, plans, archives, and verification traceability.
- **Git version governance**: change isolation, commit lineage, integration branches, release commits, immutable tags, fixed deployment refs, and hotfix ancestry.
- **Project-skill governance**: extraction and maintenance of repeated, specialized, or high-risk operational knowledge.

Use every applicable domain when a task crosses boundaries. For example, a release-policy change may require a Git invariant, a baseline update, verification evidence, and a project release skill.

## Document Governance

### Classify Each Fact

Assign every material statement to exactly one primary authority layer:

- **Requirement**: durable user outcome or product constraint, with stable identity and observable acceptance.
- **Baseline**: current, already-effective rule that constrains future implementation or review.
- **Plan**: target design or transition that is not fully current fact.
- **Code and test fact**: current schema, API shape, file location, algorithm, or runtime behavior.
- **Archive**: historical context that no longer governs new work.
- **Operational workflow**: repeatable execution knowledge, possibly suitable for a project-level skill.

Do not duplicate authority across layers. Link to the authoritative source. Read [document-lifecycle.md](references/document-lifecycle.md) when creating, reorganizing, promoting, or archiving documents.

### Bootstrap or Reorganize Documents

1. Inventory current sources before proposing a structure.
2. Infer the smallest useful governance system from project risk and complexity; do not create empty categories for symmetry.
3. Define source authority, document lifecycle, stable requirement identity, and verification ownership.
4. Present a migration plan before broad restructuring unless the user explicitly requested direct implementation.
5. Preserve valuable history and links. Prefer incremental classification over wholesale rewrites.

Read [baseline-design.md](references/baseline-design.md) and [requirements-governance.md](references/requirements-governance.md).

### Govern Requirements, Baselines, and Plans

1. Locate affected stable ids and references.
2. Distinguish clarification from semantic change. Preserve an id only while its durable outcome remains the same.
3. Keep durable current constraints in baselines and not-yet-current targets or transitions in plans.
4. When a plan completes, verify implementation evidence, merge only lasting rules into baselines, review requirement status separately, and archive superseded planning material.
5. Do not infer status or priority solely from test results, implementation effort, or document age.

Read [requirements-governance.md](references/requirements-governance.md), [document-lifecycle.md](references/document-lifecycle.md), and [baseline-design.md](references/baseline-design.md).

### Govern Verification Traceability

1. Map each in-scope requirement to the smallest effective verification owner.
2. Use cross-service E2E for user-visible integration, focused tests for detailed invariants, UI tests for UI behavior, and operational checks for deployment or runtime controls.
3. Treat passing evidence as one input to status review, not automatic proof that a requirement is Active.
4. Report missing, excessive, duplicated, or misplaced coverage.

Read [verification-traceability.md](references/verification-traceability.md).

## Git Version Governance

Govern Git history as a durable project record, not merely a command sequence. Preserve clear ancestry from accepted changes through releases and hotfixes.

For a normal release:

1. Freeze the exact committed source on the primary integration branch, normally `main`.
2. Require the checked-out integration worktree to be clean before planning any operation that will advance it.
3. Use an isolated worktree on a temporary release branch, such as `release/v<version>`, for version edits, checks, builds, and the release commit.
4. Revalidate that the integration branch is clean and still at the frozen source commit after checks pass.
5. Fast-forward the integration branch to the release commit, or use the project's explicitly approved merge policy. Stop if ancestry diverged.
6. Create the annotated `v<version>` tag only after the release commit is in integration-branch history, and require the tag and integration branch to resolve to the same commit.
7. Pin deployment and every retry to the recorded tag and full commit id. Never re-resolve a moving branch or infer a different release commit without current user approval.
8. Create maintenance branches from immutable release tags, for example `git switch -c hotfix/v0.31.2 v0.31.2`; do not replace release tags with long-lived version branches merely to enable fixes.

Never leave a release commit reachable only through a tag created on detached `HEAD`. Never move a checked-out dirty branch by low-level ref mutation. Never move or delete a published release tag without explicit authorization for that exact tag operation.

Read [git-version-governance.md](references/git-version-governance.md) before changing commit, branch, tag, release, deployment-ref, retry, or hotfix policy.

## Project-Skill Governance

1. Confirm that the workflow is repeated, specialized, high-risk, or expensive to rediscover.
2. Keep universal governance here and project-specific commands, topology, terminology, and safety boundaries in the project skill.
3. Prefer a concise procedural `SKILL.md`; move detailed knowledge to references and deterministic operations to tested scripts.
4. Use `skillcraft` when creating or materially revising a skill.
5. Do not turn one-time plans, ordinary coding conventions, or unstable product proposals into skills.

Read [project-skill-design.md](references/project-skill-design.md).

## Resolve Conflicts

When documents, Git history, code, tests, or skills disagree:

1. State the conflicting claims and cite their sources.
2. Identify the authority domain and layer of each claim.
3. Determine whether the mismatch is stale governance, invalid ancestry, incomplete implementation, insufficient evidence, or an unresolved product decision.
4. Repair mechanical drift only when semantics are unambiguous and editing is authorized.
5. Stop for a decision when resolution would change user outcomes, permissions, data guarantees, compatibility, priority, accepted Git history, or release identity.

Never manufacture consistency by silently rewriting a source, moving a tag, or changing the deployment commit.

## Validate

For Markdown governance documents, run:

```bash
node <skill-directory>/scripts/validate-governance.mjs --root <project-root>
```

Use `--docs <relative-path>` when governance documents are not under `docs/`. Treat errors as structural defects and warnings as review prompts; the validator does not decide product semantics, priority, or completion status.

For Git governance, inspect the relevant refs and ancestry directly. Verify staged scope before committing, confirm the release tag type and target, prove the release commit is reachable from the integration branch, and compare the exact deployment commit with the recorded release commit.

Also run project-specific documentation, test, repository, and whitespace checks appropriate to the change.

## Deliver

Report:

- governance domains and files changed;
- requirement ids and semantic or status decisions;
- branch, commit, tag, deployment-ref, and hotfix-lineage decisions;
- verification ownership and remaining gaps;
- conflicts still requiring a decision;
- project skills created, changed, or recommended;
- structural validation and relevant project checks;
- breaking changes and compatibility provisions, explicitly stating when there are none.

Do not release, deploy, publish, migrate live state, push, rewrite history, or move tags unless the user explicitly authorizes that action in the current request.
