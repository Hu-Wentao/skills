---
name: git-worktree
description: Manage Git worktrees, owner-task completion handoffs, and evidence-based local development-state maintenance. Use when Codex creates or enters a worktree; implements a plan, specification, or implementation prompt on a non-main task branch; must mark the final validated commit complete even when the worktree existed before the conversation; lists or creates worktrees; audits, merges, retains, deletes, rescues, or cleans local branches and worktrees; or safely removes stale registrations. Preserves active and dirty work, validates exact snapshots and HEADs, and keeps remote deletion, pushing, rebasing, squashing, stashing, and forced removal outside the workflow.
---

# Git Worktree

Manage worktrees from creation through merge and cleanup. Treat branch
maintenance as maintenance of every local development surface, not only named
unmerged branches.

## Prepare

1. Read the target repository instructions.
2. Check `git status --short`, the current branch, and `git worktree list --porcelain` before changing state.
3. Resolve `SKILL_DIR` to this skill directory and invoke the CLI with:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <repository-or-worktree> <command>
```

4. For any code implementation task, inspect the current directory rather than
   relying on whether this conversation created or remembers the worktree:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <current-worktree> \
  owner-status
```

Treat a user request to implement a plan, specification, or implementation
prompt in the current non-main worktree as ownership of that task branch for
this conversation. A worktree created before the conversation, created by
Codex before this turn, created manually by the user, or created during the
task has the same owner-completion lifecycle. Record the returned absolute
worktree path, branch, exact HEAD, main/detached status, active operations, and
completion state before editing.

## List Worktrees

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> list
```

Use the JSON result to identify worktree paths, checked-out branches, detached
worktrees, and the main worktree.

## Create a Worktree

Choose a short branch name aligned with repository conventions. Default the
base to the current branch only when the user did not specify another base.

- Treat a worktree explicitly requested by the user as user-owned. Keep it
  until the user explicitly requests cleanup or removal.
- Treat a worktree created only to isolate an internal temporary task as
  agent-created temporary state. Create it with `--temporary` so the CLI
  persistently records its base commit and original target branch. Deliver its
  completed change to that target and automatically remove the worktree before
  reporting the requested repository update complete. Refuse forced cleanup
  and preserve it if delivery is unsafe.

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> create \
  --branch <new-branch> [--base <base-branch>] [--path <worktree-path>] \
  [--temporary]
```

The default path is a sibling of the main worktree named
`<project>-T-<branch>`, with `/` converted to `-`. Initialize dependencies only
when appropriate and follow the repository's package-manager instructions.
Explicit `--path` values must also be outside the repository root. Prefer
omitting `--path` so the deterministic creator selects the sibling path;
paths below the repository (including `.worktrees/`) are rejected.

## Mark Owner Completion

For an owned plan/specification implementation on an eligible non-main task
branch, marking completion is a required handoff step. After every authorized
change is committed and every source-worktree validation passes, run
`owner-status` again, confirm the worktree is clean and has no active Git
operation, resolve its final exact HEAD, and mark that commit complete:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <worktree-path> \
  mark-complete --expected-head <exact-head>
```

This creates the local custom ref `refs/agents/completed/<branch>` at the exact
branch commit. It is neither a normal tag nor a remote ref. Only the task that
owns the branch may create or refresh this handoff. Do not mark incomplete,
blocked, dirty, uncommitted, or unvalidated work complete.

The completion ref is not proof that the user's requested repository was
updated. After marking, run `owner-status` again and obey its ownership-aware
`next_action`:

- `user_owned` work ends as a handoff unless the user separately requests a
  merge or cleanup.
- `agent_temporary` work remains incomplete while `delivery.status` is
  `integration_required` or `target_validation_and_cleanup_required`.
- For `agent_temporary`, merge the exact completed HEAD to the recorded target,
  passing both exact HEADs from the latest `owner-status`; validate the merged
  target; and remove the temporary worktree with `--require-merged-into` and
  `--expected-head`. Only then report the repository update complete. The CLI
  rejects delivery without a current completion ref or to a different target.
- If the target is dirty, moved, conflicted, missing, or fails validation,
  preserve the branch and worktree and report `delivery blocked`; never report
  the implementation or skill update as complete merely because the completion
  ref exists.

Do not silently omit the terminal step. If the current path is the main
worktree, detached, dirty, locked, missing, uninspectable, prunable, has an
active Git operation, still has uncommitted authorized work, failed required
validation, or the plan is only partially implemented, do not create the ref;
report `completion marker: not created` and the exact blocker. If the owner
task completes without code changes because the exact branch HEAD already
satisfies and validates the requested plan, it may mark that validated clean
HEAD complete. Never create a normal `refs/tags/*` tag as a substitute.

A completion ref is current only while it equals the branch HEAD and every
attached worktree is clean. A matching ref becomes blocked while an attached
worktree is dirty, locked, missing, uninspectable, prunable, or has an active
Git operation; cleaning that state makes it current again. A later commit makes
the ref stale automatically. During maintenance, treat only a current
completion ref as the owner's explicit handoff; an absent, blocked, or stale
ref does not prove that the task is active or finished.

## Maintain Branches and Worktrees

Treat “整理分支” without a narrower scope as an audit of all local branches and
registered non-main worktrees against the target. Audit before mutation:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  maintenance-audit --target <branch> --all
```

The audit emits a stable `snapshot_id` over the target HEAD, every candidate,
all attached worktree state, and completion evidence. Any relevant state change
invalidates that snapshot. Only an `--all` audit is eligible as input to
`maintenance-run`; bounded audits remain inspection-only. An all-candidate
audit with a non-empty `rescue_required_worktrees` list is not run-eligible.
Resolve every preservation blocker and re-audit before building a terminal
decision plan.

Treat a clean detached worktree whose HEAD is outside the target and lacks an
exact ordinary local `refs/heads/*` or `refs/tags/*` anchor as requiring rescue.
Internal snapshot, reflog, remote-tracking, and completion refs do not satisfy
this requirement. Rescue these candidates immediately after the audit, before
semantic classification or any other maintenance mutation. Multiple detached
worktrees at the same exact HEAD need no additional rescue when that HEAD is
already anchored by an ordinary local branch or tag.

Use `--recent-count <N>` or `--recent-days <N>` instead of `--all` when the user
supplies a bounded window. The audit emits separate candidates for branch
history and worktree directories so a protected branch can be retained while
its completed clean worktree is removed. It reports:

- exact HEAD and target divergence;
- ancestry and patch equivalence;
- dirty and untracked files;
- detached, missing, locked, and prunable state;
- merge, rebase, cherry-pick, revert, or bisect state;
- owner completion ref status and whether it matches the exact branch HEAD;
- protected branch status and decision-specific requirements.

For every selected candidate, inspect its commits, diff, current target code,
governing requirements, tests, later replacements, and review history when
available. Assign exactly one decision within its reported `decision_scope`:

- **merge**: required behavior remains valuable and compatible. Preserve any
  branchless or uncommitted work first, validate it, merge it, and clean up only
  after validation succeeds.
- **retain**: work is active, incomplete, dirty, locked, protected,
  semantically unresolved, or otherwise unsafe to integrate or remove.
- **delete**: committed behavior is contained, patch-equivalent, demonstrably
  superseded, or has no remaining value. Record the evidence and exact commit.

### Reconcile published release lineages

Do not treat retaining or removing a `release/*`, `repair/*`, or `hotfix/*`
worktree as proof that its published fixes are present in the target. Before
classifying any protected branch, inspect its matching stable tag, the exact
peeled tag commit, and whether that commit is reachable from the target.

When the repository configures release governance, resolve
`project-governance` for `release-deployment` and use its read-only
`sync-main-plan` or equivalent operation as the authority for release-lineage
integration. If an explicit branch-maintenance request authorizes the required
local target merge, execute only the contracted `sync-main` operation. Do not
replace it with a generic merge of the protected branch: the branch may have
advanced beyond the immutable published tag. Re-audit all candidates after a
successful synchronization because the target HEAD and snapshot have changed.

If a published stable tag is not reachable from the target and governed
synchronization cannot complete, retain the branch and report the exact
tag/commit and blocker. Do not report branch maintenance as fully reconciled.
Merge conflicts, missing contracts, or unavailable authority are preservation
outcomes, not evidence that the published repair is obsolete.

Treat an untagged protected branch as an active or unresolved release lineage.
Retain its branch ref; a clean worktree may still be removed under the ordinary
worktree-only rules. Do not merge the candidate into the target, delete its
branch, or infer that its commits are published without a separate exact
release-resolution decision.

Treat a dirty worktree as presumptively active and default it to **retain**.
This includes tracked modifications, staged changes, and untracked files. If
the user identifies a branch/worktree as owned by another active thread, retain
it even when it happens to be clean at one observation. During branch
maintenance, do not modify, stage, commit, switch, merge, delete, remove,
rescue, install dependencies in, run write-capable validation in, or otherwise
advance an active or dirty worktree. Read-only inspection is allowed. A generic
“整理分支” or “合并所有分支” request does not override this ownership boundary;
acting on it requires a separate exact request that names the candidate and
authorizes the needed mutation.

If a candidate's HEAD, branch, or status changes after its audit, do not chase
new edits. Re-audit it, classify it as retain, and leave it for the owning
thread. If a rescue-required worktree disappears, stop the maintenance batch
and report its audited exact HEAD and remaining refs. Do not call an internal
snapshot or reflog entry a completed rescue; request authorization to create a
normal branch at that exact commit when the worktree can no longer be attached.
Dirty, active-operation, locked, missing, or uninspectable evidence is a
mutation blocker, not a prompt to repair the worktree from the maintenance
thread.

When a branch was previously identified as owned by another active task, a
later current `refs/agents/completed/<branch>` ref supersedes that earlier
observation if the audited HEAD still matches and the worktree remains clean.
The maintenance task must never create this ref on the owner's behalf.

Run maintenance as a fixed-point workflow. Preservation steps such as rescue
or pruning are not candidate decisions. Keep every rescued branch in the
current maintenance batch, even when its original commit falls outside a
recent-count or recent-days window, and continue until it reaches exactly one
terminal merge, retain, or delete decision. After any rescue, merge, or delete
changes refs or the target HEAD, refresh the affected evidence before the next
mutation.

Do not infer that a clean directory is completed work. Do not interpret age as
deletion evidence. Re-audit when any HEAD or worktree status changes. A request
to maintain a selected local scope does not authorize remote deletion, push,
tag changes, or cleanup outside that scope.

### Apply an exact decision plan

After semantic review, submit every candidate's terminal decision as JSON. Keep
the plan in the pipeline when practical; the script does not require a durable
state-file location.

```json
{
  "schema_version": 1,
  "snapshot_id": "<maintenance-audit snapshot_id>",
  "target": "main",
  "decisions": [
    {
      "candidate_id": "branch:feat/example",
      "decision": "merge",
      "reason": "required behavior is complete and validated"
    },
    {
      "candidate_id": "worktree:/absolute/example-path",
      "decision": "retain",
      "reason": "validate the merged target before cleanup"
    }
  ]
}
```

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <target-worktree> \
  maintenance-run --plan - < <decision-plan.json>
```

The plan must classify every candidate from the `--all` audit as `merge`,
`delete`, or `retain`, and every decision requires a reason. The runner:

- acquires one non-blocking Agent mutation lock in the repository's Git common
  directory; all mutating commands from this CLI use the same lock;
- refuses mutations while the target worktree is dirty, locked, missing,
  uninspectable, prunable, or has an active Git operation;
- rejects a changed snapshot before mutation, then rechecks each candidate and
  the expected target HEAD before every operation;
- executes branch merges first, classified branch deletions second, and clean
  worktree removals third;
- removes completion refs whose local branches no longer exist after a
  successful run;
- emits one structured completed report, or a structured paused report when a
  conflict or safety check stops execution; and
- never pushes, deletes remote refs, or changes normal tags.

The runner rejects the entire plan before its first mutation when any candidate
still has `rescue_required: true`. A `retain` decision cannot bypass this gate.

Do not plan deletion of a source worktree in the same run that merges its
branch. Retain it, validate the merged target, audit again, then submit cleanup
as a second exact plan. Set `allow_protected: true` only when deletion of the
named `release/*`, `repair/*`, or `hotfix/*` branch is separately authorized.
Set `allow_uncontained_detached: true` only for an evidence-reviewed discard.
Rescue an uncontained detached worktree before planning `merge`.

### Detached worktrees

Never remove a detached worktree merely because it is clean.

- If its HEAD is contained in the target and it is clean, remove it with both
  `--require-contained-in` and the audited `--expected-head`.
- If it has unique commits, attach an exact rescue branch before merge or
  any terminal retain/merge/delete decision unless its exact HEAD already has
  an ordinary local branch or tag. Rescue is a preservation transition, never
  an implicit retain decision:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  rescue-detached --worktree <worktree-path> --branch <new-branch> \
  --expected-head <audited-head> --target <target-branch>
```

The result includes the rescued branch's fresh maintenance `candidate`, marks
its `classification_status` as `pending`, and names the required next action.
Immediately inspect that candidate and continue with merge, evidence-based
delete, or an explicit retain reason. Do not end “整理分支” merely because every
detached HEAD now has a name. Conversely, do not end or start mutation while an
audited rescue-required HEAD still lacks a normal branch or tag.

- If it is dirty, retain it without changing its detached state. “整理分支”
  alone authorizes neither rescue nor commit. Rescue or “commit and merge” only
  after a separate exact request names this worktree and no concurrent owner is
  still editing it.
- To discard a reviewed uncontained detached HEAD, prefer rescuing it and then
  using the classified branch-deletion workflow. Direct removal additionally
  requires `--allow-uncontained-detached --reason <evidence>`.

### Missing worktrees

Prune only registrations whose paths no longer exist. Supply the complete
currently eligible set as audited `PATH=HEAD` pairs because Git prunes missing
worktrees repository-wide:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> prune-missing \
  --expect "<path-1>=<head-1>" --expect "<path-2>=<head-2>"
```

The command refuses a partial or changed set and retains every branch ref.
Locked missing registrations remain untouched.

## Maintain Recent Unmerged Branches

Keep the backward-compatible branch-only audit for explicit requests such as
“最近 N 个未合并分支” or “最近 N 天的未合并分支”:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-audit \
  --recent-count <N> [--target <branch>]

uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-audit \
  --recent-days <N> [--target <branch>]
```

Prefer `maintenance-audit` for any workflow that must include merged,
detached, dirty, or missing worktrees. Refresh remote refs only when remote
state matters and the user permits it.

Delete one classified branch with:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-delete \
  --branch <branch> [--target <branch>] --reason "<evidence>" \
  --expected-head <audited-head> \
  [--expected-target-head <audited-target-head>] \
  [--allow-unmerged] [--remove-worktree]
```

Use `--allow-unmerged` only after evidence-based classification. Use
`--expected-target-head` for every unmerged deletion so target movement
invalidates stale review evidence. Use
`--remove-worktree` only after clean-state checks. The command refuses dirty,
locked, prunable, missing, main, or Git-operation-in-progress worktrees.
`release/*`, `repair/*`, and `hotfix/*` require separate
`--allow-protected` authorization; otherwise retain their branch refs.

## Merge a Branch

Run from the worktree checked out on the target branch:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <target-worktree> merge \
  [--source <source-branch>] [--target <target-branch>] \
  [--expected-source-head <audited-head>] \
  [--expected-target-head <audited-target-head>]
```

The merge uses `git merge --no-ff --no-edit` and checks every affected
worktree. Interpret authorization narrowly:

- **Merge `<branch>`**: stop if either affected worktree is dirty.
- **Commit and merge `<branch>`**: inspect and commit only source-worktree
  changes, then rerun the merge command.
- **Merge and clean up `<branch>`**: merge first; remove the source worktree
  only after merge and validation succeed.

When Codex created a worktree with `--temporary` solely to implement the
user's requested change, that implementation authorization includes the safe
local merge into the target recorded at creation and removal of the clean
temporary worktree after target validation. It does not authorize push,
publication, remote deletion, branch deletion, history rewriting, or a
different target. A target HEAD change requires a fresh read-only comparison;
a dirty target or semantic conflict blocks delivery and must not be bypassed.

If conflicts occur, preserve clear intent from both branches, run focused
validation, and continue the merge. Stop when multiple semantic resolutions
remain plausible. Never resolve blindly with `ours` or `theirs`.

## Remove a Worktree

Remove a user-owned worktree only after an explicit cleanup or removal request.
Automatically remove agent-created temporary worktrees after use when safe.

For an attached branch after merge:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> remove \
  --worktree <worktree-path> --require-merged-into <branch>
```

For a detached worktree:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> remove \
  --worktree <worktree-path> --require-contained-in <target> \
  --expected-head <audited-head>
```

The CLI refuses the main worktree, dirty state, missing or prunable paths,
locked worktrees, and any active Git operation. Removing an attached worktree
retains its branch. Removing a protected branch's clean worktree does not
authorize deletion of the protected branch. Never force removal, stash, push,
rebase, or squash without authorization for that exact operation.

Removing an `agent_temporary` worktree also removes its internal temporary
ownership refs. Retain its ordinary local branch and completion ref unless a
separate branch-maintenance decision authorizes branch deletion.

## Report

Report:

- every branch and worktree decision with evidence and exact commit;
- every observed completion ref as current, blocked, stale, absent, or not
  applicable;
- maintenance snapshot IDs, repository-lock evidence, terminal decision
  reports, paused operations, and removed orphan completion refs;
- a separate **retained active/dirty work** list containing worktree path,
  branch or detached state, observed HEAD, dirty/untracked paths, active Git
  operations, retention reason, and the mutations intentionally skipped;
- rescued detached HEADs, preserved dirty changes, and the terminal decision
  subsequently reached by every rescued branch;
- source, target, and merge commit;
- removed worktree paths and deleted branch identities;
- pruned missing registrations and confirmation that branch refs remain;
- unresolved dirty state, active operations, or conflicts;
- validation commands and results;
- whether remote branches remained untouched;
- owner-task worktree identity discovered from the current directory, final
  exact HEAD, ownership kind, delivery status, target merge commit, removed
  temporary worktree, and the created/current completion ref, or the exact
  reason delivery did not finish;
- breaking and compatibility effects.

## Resource

- `scripts/git_worktree.py`: deterministic worktree lifecycle, unified
  maintenance audit and decision-plan runner, repository mutation locking,
  current-worktree owner-status discovery, exact completion handoff, detached
  rescue, exact stale-registration pruning, merge, and classified deletion
  with cross-worktree safety checks.
