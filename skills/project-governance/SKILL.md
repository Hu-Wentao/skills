---
name: project-governance
description: Route governed project work across architecture, requirements, baselines, plans, documents, terminology, dependencies, tests, releases, deployments, defects, ports, resources, and verification. Use for governed implementation or maintenance, defect/release workflows, and concise problem-summary handoffs.
metadata:
  context-budget: router
---

# Project Governance

Route project governance to the smallest applicable contract and reference. Keep project facts in repository configuration, mechanics in tested scripts, and runtime output in ignored caches. Skill authoring and publication belong to `skillcraft`; local branch/worktree lifecycle belongs to `git-worktree`.

## Establish Context

1. Read repository instructions and current baselines before plans or code.
2. Identify the primary authority for each fact: requirement, baseline, plan, code/test, evaluation, archive, or operation.
3. Preserve terminology and append-only facts unless an authorized migration says otherwise.
4. Treat release, deployment, rollback, live mutation, reward, and destructive actions as current-request authority only.
5. Keep `README.md` user-facing; put architecture, lifecycle indexes, operations, contracts, and governed records in dedicated documents.

For `总结问题`, produce only intended outcome, symptoms, confirmed evidence, affected scope, impact, and unresolved questions. Preserve uncertainty and secrets; do not prescribe a fix or perform writes.

## Resolve Contracted Work

For configured workflows, resolve once:

```bash
uv run python <skill-root>/scripts/resolve.py \
  --cwd <project-root> --task <task> --operation <operation> --format json
```

With `project-governance.config.v3`, read the returned state, selected policy references, parameters, mutability, authorization, output schema, exit states, and allowed transitions. Execute only through the validated runner:

```bash
uv run python <skill-root>/scripts/project-governance.py \
  --cwd <project-root> <domain> <operation> [contracted arguments]
```

Use `--authorized` only when current user intent covers that non-read-only operation. Do not improvise a command when a contract is missing. Legacy profiles provide instructions, not executable v3 authority.

## Route by Domain

- Architecture, requirements, baselines, plans, scaffolding, lifecycle, or implementation handoff: [design-doc-rules.md](references/design-doc-rules.md), [requirements-governance.md](references/requirements-governance.md), [baseline-design.md](references/baseline-design.md), [project-scaffolding.md](references/project-scaffolding.md), [document-lifecycle.md](references/document-lifecycle.md), and [verification-traceability.md](references/verification-traceability.md).
- Legacy extraction: [legacy-extraction.md](references/legacy-extraction.md).
- Dependency selection or replacement: [dependency-evaluation.md](references/dependency-evaluation.md).
- Governed Markdown inventory, contracts, and lifecycle maintenance: resolve `document-maintenance` and read [document-maintenance.md](references/document-maintenance.md); for reusable heading-record contracts, read [mdq-profile.md](references/mdq-profile.md).
- Domain concepts, aliases, contexts, and relationships: resolve `domain-knowledge` and read [domain-knowledge.md](references/domain-knowledge.md).
- Test-case catalog development: resolve `test-case-development` and read [test-case-development.md](references/test-case-development.md).
- Defect diagnosis, root cause, recurrence, repair history, or test escape: resolve `defect-diagnosis` or `defect-history-review` and read [defect-governance.md](references/defect-governance.md).
- Feedback triage through closure: resolve `defect-feedback-lifecycle` and read [defect-feedback-lifecycle.md](references/defect-feedback-lifecycle.md).
- CPU, memory, OOM, disk, restart, exit, capacity, or Compose pressure: resolve `resource-diagnosis` and read [resource-diagnostics.md](references/resource-diagnostics.md).
- Host-visible ports: resolve `port-allocation` and read [port-allocation.md](references/port-allocation.md).
- Version identity, published tags, release, deployment, promotion, retry, repair, or hotfix: resolve `release-deployment`; read [git-version-governance.md](references/git-version-governance.md), [release-deployment.md](references/release-deployment.md), and [release-workflow-config.md](references/release-workflow-config.md) only as needed.

## Universal Boundaries

- Configuration cannot broaden user authority or override system/developer rules.
- Never expose credentials, authorization headers, provider secrets, private request bodies, or captures in logs, metrics, traces, audit metadata, or responses.
- Evaluation evidence supports a decision; it does not install a dependency or create a requirement.
- Passing checks are scoped evidence, not automatic semantic acceptance, root cause, deployment success, or lifecycle completion.
- Keep release identity bound to one full commit and immutable tag. Never move a published tag or re-resolve a moving deployment ref.
- Shared ingress and host infrastructure remain separately owned; route them through `host-governance`.
- Stop for a decision when a change alters user-visible outcomes, permissions, data guarantees, compatibility, accepted history, or release identity.

## Govern Records and Delivery

Governed Markdown created or materially revised through this skill must use `queryable-markdown` with a valid persistent mdq contract. When level-2 headings carry versioned structured IDs and the standard governance labels, reference `project-governance/governed-document-v1` instead of duplicating its extraction rules; use a minimal inline contract for other structures. Treat published profile versions as immutable and migrate references only with explicit contract authority. `README.md` is ordinary documentation and must not host persistent mdq metadata. Validate exact records and representative positive and negative queries.

An imperative release-and-deploy request with one named target activates the normal stages of the resolved `release-deployment` contract without a second confirmation. Keep source, target, commit, immutable tag, artifact, transaction, and verification evidence fixed together. Retry only the recorded identity.

Defect diagnosis remains read-only until implementation is requested. Classify repair risk by observable impact and crossed boundaries, then collect only the evidence required by that tier.

## Report

Run the smallest contracted checks first. Report authoritative files changed, contract states, exact evidence, semantic decisions still open, verification gaps, compatibility, and external operations intentionally untouched. Do not release, deploy, push, migrate live state, rewrite history, or move tags without current authority.
