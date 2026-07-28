---
name: project-governance
description: "Bootstrap, review, and maintain project architecture, governed documents, compatibility, Git lineage, releases and deployments, project skills, runtime ports, defects, and feedback lifecycles. Use for requirements, baselines, plans, verification, branches, commits, worktrees, SemVer, release tags, promotions, fixed-tag retries, hotfixes, PPISS ports, recurring defects, root cause, repair history, feedback rewards, or reconciliation between governance sources and implementation."
---

# Project Governance

## Establish Context

1. Read applicable repository instructions.
2. Inspect the current worktree, branch, upstream, worktree topology, and source authority before changing anything.
3. Keep universal policy in this skill, project facts in repository configuration, deterministic operations in tested scripts, and runtime output in ignored caches.
4. Preserve current terminology and authority unless the user approves a migration.
5. Treat release, deployment, publishing, rollback, live migration, reward, and destructive authority as current-turn permissions only.

For read-only review, inspect and report without editing. For changes, follow the repository's planning, dirty-worktree, approval, commit, and deployment rules.

## Use Deterministic Task Contracts

For a configured workflow, resolve a small JSON task contract:

```bash
uv run python <skill-root>/scripts/resolve.py \
  --cwd <project-root> --task <task> --operation <operation> --format json
```

With `project-governance.config.v3`, consume `state`, `policy_refs`, parameter schemas, mutability, authorization requirements, output schema, exit codes, and allowed next states. Do not read every policy reference by default. Read only the referenced section needed for a semantic decision, conflict, failed precondition, or unsupported operation.

Execute one validated operation through:

```bash
uv run python <skill-root>/scripts/project-governance.py \
  --cwd <project-root> <domain> <operation> [contracted arguments]
```

Use `--authorized` only after the current user authorizes a non-read-only operation. The flag is a mechanical gate, not proof of authorization. Never bypass the runner with a declared command string when a v3 contract exists.

Supported aliases are `defect collect`, `docs audit`, `git snapshot`, `release inspect`, `release plan`, `release run`, and `release retry`. A project contract may expose only a subset.

Legacy v1/v2 profiles remain readable during migration. They return composed instructions and declarative command strings; read their resolved instructions because they do not provide executable contracts.

## Select the Governance Domain

- For project design, architecture, module ownership, scaffolding, or implementation handoff, read [design-doc-rules.md](references/design-doc-rules.md), [project-scaffolding.md](references/project-scaffolding.md), and [legacy-extraction.md](references/legacy-extraction.md) as applicable.
- For SemVer, migrations, compatibility surfaces, release identities, tags, promotions, retries, or hotfix ancestry, read [git-version-governance.md](references/git-version-governance.md) and [release-deployment.md](references/release-deployment.md) only when the task contract cannot decide the required semantic boundary.
- For requirements, baselines, plans, archives, lifecycle, or verification ownership, read [requirements-governance.md](references/requirements-governance.md), [baseline-design.md](references/baseline-design.md), [document-lifecycle.md](references/document-lifecycle.md), and [verification-traceability.md](references/verification-traceability.md) as needed.
- For defects, recurrence, root cause, repair design, history, and test escape, resolve `defect-diagnosis` or `defect-history-review`; read [defect-governance.md](references/defect-governance.md) for semantic judgment.
- For feedback triage, reward approval, repair-to-release handoff, or closure, resolve `defect-feedback-lifecycle`; read [defect-feedback-lifecycle.md](references/defect-feedback-lifecycle.md) at authority transitions.
- For PPISS port allocation, use `project-segments.py` and resolve `port-allocation`; read [port-allocation.md](references/port-allocation.md) for an established-port migration.
- For repeated, specialized, high-risk workflow extraction, read [project-skill-design.md](references/project-skill-design.md). Prefer concise policy, project configuration, and tested scripts.

Treat these domains as peers. Crossing a domain boundary does not transfer authorization.

## Preserve Non-configurable Invariants

- Do not broaden user authorization through configuration or task output.
- Do not expose credentials, authorization headers, request bodies, captures, or provider secrets.
- Do not mutate a published release tag or re-resolve a moving deployment ref.
- Keep release/retry identity fixed to the recorded full commit and immutable tag.
- Do not classify a defect root cause, recurrence, ownership, requirement status, priority, or breaking-change acceptance from a script result alone.
- Do not turn passing checks into automatic proof of product semantics or deployment success.
- Stop for a decision when resolution would change user outcomes, permissions, data guarantees, compatibility, accepted Git history, or release identity.

## Govern Documents

Use `queryable-markdown` for governed Markdown created or materially revised under this skill unless the project explicitly excludes it. Keep each fact in one primary authority layer: Requirement, Baseline, Plan, Code/Test Fact, Archive, or Operational Workflow.

Run the contracted `docs audit` operation when available. Otherwise run:

```bash
node <skill-root>/scripts/validate-governance.mjs --root <project-root>
```

Mechanical validation may find missing contracts, links, identifiers, lifecycle mappings, or verification references. AI still decides semantics, priority, completion, and authority.

## Govern Git, Releases, and Deployment

Use `git snapshot`, `release inspect`, and `release plan` before semantic release decisions. Invoke `release run` or `release retry` only with current explicit authorization and the exact target/ref authorized by the user.

Treat repository release and deployment executors as automation boundaries. Do not reproduce their internal build, migration, health, canary, or smoke steps. Resume only the same yielded process. Never auto-retry, auto-promote, auto-rollback, restore state, migrate live data, or select a different commit.

## Govern Defects

Run `defect collect` before writing ad hoc Git, SQLite, Docker, SSH, or application probes when the project contract supports the evidence scope. Read the returned evidence envelope, then use [defect-governance.md](references/defect-governance.md) to classify recurrence, systemic cause, ownership, repair shape, next-unseen-case behavior, and test escape.

Keep diagnosis read-only unless implementation is explicitly authorized. Persist repair history only through the project-approved owner.

## Validate and Deliver

Run the smallest contracted checks first, then project-specific tests appropriate to the change. Validate every modified skill with Skillcraft and test every added deterministic script.

Report:

- domains and authoritative files changed;
- task contract, fixed identities, evidence, and exit states;
- semantic decisions still made by AI;
- verification performed and remaining gaps;
- breaking changes and compatibility provisions;
- commits, tags, deployment refs, publication state, and unauthorized operations left untouched.

Do not release, deploy, publish, migrate live state, push, rewrite history, or move tags unless explicitly authorized in the current request.
