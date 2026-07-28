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

If the release is blocked before its source is frozen:

1. Identify the exact blocker and the next release stage it prevents.
2. Perform only the smallest already-authorized action needed to clear it.
3. Return immediately to the next incomplete release stage after it clears.
4. Freeze the source as soon as the authorized changes are committed and the
   integration worktree satisfies the project rules.

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
2. Resolve the intended source once to a full commit id and record it.
3. Require committed state. Never synthesize a release from uncommitted or
   untracked files.
4. Do not re-resolve a branch, `HEAD`, or another moving ref after the commit is
   frozen.
5. Keep the release tag, full commit id, and deployment target together in
   every plan, command boundary, retry, and report.

For a full release, require the primary integration worktree to be clean,
checked out on its integration branch, and still at the frozen source commit
before it is advanced. For deploy-only work, use the exact user-authorized
commit or immutable tag and do not mutate the control worktree.

## Isolate Work in Fresh Worktrees

Use a new temporary worktree for release planning, release preparation,
deploy-only work, and every retry. Verify its exact `HEAD` and cleanliness
before running checks, builds, version edits, or deployment commands.

- Use a detached worktree for a preview, deploy-only operation, or retry.
- Use a temporary `release/v<version>` branch at the frozen source for a full
  release.
- Run release checks, version edits, builds, and deployment from the isolated
  worktree.
- Never use `stash`, `reset`, `clean`, or forced removal to prepare the user's
  control worktree.
- Remove a successful clean worktree when it is no longer needed. Preserve and
  report a failed or dirty worktree while its evidence is still useful.

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

For a release:

1. Create the version commit on the temporary release branch.
2. Revalidate that the integration worktree is clean and unchanged.
3. Fast-forward or apply the project's explicitly approved integration policy.
4. Create the annotated `v<version>` tag only after the release commit is in
   integration history.
5. Verify the release worktree, integration branch, and peeled release tag
   resolve to the same full commit.

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

## Retry Only a Fixed Tag

After a deployment failure:

1. Preserve the recorded release tag and full commit.
2. Require the tag to remain immutable and reachable from the integration
   branch.
3. Create a fresh detached worktree at that exact tag/commit.
4. Re-run the project-configured retry gates and deployment command against the
   same target unless the user explicitly authorizes another target.
5. Never retry from a branch name, a newer `HEAD`, a reused uncertain
   worktree, or a newly inferred version.

Retry authorization does not include diagnosis, repair, rollback, database
restore, source retirement, or tag mutation. Obtain current authority for each
additional action.

## Respect Failure Boundaries

- Before integration: leave the integration branch and release tags unchanged;
  preserve the isolated worktree and relevant safe logs.
- After integration but before release tagging: report the exact partial state
  and stop; do not choose another commit or version.
- After release tagging but before verified deployment: keep the tag and commit
  fixed. Report the target as failed or deployed but unverified according to
  project evidence.
- After a failed acceptance check: do not print a success marker, create a
  successful deployment tag, promote, retry, or roll back automatically.
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
