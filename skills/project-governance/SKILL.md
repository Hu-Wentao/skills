---
name: project-governance
description: "Bootstrap, review, and maintain project architecture, governed documents, domain terminology and concept catalogs, Markdown lifecycle, implementation-plan handoffs, dependency evaluations, compatibility, Git lineage, releases, deployments, project skills, ports, defects, resource diagnostics, and feedback lifecycles. Use for plan or specification implementation in a task worktree; domain language, bounded contexts, glossaries, and semantic relationships; document inspection, mdq contracts, stale requirements or plans, baselines, and archives; third-party technology assessment or replacement; verification, branches, commits, worktrees, SemVer, tags, promotions, deployment recovery, fixed-tag retries, repairs, hotfixes, PPISS ports, recurring defects, root cause, host or Compose CPU/memory/OOM/disk incidents, resource pressure, repair history, feedback rewards, or reconciliation between governance sources and implementation."
---

# Project Governance

## Establish Context

1. Read applicable repository instructions.
2. Inspect the current worktree, branch, upstream, worktree topology, and source authority before changing anything.
3. Keep universal policy in this skill, project facts in repository configuration, deterministic operations in tested scripts, and runtime output in ignored caches.
4. Preserve current terminology and authority unless the user approves a migration.
5. Treat release, deployment, publishing, rollback, live migration, reward, and destructive authority as current-turn permissions only.
6. When the user asks to implement a plan, specification, or implementation
   prompt, use `git-worktree` `owner-status` on the current directory before
   editing. Treat an eligible non-main worktree as this conversation's owner
   task even when the worktree existed before the conversation or was created
   outside this turn. After the implementation is fully validated, committed,
   and clean, use `git-worktree` `mark-complete` on the final exact HEAD before
   reporting completion. Never mark partial, blocked, dirty, unvalidated,
   detached, or main-worktree work complete; report the exact blocker instead.

For read-only review, inspect and report without editing. Do not classify a
project-scoped external dependency or technology evaluation as read-only merely
because upstream inspection is read-only: follow
[dependency-evaluation.md](references/dependency-evaluation.md). When the
installed `recall-resources` skill advertises the compatible shared-assessment
capability, persist reusable upstream evidence there and keep only a pinned
`TECH-FIT-*` project-fit record locally. Otherwise persist the complete local
`TECH-EVAL-*` fallback. Do not infer capability from a folder name. Skip
persistence only when the user explicitly forbids writes or no writable project
context exists. For other changes, follow the repository's planning,
dirty-worktree, approval, commit, and deployment rules.

When shared assessment storage is used, treat claim ownership as a completion
gate. Keep upstream and generally reusable claims in the shared assessment;
keep project facts, consequences, integration ownership, and decisions in the
local `TECH-FIT-*` record. Run the claim-partition and final ownership audit in
`dependency-evaluation.md` before handoff. Do not apply this split to the
complete local `TECH-EVAL-*` fallback.

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

Supported release aliases include `release sync-main-plan`, `release sync-main`,
`release inspect`, `release bootstrap-plan`, `release bootstrap`, `release plan`, `release prepare-plan`, `release prepare`,
`release run`, `release promote-plan`, `release promote`, `release retry`, `release repair-prepare-plan`,
`release repair-prepare`, `release repair-plan`, and `release repair`. A
project-owned contract may expose only a subset.

Supported resource diagnostics aliases include `resource diagnose`, which runs
the configured read-only instance availability collection. Use the task
contract's additional resource-evidence operation when the fast path says that
historical CPU, memory, OOM, disk, or capacity evidence is needed.

Supported domain knowledge aliases are `domain inspect`, `domain get`,
`domain search`, `domain plan`, `domain maintain`, and `domain verify`.
The managed contract defaults to `docs/domain-concepts.md` and the `lite`
profile when a project has not registered its own `domain-knowledge` task.

When a repository does not register a `release-deployment` task, resolve the
skill-owned managed contract. Do not treat a similarly named repository script
as a substitute. Managed `inspect` and `bootstrap-plan` remain read-only;
mutating operations fail closed until the repository has an explicit
`release-workflow.json` with artifact and target hooks. Read
[release-workflow-config.md](references/release-workflow-config.md) before
bootstrapping or changing those hooks.

Legacy v1/v2 profiles remain readable during migration. They return composed instructions and declarative command strings; read their resolved instructions because they do not provide executable contracts.

## Select the Governance Domain

- For project design, architecture, module ownership, scaffolding, or implementation handoff, read [design-doc-rules.md](references/design-doc-rules.md), [project-scaffolding.md](references/project-scaffolding.md), and [legacy-extraction.md](references/legacy-extraction.md) as applicable.
- For a current or proposed third-party library, framework, service, runtime, replacement, or technology fit assessment, read [dependency-evaluation.md](references/dependency-evaluation.md). Keep official upstream evidence, project facts, and AI inference distinct; pin shared evidence revisions when the compatible `recall-resources` capability is available.
- For SemVer, migrations, compatibility surfaces, release identities, tags, promotions, retries, or hotfix ancestry, read [git-version-governance.md](references/git-version-governance.md) and [release-deployment.md](references/release-deployment.md) only when the task contract cannot decide the required semantic boundary.
- For requirements, baselines, plans, archives, lifecycle, or verification ownership, read [requirements-governance.md](references/requirements-governance.md), [baseline-design.md](references/baseline-design.md), [document-lifecycle.md](references/document-lifecycle.md), and [verification-traceability.md](references/verification-traceability.md) as needed.
- For project-wide documentation inventory, missing or invalid `mdq` contracts, stale lifecycle state, link and index drift, or authorized documentation cleanup, resolve `document-maintenance` and read [document-maintenance.md](references/document-maintenance.md).
- For ubiquitous language, stable concept identifiers, aliases, bounded-context ownership, glossaries, or semantic relationships, resolve `domain-knowledge` and read [domain-knowledge.md](references/domain-knowledge.md). Keep requirements, baselines, plans, code, and tests authoritative for their own facts.
- For defects, recurrence, root cause, repair design, history, and test escape, resolve `defect-diagnosis` or `defect-history-review`; read [defect-governance.md](references/defect-governance.md) for semantic judgment.
- For feedback triage, reward approval, repair-to-release handoff, or closure, resolve `defect-feedback-lifecycle`; read [defect-feedback-lifecycle.md](references/defect-feedback-lifecycle.md) at authority transitions.
- For host or Compose availability, CPU, memory, OOM, disk, restart, exit, capacity, or resource-pressure diagnosis, resolve `resource-diagnosis`; read [resource-diagnostics.md](references/resource-diagnostics.md) and use the project-owned collector profile.
- Before creating, changing, reviewing, or accepting any host-visible port,
  resolve `port-allocation` and use `project-segments.py`; this includes
  loopback, LAN, Tailscale, monitoring, infrastructure, and standard-protocol
  ports. A standard protocol port may remain container-private only when the
  project documents its PPISS host translation. Treat missing or invalid
  project port configuration as a blocker. Read
  [port-allocation.md](references/port-allocation.md) for an established-port
  migration.
- For repeated, specialized, high-risk workflow extraction, read [project-skill-design.md](references/project-skill-design.md). Prefer concise policy, project configuration, and tested scripts.

Treat these domains as peers. Crossing a domain boundary does not transfer authorization.

## Preserve Non-configurable Invariants

- Do not broaden user authorization through configuration or task output.
- Do not expose credentials, authorization headers, request bodies, captures, or provider secrets.
- Do not mutate a published release tag or re-resolve a moving deployment ref.
- Keep release/retry identity fixed to the recorded full commit and immutable tag.
- Treat host-shared ingress, reverse proxies, load balancers, and tunnels as
  separately owned infrastructure. An application executor must not edit or
  restore a monolithic shared configuration or reload the shared process
  directly. It may submit only its declared project fragment through a
  host-owned serialized transaction that validates the complete composed
  candidate and preserves every other project. Without that contract, leave
  shared ingress unchanged.
- When a release or deployment needs shared host infrastructure, use the
  installed `host-governance` skill as the separate transaction owner. Resolve
  its configured `control` operation from the consuming project, execute only
  through its validated runner, and preserve the returned host transaction ID,
  generations, safe digests, phase, and verification state as referenced
  deployment evidence. Do not copy its state machine into a release hook.
- When the highest stable tag is already reachable from the committed
  integration ref, freeze that ref into an isolated retained release lineage
  without inspecting control-worktree cleanliness. Release and deployment
  preflight must not run `git status` against the control worktree.
- After source freeze, do not make release or deployment status depend on the
  moving integration branch. Treat synchronization back to it as a separately
  authorized and separately reported operation.
- Do not classify a defect root cause, recurrence, ownership, requirement status, priority, or breaking-change acceptance from a script result alone.
- Do not turn passing checks into automatic proof of product semantics or deployment success.
- Stop for a decision when resolution would change user outcomes, permissions, data guarantees, compatibility, accepted Git history, or release identity.

## Govern Documents

Use `queryable-markdown` for every governed Markdown document created or materially revised under this skill. A valid persistent mdq contract in YAML Front Matter is a mandatory part of the authorized governed-document write, not an optional follow-up. If an existing target has no valid contract, inspect and convert that target within the same authorized edit; the governance workflow supplies authority only for the minimal contract needed by that document and does not authorize unrelated normalization, bulk migration, sidecar creation, or repair of other documents.

Before completing the write:

1. define stable record identity, boundaries, and every field needed for lifecycle or authority queries;
2. keep semantic status in an explicit declared field rather than inferring it from prose or directory placement;
3. run mdq `validate`, `diagnose`, representative exact and negative queries, and any required collection scan;
4. stop with the document incomplete if the persistent contract is missing, invalid, ambiguous, or cannot expose the governed record.

Keep each fact in one primary authority layer: Requirement, Baseline, Plan, Code/Test Fact, Evaluation Evidence, Archive, or Operational Workflow. Evaluation Evidence supports a decision but does not make a candidate an installed or adopted dependency. Treat mdq as structural extraction only; AI and the applicable governance domain still decide status meaning, priority, completion, and authority.

Use the contracted document-maintenance operations when available:

- `docs inspect` and `docs plan` are read-only;
- `docs maintain` requires current explicit write authorization and bounds the
  documentation scope before edits;
- `docs verify` is read-only and is required after maintenance;
- `docs audit` remains a read-only compatibility operation with its legacy
  output schema; use `docs verify` for the expanded lifecycle checks.

Otherwise run:

```bash
node <skill-root>/scripts/validate-governance.mjs --root <project-root>
```

Document maintenance requires `queryable-markdown` and treats a missing or invalid persistent contract on governed requirements, baselines, plans, dependency evaluations, defects, archives, coverage, verification, or traceability documents as structural drift. Mechanical validation may also find broken links, identifiers, lifecycle mappings, or verification references. AI still decides semantics, priority, completion, and authority. Inventorying all Markdown does not make ordinary README, package, or operations documents governed records.

## Govern Domain Knowledge

Use one stable MDQ-backed concept protocol with the smallest profile that fits:

- `lite` for a compact shared vocabulary;
- `catalog` for structured concepts, aliases, kinds, scope notes, and
  relationships;
- `bounded` for DDD bounded contexts, arc42-style glossary and cross-cutting
  concepts, and a small SKOS-inspired semantic field set.

Do not create three incompatible document systems. Preserve concept IDs when
upgrading profiles. Domain documents own names, definitions, contexts, and
semantic relationships; they cite but do not duplicate requirement status,
effective baseline behavior, planned behavior, or implementation evidence.

Use `domain inspect/get/search/plan` for read-only discovery. `domain maintain`
requires current write authorization and returns a source-hashed bounded scope;
apply only the approved semantic edits, then run `domain verify`. A missing
default concept document is `not_configured`, not a failure for an existing
project. Scripts verify structure and relationships, while AI and project
stakeholders decide meanings, context boundaries, and accepted terminology.

## Govern Git, Releases, and Deployment

Use `git snapshot`, `release inspect`, and the applicable normal, promotion, or repair plan before semantic release decisions. Invoke `release run`, `release promote`, `release retry`, or `release repair` only with current explicit authorization and the exact target/ref authorized by the user.

Treat a request for a full release or release-and-deploy as authority over an
already committed source identity, not as authority to commit the control
worktree. Resolve the committed integration ref directly and use `release
prepare` to create or resume the retained release worktree. Do not inspect or
report control-worktree cleanliness during release inspection, planning,
preparation, execution, deployment, promotion, or retry. The isolated release,
repair, or detached worktree is the only checkout whose cleanliness is a
release/deployment precondition. If the user intends uncommitted bytes to enter
the candidate, obtain separate scope for finishing and committing those bytes
before release preparation.

After preparation freezes the source commit, determine release, retry, and
deployment status only from the retained release or repair lineage, immutable
tag, frozen artifacts, target transaction, and verification evidence. Treat
any later synchronization back to the integration branch as a separate
post-release integration operation. Report its status separately; a dirty or
moving control worktree may block that integration operation but must not
reopen, invalidate, or be described as blocking the frozen release.

When target completion depends on shared ingress, keep the project deployment
transaction and host transaction as separate monotonic identities. The project
executor may request `host-governance control plan` before application
mutation and the authorized `apply` plus read-only `verify` after the candidate
origin is ready. Deployment completion requires verified host evidence that
matches the exact project, target, release identity, and desired declaration
digest. A failed or incomplete host transaction leaves the application target
deployed but ingress-incomplete; it never authorizes direct reload, monolithic
configuration restoration, application rollback, or a successful deployment
tag.

For the managed contract, keep Git locking, version reservation,
`release/v<version>` and `repair/v<version>` worktrees, annotated stable tags,
artifact manifests, target transactions, and fixed-tag retries inside
`release-workflow.py`. Project hooks may test, freeze artifacts, deploy, verify,
or migrate, but must not recreate or bypass those identities. An artifact
freeze hook must finish with the structured evidence required by
[release-workflow-config.md](references/release-workflow-config.md). A deploy
hook must consume the frozen manifest and must not rebuild it.

Keep a stable release tag bound only to its exact source commit. A later
authorized `release promote` may append the first immutable artifact manifest
for a new target from a clean checkout of that tag; it must not amend the tag,
create a source commit, or replace an existing `(tag, target)` manifest. Every
successful `deploy/<target>/<UTC timestamp>/v<version>` tag must point to the
same release commit and record the selected artifact evidence.

Classify a failed deployment before the next mutation. Use `release retry` only when source remains unchanged at the fixed release tag. If source must change, use `release repair-plan` and `release repair` to create the next patch release from the failed immutable tag. Do not substitute a new normal release from current `main`, merge current integration changes into the repair candidate, or infer permission to synchronize the repair back to `main`.

When a pre-tag artifact build or freeze fails, inspect the resolved task
contract and project profile for every declared artifact acquisition, build,
or transfer mode before retrying or editing source. If neither a stable tag nor
an artifact manifest exists, prefer an already-configured mode that avoids the
failed execution boundary while preserving the exact commit, tree, target,
platform, and executor-owned identity verification. Do not invent a fallback,
change target, or switch modes after artifact identity is frozen.

Treat a missing project repair contract as a release-tooling capability defect, not automatically as a new authorization decision. When the current request already authorizes repairing the failed source and continuing the same target deployment, add the smallest repair contract, executor support, and focused tests on the isolated repair lineage, resolve the updated contract, and continue without asking for the same authority again. Otherwise stop and request only the missing repair authority. Never bypass the contract with a normal release.

Keep a repair candidate untagged while source verification, representative migration rehearsal, candidate admission, or target preflight is failing. Record candidate commits, artifact digests, and attempt evidence instead of minting stable patch tags. Create the next immutable patch tag only after every pre-tag gate passes; retries of that tag never create another version.

Treat repository release and deployment executors as automation boundaries. Do not reproduce their internal build, migration, health, canary, or smoke steps. Resume only the same yielded process. Do not retry by default; when the current request explicitly authorizes continued deployment or bounded retry, retry only transient failures with the same exact tag, commit, artifact, and target under the project contract. Never auto-promote, auto-rollback, restore state, migrate live data, or select a different commit.

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

For release work, always label the release/deployment state separately from
post-release integration state. Do not collapse an integration-branch conflict
or dirty-worktree blocker into `release failed` after source freeze.

After a deployment reaches a terminal state, make the final user-visible
handoff explicitly show the service interruption duration and its measurement
boundary, or `not measured` with the reason. Also show the exact release
identity and target, total deployment or release duration when available,
transaction status, health or canary result, database migration status, timing
anomalies, and safe evidence or log paths. Do not leave these facts only in
progress commentary or require the user to ask for them separately.

Do not release, deploy, publish, migrate live state, push, rewrite history, or move tags unless explicitly authorized in the current request.
