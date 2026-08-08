---
mdq:
  version: 1
  dialect: gfm
  records:
    boundary:
      source: heading
      levels: [2]
    key:
      source: heading
  fields:
    title:
      source: heading
    raw:
      source: body
  tolerance:
    incomplete: false
---
# Release and Deployment Governance

## Separate Application Releases from Instance State

Use this workflow only when the requested object is a committed application
artifact, release identity, deployed code or image, or environment promotion.
Do not enter it for a one-off instance-state operation such as changing rows,
restoring a backup, importing data, rotating a credential through an existing
workflow, or migrating archived data.

For an instance-state request:

1. Perform a read-only feasibility check before creating code or changing
   remote state.
2. Stop when there are no actionable records.
3. Prefer, in order, an existing operational command, a read-only plan, a
   pinned one-off artifact with focused verification, and only then a permanent
   product command when the capability is repeated.
4. Keep application versions, release tags, images, schema, and unrelated
   services unchanged unless the request independently requires them.

Treat committing a one-off operational artifact as separate from releasing or
deploying the application.

## Require Current Authorization

Release, deploy, publish, promote, retry, roll back, restore, migrate live
state, and move or delete tags are separate external mutations. Perform only
the operations explicitly authorized in the current request. A prior request,
an existing automation, a prepared commit, or a failed earlier attempt does not
provide current authority for another mutation.

Resolve ambiguity before acting when the requested object could be either
application code or instance state. A target name, production host, or the word
“update” does not by itself authorize an application deployment.

## Keep Authorized Work Moving

When the current request explicitly authorizes a sequence such as completing
named pending changes, committing them, releasing the resulting commit, and
deploying it, treat every named step as current authority for that sequence.
Do not request the same authorization again between those steps. Do not extend
the sequence to an unnamed mutation.

Interpret retry and repair scope from the verbs the user actually authorized:

- A request to retry or keep deploying one frozen release authorizes only
  bounded attempts of the same commit, tag, artifact, and target.
- A request to fix or repair the failed release and keep deploying it until
  verified also authorizes the required next patch candidate and its named
  target gates. Do not ask again between diagnosis, repair, patch publication,
  fixed-artifact retry, and verification.
- A request to hotfix one currently deployed target authorizes read-only
  deployed-identity inspection, one isolated minimal repair from that exact
  tag, the next global patch reservation, contracted hotfix gates, publication,
  and verified deployment back to the same target.
- Neither form authorizes a different target, tag mutation, rollback, restore,
  destructive migration, unrelated cleanup, or synchronization back to the
  integration branch.

If the release is blocked before its source is frozen:

1. Identify the exact blocker and the next release stage it prevents.
2. Perform only the smallest already-authorized action needed to clear it.
3. Return immediately to the next incomplete release stage after it clears.
4. Freeze the source as soon as the authorized changes are committed and the
   committed integration ref satisfies the project rules. Do not inspect
   control-worktree cleanliness as part of release or deployment preflight.

Classify a discovery as a hard blocker only when it prevents producing the
explicitly requested committed source, leaves the source or target identity
ambiguous, violates a non-configurable safety invariant, or fails a required
project gate or release-automation boundary. Treat adjacent defect suspicions,
opportunistic cleanup, optional hardening, unrelated documentation drift, and
exploratory analysis not required by a failed gate as follow-up work.

Only a hard blocker or superseding user instruction may pause an authorized
release workflow. When clearing a hard blocker requires an operation outside
the current authorization or a source change after the release identity is
frozen, stop and request that exact authority. Otherwise, report non-blocking
findings separately and continue. Do not start a general code review, broad
root-cause investigation, refactor, or documentation cleanup while a
currently authorized release is waiting to advance.

## Freeze the Release Identity

1. Read repository instructions and resolve the committed integration ref
   without inspecting control-worktree cleanliness.
2. Resolve the intended committed integration ref once to a full commit id and
   record it.
3. Require committed source identity. Never synthesize a release from staged,
   unstaged, or untracked files; resolving the branch ref excludes those bytes
   without a control-worktree status check.
4. Create the retained release branch and worktree from the resolved committed
   source without running `git status` against the control worktree.
5. Treat synchronization of an integration branch as a separate operation
   with its own prerequisites. Never import its checkout-cleanliness gate into
   release or deployment planning, preparation, execution, or reporting.
6. Do not re-resolve a branch, `HEAD`, or another moving ref after the commit is
   frozen.
7. Keep the release tag, full commit id, and deployment target together in
   every plan, command boundary, retry, and report.

For a normal full release, the retained release lineage becomes the release
identity authority at source freeze. Later branch movement can block only a
separately required integration mutation; it cannot reopen or invalidate that
frozen release. For a repair release, freeze the failed release tag and its
peeled commit as the base identity, then follow the
isolated repair rules below. For deploy-only work, use the exact
user-authorized commit or immutable tag and do not mutate the control worktree.
For a deployed-base hotfix, freeze the target's verified current stable tag,
peeled commit, successful transaction, immutable deployment evidence digest,
and the committed controller identity used to inspect and execute the flow.

## Separate Project Releases from Module Artifacts

In a repository with a project release version and independently versioned
modules, freeze both identities without collapsing them:

- The project version and release tag identify the complete committed source
  release.
- A module version identifies that module's immutable runtime artifact.
- Bump a module only when its artifact changes through its direct runtime
  inputs, transitive first-party runtime dependencies, or a shared input proven
  to affect that artifact.
- Keep unaffected module versions unchanged across project releases and reuse
  their existing immutable artifacts during deployment.

Do not treat a repository-wide lockfile, root manifest, workspace file,
compiler base config, or shared Dockerfile as automatic evidence that every
module artifact changed. Resolve the production dependency closure or compare a
canonical per-module runtime-input manifest. A shared input may bump every
module only when its semantic delta actually changes every artifact, such as a
runtime base-image or universal build-output change.

Require release automation tests that prove direct and transitive changes bump
the correct modules, test/document-only and unrelated lockfile changes do not,
target-specific shared inputs affect only their targets, and genuinely global
runtime changes affect all modules. Artifact reuse must use the unchanged
module identity; rebuilding different bytes under an unchanged module version
is forbidden.

## Isolate Work in Fresh Worktrees

Use a new isolated worktree for release planning, release preparation,
deploy-only work, and every retry. Verify its exact `HEAD` and cleanliness
before running checks, builds, version edits, or deployment commands.

- Use a detached worktree for a preview, deploy-only operation, or retry.
- Use a retained `release/v<version>` branch at the frozen source for a normal
  full release.
- Use a retained `repair/v<version>` branch rooted at the failed immutable
  release tag for a repair release.
- Use a retained `hotfix/v<version>` branch rooted at the target's verified
  currently deployed stable tag for a deployed-base hotfix.
- Run release checks, version edits, builds, and deployment from the isolated
  worktree.
- Never use `stash`, `reset`, `clean`, or forced removal to prepare the user's
  control worktree.
- Remove a successful clean worktree when it is no longer needed, but retain
  its release or repair branch according to project policy. Preserve and report
  a failed or dirty worktree while its evidence is still useful.

## Create and Preserve Git Identities

Use these tag formats:

```text
release tag:
  v<version>

successful deployment tag:
  deploy/<target>/<UTC timestamp>/v<version>
```

The UTC timestamp must be an unambiguous, filename-safe UTC instant. A project
profile may select a precise rendering, but it must preserve UTC ordering and
must not replace the target or release version components.

For a normal release, follow the project's contracted integration policy:

1. Create the version commit on the retained release branch.
2. Keep the release branch and its clean worktree fixed as the candidate
   authority.
3. If the contract requires the release commit in integration history before
   tagging, revalidate the integration ref and require a clean control worktree
   only for that mutation. If it is dirty or moved, report the integration
   operation as blocked without changing the frozen release status.
4. Apply only the project's explicitly approved integration policy.
5. Create the annotated `v<version>` tag at the contracted admission point.
6. Verify the retained release branch and peeled tag resolve to the same full
   commit; also verify the integration branch only when the contract makes it
   an identity participant.

Create a successful deployment tag only after the project's required health,
identity, and acceptance evidence declares that target verified. Point it to
the same release commit as the stable release tag. Record the target, artifact
manifest digest or immutable artifact digests, and deployment transaction
identity in the annotated tag message or another immutable referenced record.
Creating a deployment tag does not require or authorize a source commit. A
failed or unverified deployment must not receive a successful deployment tag.

Treat release and successful deployment tags as immutable records. Do not move,
delete, replace, or reuse them without explicit authorization for that exact
tag operation.

## Promote the Same Release Identity

Promote one immutable release identity through environments. Resolve the
release tag and full commit before the first environment and use that exact
pair for every later environment. Reuse the exact same artifact digest when it
is compatible with the next target. When targets require different platform or
build artifacts, key each immutable manifest by `(release tag, target)`.

A later authorized promotion may create the first manifest for a target after
the stable tag exists only from a clean detached checkout of that exact tag.
Persist the new manifest append-only before deployment. Never overwrite,
delete, or rebuild an existing `(release tag, target)` manifest, and never read
or resolve a moving branch for this operation. Resolve build and target hooks
from the tagged checkout rather than the control worktree. This adds deployment
evidence, not source history: do not create a source commit or move the release
tag. If source or build configuration must change, create a new release
version.

Run every environment-specific gate from a clean checkout of the same commit.
Advance to the next environment only after the preceding environment satisfies
its configured completion evidence. A partial, failed, or unverified
environment blocks automatic promotion but does not authorize rollback or
another commit.

## Resolve Target-Specific Execution Defaults

A project may select different build or artifact-transfer defaults by deployment
target. Keep that mapping in the project profile and resolve it deterministically
inside the repository executor after the target is known. When the task contract
cannot express a conditional default, omit the scalar parameter default so the
runner does not overwrite the executor's target-aware choice.

Keep explicit contracted parameters as per-run overrides. A default-mode change
does not authorize a release, deployment, retry, promotion, or a change to a
frozen tag.

## Source Delivery

Use exactly one source-delivery mode: `archive` or `github`. The project
profile must declare the deterministic source-preparation command and the
deployment controller that owns transport, receiver verification, extraction,
source execution, cleanup, and failure propagation. The task contract must
expose only that enum plus every required mode-specific input. Read
[source-delivery.md](source-delivery.md) for the required archive and GitHub
invariants. Do not make a release by copying a worktree, enumerating helper
files, using `rsync` for source acquisition, or asking the server to pull a
moving Git ref.

## Govern Shared Host Ingress

Classify ingress, reverse-proxy, load-balancer, and tunnel ownership before an
application deployment mutates routing:

- A dedicated ingress instance may be owned by one project when the project
  contract explicitly declares its configuration, reload, and recovery hooks.
- A shared ingress instance is host-scoped infrastructure. The host controller
  owns the root configuration, reload capability, protected credentials,
  project registry, hostname claims, transaction journal, and host-wide lock.
  Each project owns only its declared fragment and desired upstreams.

Application deployment authority alone does not authorize a shared-ingress
mutation. Resolve the installed `host-governance` skill's `control` operation
from the consuming project. A configured `host-governance.config.v2` task
contract must bind the host operation to a stable project identity, declared
fragment, hostname claims, and target. Execute it only through the
`host-governance` validated runner. If no such contract exists, keep the
current shared routing unchanged and report the missing capability; never fall
back to a command string embedded in the project release profile.

A shared-ingress transaction must:

1. Keep unrelated project fragments byte-for-byte unchanged and reject an
   undeclared hostname, fragment, or ownership collision.
2. Treat an earlier `control plan` as advisory. During authorized `control
   apply`, acquire the host-wide lock, re-read authoritative and live state,
   and verify the expected owner-specific or complete configuration generation.
3. Compose the complete candidate from every currently registered fragment while
   substituting only the requesting project's candidate fragment.
4. Validate that complete candidate through the host-owned privileged wrapper.
   Keep credentials inside the wrapper and out of commands, logs, generated
   fragments, and transaction evidence.
5. Replace only the owned fragment atomically, reload through the host
   controller, and persist the stable host transaction ID, base/result
   generation, desired declaration digest, composed candidate digest, phase,
   and safe evidence.
6. Verify the shared process, the changed project routes, and every registered
   project's declared lightweight health check. A process-level success alone
   is insufficient because a shared reload has cross-project blast radius.
7. If commit or verification fails, use the controller's declared transaction
   compensation to restore only the requesting project's previous fragment,
   recompose the prior complete configuration, reload, and reverify all
   registered checks. This is completion of the ingress transaction, not
   authority to roll back application code, restore data, or overwrite another
   project's fragment. Preserve a failed transaction for reconciliation when
   compensation cannot be verified.

Prefer stable project-owned loopback upstreams so an ordinary application
release does not need to mutate ingress. When routing must change for cutover,
bring the candidate origin to readiness first, then run the shared-ingress
transaction while the prior origin remains available until routing acceptance
passes. Persist application deployment and host-ingress transactions as
separate monotonic identities; success or authority for one does not imply the
other. The project transaction stores only a reference to safe host evidence,
not a copy of the host journal or complete configuration.

Run read-only `control verify` after apply. A successful deployment target that
depends on changed shared ingress requires the returned host evidence to match
the exact project, target, release identity, desired declaration digest, and
verified result generation. If the application is healthy but the host
transaction is failed or incomplete, report `deployed but ingress-incomplete`,
do not create the successful deployment tag, and resume only the same
authorized host transaction or its declared reconciliation operation.

An application rollback never restores a captured shared root configuration.
After separate current rollback authority, request the prior project
declaration through `host-governance control rollback`; the host controller
must recompose the latest declarations for every owner and verify the resulting
generation.

If scoped fragment ownership, complete-candidate validation, serialized reload,
credential isolation, and cross-project recovery cannot all be guaranteed, do
not automate a shared-ingress mutation from an application release. Use a
dedicated ingress instance or obtain a separately governed host operation.

## Classify a Failure Before the Next Mutation

Record the failed phase, fixed identity, target, and whether source bytes must
change before choosing the next operation:

1. Determine whether a stable tag exists and whether any artifact manifest was
   persisted for the exact candidate and target.
2. For a pre-tag artifact build or freeze failure, inspect the resolved task
   contract and project profile for every declared artifact acquisition,
   build, or transfer mode, including explicit overrides hidden by a
   target-specific default.
3. Compare those configured modes against the failed execution boundary before
   changing source, resource thresholds, build limits, or retrying the same
   deterministic failure.
4. When no stable tag or artifact manifest exists, prefer an already-configured
   mode that bypasses the failed build location while preserving the exact
   commit, tree, target, required platform, and executor-owned digest and
   identity verification.
5. Never invent an unconfigured fallback, bypass the project executor, change
   target implicitly, or switch modes after an artifact manifest or stable tag
   has frozen the artifact identity.

- Before a release tag exists, repair the authorized candidate and rerun its
  gates; do not manufacture a failed release identity.
- For a transient transport, registry, resource-admission, or host failure,
  retry the same immutable tag, commit, artifact digest, and target.
- For a source, migration, or packaging defect after tagging, preserve the
  failed tag and create the next patch release through the repair workflow.
- For an acceptance or evidence timeout with unchanged running source, rerun
  only the project-owned verification or reconciliation boundary when it
  supports that operation; do not rebuild.
- For a partially switched or data-affecting deployment, preserve evidence and
  use only the project executor's declared reconciliation path. Rollback,
  restore, or destructive migration remains separate authority.

Make transient retries bounded and idempotent. The project contract or executor
must declare attempt limits, backoff, and the terminal state. A request to
continue until verified keeps already-authorized retry or repair operations
active; it does not convert repeated deterministic failures into transient
ones or broaden the mutation scope.

## Diagnose and Qualify Before Publishing

For a project that supports candidate qualification, keep fast diagnosis,
production-shape qualification, and publication/deployment as separate
contracted operations:

1. Run the fast diagnostic graph against one exact committed candidate. Emit
   the first actionable failure immediately while continuing independent safe
   gates; mark dependent gates as blocked instead of hiding them.
2. Persist private per-gate evidence, stable failure codes, input digests,
   fingerprints, durations, cache decisions, and a deterministic reproduction
   operation. Do not expose detailed logs or sensitive values in progress
   events.
3. Give every diagnostic and production-shape check an explicit project-owned
   timeout, terminate its process group at the boundary, and retain bounded
   progress output plus private full stdout/stderr. A timeout is a classified
   failure with evidence, never permission to wait indefinitely.
4. Reuse a successful gate only when its declared input digest, toolchain, and tool policy
   remain identical. After a repair, rerun the failed gate and its downstream
   dependencies rather than every unrelated gate.
5. Run production-shape qualification before creating a stable tag. Bind its
   receipt to the exact commit, tree, target, artifact mode, source evidence,
   and immutable artifact manifests.
6. Make publication/deployment consume that receipt. It may refresh short-lived
   target admission but must not rediscover source, rebuild artifacts, or use
   the live deployment as the first realistic integration test.

Persist a technical release-task identity when attempts can cross processes or
worktrees. Track cumulative qualification duration and failure fingerprints,
but never persist or broaden user authorization. Reject an unchanged
deterministic failure, bound transient retries, and trip a project-configured
circuit breaker after the declared distinct-failure or duration budget. A
generic request to continue does not override that breaker.
Treat a process that disappeared with a running attempt as an interrupted
failure and count it against the retry and duration budgets; stale `running`
state must not create an unbounded crash loop.

Record timing for failed as well as successful attempts. Measure at least the
time to first actionable failure, per-gate duration, blocked dependencies,
cache reuse, and total qualification duration. Passing timing checks remains
operational evidence, not proof of product semantics.

### Establish generated outputs before tests

Treat generated output consumed through a package export, generated client,
compiled schema, code-generation entry point, or equivalent build-backed import
as a prerequisite of the consuming test gate. A checkout may contain stale or
missing ignored output even when its tracked source is clean, so test discovery
must not rely on whatever output a prior command happened to leave behind.

For each consuming gate, require the project contract or its deterministic
executor to:

1. detect changes to package export maps, generated entry points, their source,
   build configuration, workspace dependency graph, lockfile, or toolchain;
2. select the smallest affected producer dependency closure and build it in
   dependency order before starting consumers;
3. invalidate the selected producers' declared generated directories before
   rebuilding, so an old file cannot satisfy the gate;
4. verify every selected export or generated entry target exists after the
   build and before test collection; and
5. include the producer inputs and generated-output verification in the gate's
   reuse digest and private evidence.

Keep the commands and output-directory declarations project-owned. Do not
guess package-manager commands, delete undeclared directories, or expand an
affected build into a full-workspace build without a project contract. If a
test is started before these prerequisites and fails only because a generated
entry is absent, classify the incident as qualification orchestration and fix
the gate ordering; do not count it as a product defect, deterministic candidate
fingerprint, or transient retry. If the declared build or post-build export
verification fails, retain that failure as the actionable build evidence.

## Separate Maintenance Validation from Release Gates

Tests that validate a release-governance skill, its project configuration,
repository-owned release controllers, or the focused test harness are
maintenance validation. Declare them in the project task contract as a
standalone read-only operation, such as `maintenance-validate`, with their exact
project command. Run that operation after changing the governed skill,
controller scripts, contract/configuration, or corresponding focused tests and
before publishing or merging those changes.

Normal release operations must not invoke maintenance validation. Keep it out
of inspect, prepare, Doctor, qualification, publication/deployment, promotion,
repair, and retry paths. Release Doctor and qualification may run product or
candidate tests whose purpose is to validate the exact application candidate;
the project contract must declare those separately as candidate gates. A test's
directory does not determine its role: classify it by the behavior and evidence
it validates.

## Admit Stable Tags Only After Candidate Gates

Do not create a stable patch tag merely because repair work has started or a
candidate attempt exists. Keep the repair branch untagged while any pre-tag
gate fails. Use commit ids, immutable candidate artifact digests, CI run ids,
and deployment-attempt records for intermediate evidence.

Before creating the stable repair tag, require all project-declared source
verification, focused and regression tests, representative legacy-schema
migration rehearsal, candidate admission, artifact verification, and target
preflight gates to pass. Run migration rehearsal against a sanitized copy or
fixture that preserves the relevant production schema shape; never use the
live database as a speculative candidate test.

After a stable tag exists:

- Transient deployment or verification failures retry the same tag, commit,
  and artifact digest and never consume another version.
- A deterministic source defect that requires changed bytes produces the next
  patch version because the published tag remains immutable.
- Pre-release tags may be used only when the project explicitly publishes and
  retains them as release identities. Do not create `-rc` tags merely as a
  substitute for ordinary candidate build and attempt records.

Frequent stable patch tags therefore indicate that a required failure mode is
escaping the pre-tag admission suite. Record and repair that test escape rather
than weakening tag immutability or reusing a version.

## Hotfix the Currently Deployed Release Without Advancing Main

Use a deployed-base hotfix when one successfully deployed target contains a
production defect and current integration history includes unrelated feature
work. Do not reinterpret this case as a normal release or as a repair of the
highest published tag.

1. Run the project-configured read-only target inspector. Require it to
   reconcile the live deployment manifest, completed deployment transaction,
   stable tag, full commit, and immutable deployment evidence into one
   content-identified result.
2. Cross-check the reported tag and commit against local annotated release and
   successful deployment evidence tags. Stop on missing, partial, unverified,
   or conflicting identity.
3. Freeze the committed controller identity separately from application
   source. Current controller code may inspect and orchestrate historical
   releases, but the candidate application source must start at the deployed
   tag and must never import integration-branch application bytes.
4. Reserve the immediate patch after the greatest version among all stable
   tags and untagged release, repair, or hotfix reservations. Root a retained
   `hotfix/v<version>` worktree at the deployed tag. Record lower untagged
   reservations as superseded without deleting, rewriting, or merging them.
5. Require a committed repair after version reservation and reject merge
   commits in the hotfix range. Run a project-owned scope gate that fails
   closed for migrations, release-controller changes, infrastructure,
   dependency-lock changes, or any other change the project classifies as too
   broad for hotfix.
6. Run the project-owned affected regression gates. Reuse only immutable
   deployed-base artifacts whose runtime inputs and digests are unchanged;
   rebuild and freeze the affected closure under the new release identity.
7. Re-run the target inspector immediately before tagging. If the target tag,
   commit, transaction status, or evidence digest changed, stop and require a
   new hotfix decision instead of deploying over a different base.
8. Create the new annotated stable tag only after scope, gates, artifact
   freeze, and target admission pass. Deploy and verify the same tag, commit,
   artifact manifests, and target transaction. Fixed-tag retry rules apply
   after publication.

Hotfix does not authorize rollback, restore, live migration, another target,
tag mutation, or synchronization back to the integration branch. Integrate the
repair separately after production is verified. A superseded lower reservation
cannot later publish its reserved version; preserve its work and create a new
higher normal release after the repair enters integration history.

If deployment fails after the hotfix tag exists, retry that fixed tag, commit,
artifact manifest, and target through the controller identity frozen in the
hotfix state. Do not fall back to release scripts embedded in the older
application lineage and do not re-run source qualification or rebuild the
artifact during retry.

## Repair a Frozen Release Without Advancing Main

Distinguish retry from repair before selecting an executor:

- If source does not change, retry the exact failed tag and commit.
- If source must change, create a new patch release from the failed immutable
  tag through the project-configured repair operation.
- If the project has no repair contract and the current request already
  authorizes source repair plus continued release/deployment, treat the missing
  operation as a project release-tooling defect. On the isolated repair
  lineage, add the smallest task contract, executor support, and focused tests;
  resolve the updated contract and resume the same repair sequence.
- If repair is not currently authorized, stop and request that exact authority.
  Never fall back to a normal release from current `main`.

For a repair release:

1. Freeze the failed release tag, its peeled full commit, the target, and the
   proposed new patch version.
2. Require the failed tag to remain immutable. The project may additionally
   require it to be the highest published release tag so ordinary SemVer
   selection remains unambiguous.
3. Create a fresh `repair/v<version>` worktree rooted at the failed tag. The
   candidate may contain only explicitly authorized repair commits and the
   generated version commit after that base.
4. Reject merge commits in the repair range. Never merge, rebase, or otherwise
   import the current integration branch into the repair candidate. Surface the
   complete commit and changed-file range from the frozen base for review.
5. Run the project-configured repair gates, create a new immutable patch tag,
   and deploy that exact new tag. Keep the failed tag unchanged.
6. Keep the repair branch or another explicit maintenance ref reachable until
   project retention policy permits removal. Do not require current `main` to
   equal the candidate and do not fast-forward `main` as part of repair.
7. Synchronize the repair to `main` only as a separate operation with current
   user authorization. `main` is the later integration destination, never the
   source of an in-progress repair.

If deployment of the new repair tag fails without requiring another source
change, a project retry contract may accept the retained exact
`repair/v<version>` branch as its reachability anchor. The peeled tag commit and
the retained branch head must match exactly. This exception does not permit a
moving branch ref, a different repair commit, or a retry before the immutable
repair tag exists.

A request to fix and republish a failed release authorizes neither unrelated
integration content nor a normal release from the latest integration branch.
Changing the frozen base tag, target, or repair version requires a new explicit
decision.

## Retry Only a Fixed Tag

After a deployment failure:

1. Preserve the recorded release tag and full commit.
2. Require the tag to remain immutable and reachable from the integration
   branch or, for an isolated repair release, from the project-approved exact
   repair branch whose head equals the peeled tag commit.
3. Create a fresh detached worktree at that exact tag/commit.
4. Re-run the project-configured retry gates and deployment command against the
   same target unless the user explicitly authorizes another target.
5. Never retry from a branch name, a newer `HEAD`, a reused uncertain
   worktree, or a newly inferred version.

A retry-only authorization does not include diagnosis, source repair,
rollback, database restore, source retirement, or tag mutation. When the
current request explicitly authorizes a larger fix-release-deploy sequence,
carry that authority through its named steps without requesting it again.

## Respect Failure Boundaries

- Before integration: leave the integration branch and release tags unchanged;
  preserve the isolated worktree and relevant safe logs.
- After integration but before release tagging: report the exact partial state
  and stop; do not choose another commit or version.
- After release tagging but before verified deployment: keep the tag and commit
  fixed. Report the target as failed or deployed but unverified according to
  project evidence.
- After a failed acceptance check: do not print a success marker, create a
  successful deployment tag, promote, or roll back automatically. Retry or
  reverify only when the current request and project contract already authorize
  that exact fixed-artifact operation.
- Never infer permission to restore a database, retire source data, change
  credentials, or run a live migration from release or deployment authority.

Treat project release and deployment commands as automation boundaries. Wait
for the invoked command to finish, resume only the same yielded process, and do
not duplicate its internal build, migration, health, or smoke-test steps.

## Separate Progress Events from Detailed Logs

Prefer a concise machine-readable output mode when release automation supports
one. Keep complete child stdout and stderr in a private detailed log while the
terminal emits only explicit phase events and failures.

- Emit events at owned phase boundaries instead of classifying Docker, package
  manager, SSH, or test output with regular expressions.
- Include the fixed commit, release tag, target, phase, status, and safe log
  path when they are known.
- Treat source freeze, candidate creation, verification completion,
  integration, release tagging, artifact build or upload, deployment health,
  acceptance verification, and final completion as key events.
- On failure, emit the phase, stable command identifier, exit status, fixed
  identity, log path, and at most a bounded sanitized summary. Keep the full
  diagnostic output in the detailed log.
- Emit release/deployment state and post-release integration state as separate
  scopes. After source freeze, an integration conflict or later branch movement
  must not emit or be summarized as a release failure.
- Continue draining every child stream even when its lines are not forwarded
  to the terminal. Output suppression must never allow a pipe buffer to block
  the child process.
- Apply the same secret and sensitive-body protections to detailed logs. Use
  private permissions and never make a verbose log an excuse to retain
  credentials, authorization headers, request bodies, captures, or provider
  responses.

Keep existing verbose behavior as the compatibility default unless the project
explicitly migrates it. Agents should select the concise mode when available,
silently resume the same yielded process, and report only key events, errors,
or decisions that require the user. A product-required heartbeat may be terse;
it must not reproduce ordinary build progress.

## Report Completion

Report the frozen source commit, release version and tag, deployment target,
successful deployment tag when one was created, environment-gate results,
verification evidence, safe log paths, preserved failure worktrees, and every
operation that remains unauthorized or incomplete. Never report secrets,
authorization headers, request or response bodies, or private captured
payloads.

After every terminal deployment attempt, make the final user-visible handoff
show these fields explicitly rather than leaving them only in progress events
or detailed logs:

- deployment state and exact target;
- release tag and full commit;
- service interruption duration and its measurement boundary, such as service
  stop start through public health restoration;
- total release or deployment duration when the executor reports it;
- target transaction phase/status and database migration status;
- health, smoke, and required canary outcomes;
- timing-check classification, every abnormal phase with its observed value
  and threshold, and the read-only diagnosis outcome;
- successful deployment tag when created, plus safe evidence and log paths;
- any incomplete or unauthorized operation that remains.

If interruption or total duration evidence is unavailable, write
`not measured` and the exact reason; never silently omit it or infer a value from
timestamps that do not share the project's declared measurement boundary. A
deployment that completed without service interruption should report the
measured value as zero only when executor evidence proves that boundary.

When synchronization back to the integration branch is requested, report it
under a separate post-release integration heading or structured scope. A
blocked or incomplete integration operation does not downgrade a successfully
tagged and verified release, and a successful release does not imply that
post-release integration completed.
