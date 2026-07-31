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
- Neither form authorizes a different target, tag mutation, rollback, restore,
  destructive migration, unrelated cleanup, or synchronization back to the
  integration branch.

If the release is blocked before its source is frozen:

1. Identify the exact blocker and the next release stage it prevents.
2. Perform only the smallest already-authorized action needed to clear it.
3. Return immediately to the next incomplete release stage after it clears.
4. Freeze the source as soon as the authorized changes are committed and the
   committed integration ref satisfies the project rules. Unrelated tracked,
   staged, or untracked control-worktree changes are not a source-freeze
   blocker unless the next required operation must mutate that worktree.

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

1. Read repository instructions and inspect the control worktree without
   modifying it.
2. Resolve the intended committed integration ref once to a full commit id and
   record it.
3. Require committed source identity. Never synthesize a release from staged,
   unstaged, or untracked files; those bytes remain excluded even when the
   control worktree is dirty.
4. When the highest stable tag is already reachable from the committed
   integration ref, create the retained release branch and worktree from that
   commit without requiring the control worktree to be clean.
5. Require a clean checked-out integration worktree only when the next required
   step must mutate that branch, such as synchronizing an unreachable previous
   stable tag. Do not commit, stash, reset, clean, or delete unrelated changes
   merely to satisfy release preparation.
6. Do not re-resolve a branch, `HEAD`, or another moving ref after the commit is
   frozen.
7. Keep the release tag, full commit id, and deployment target together in
   every plan, command boundary, retry, and report.

For a normal full release, the retained release lineage becomes the release
identity authority at source freeze. Later control-worktree dirtiness or branch
movement can block only a separately required integration mutation; it cannot
reopen or invalidate that frozen release. For a repair release, freeze the
failed release tag and its peeled commit as the base identity, then follow the
isolated repair rules below. For deploy-only work, use the exact
user-authorized commit or immutable tag and do not mutate the control worktree.

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
the same release commit. A failed or unverified deployment must not receive a
successful deployment tag.

Treat release and successful deployment tags as immutable records. Do not move,
delete, replace, or reuse them without explicit authorization for that exact
tag operation.

## Promote the Same Artifact

Promote one immutable release identity through environments. Resolve the
release tag and full commit before the first environment and use that exact
pair for every later environment. Do not rebuild from a branch, infer a newer
commit, or create a second release merely because promotion occurs later.

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

## Classify a Failure Before the Next Mutation

Record the failed phase, fixed identity, target, and whether source bytes must
change before choosing the next operation:

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
  scopes. After source freeze, an integration conflict, dirty control worktree,
  or later branch movement must not emit or be summarized as a release failure.
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

When synchronization back to the integration branch is requested, report it
under a separate post-release integration heading or structured scope. A
blocked or incomplete integration operation does not downgrade a successfully
tagged and verified release, and a successful release does not imply that
post-release integration completed.
