---
name: git-worktree
description: Manage Git worktrees and evidence-based local development-state maintenance. Use when Codex needs to list or create worktrees; organize branches; audit all, recent, merged, unmerged, attached, detached, dirty, missing, or prunable work; rescue branchless commits; merge, retain, or delete classified local branches and worktrees; or safely remove stale registrations. Preserves uncommitted and unreachable work, validates exact audited HEADs, and keeps remote deletion, pushing, rebasing, squashing, stashing, and forced removal outside the workflow.
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
  agent-created temporary state. Record its path and automatically remove it
  after the task finishes. Refuse forced cleanup and preserve it if unsafe.

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> create \
  --branch <new-branch> [--base <base-branch>] [--path <worktree-path>]
```

The default path is a sibling of the main worktree named
`<project>-T-<branch>`, with `/` converted to `-`. Initialize dependencies only
when appropriate and follow the repository's package-manager instructions.

## Maintain Branches and Worktrees

Treat “整理分支” without a narrower scope as an audit of all local branches and
registered non-main worktrees against the target. Audit before mutation:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  maintenance-audit --target <branch> --all
```

Use `--recent-count <N>` or `--recent-days <N>` instead of `--all` when the user
supplies a bounded window. The audit emits separate candidates for branch
history and worktree directories so a protected branch can be retained while
its completed clean worktree is removed. It reports:

- exact HEAD and target divergence;
- ancestry and patch equivalence;
- dirty and untracked files;
- detached, missing, locked, and prunable state;
- merge, rebase, cherry-pick, revert, or bisect state;
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

Do not infer that a clean directory is completed work. Do not interpret age as
deletion evidence. Re-audit when any HEAD or worktree status changes. A request
to maintain a selected local scope does not authorize remote deletion, push,
tag changes, or cleanup outside that scope.

### Detached worktrees

Never remove a detached worktree merely because it is clean.

- If its HEAD is contained in the target and it is clean, remove it with both
  `--require-contained-in` and the audited `--expected-head`.
- If it has unique commits, attach an exact rescue branch before merge or
  evidence-based deletion:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> \
  rescue-detached --worktree <worktree-path> --branch <new-branch> \
  --expected-head <audited-head>
```

- If it is dirty, rescue it before committing. “整理分支” alone does not
  authorize a commit. Inspect and commit only after the user authorizes
  “commit and merge” or an equivalent exact action.
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

## Report

Report:

- every branch and worktree decision with evidence and exact commit;
- rescued detached HEADs and preserved dirty changes;
- source, target, and merge commit;
- removed worktree paths and deleted branch identities;
- pruned missing registrations and confirmation that branch refs remain;
- unresolved dirty state, active operations, or conflicts;
- validation commands and results;
- whether remote branches remained untouched;
- breaking and compatibility effects.

## Resource

- `scripts/git_worktree.py`: deterministic worktree lifecycle, unified
  maintenance audit, detached rescue, exact stale-registration pruning, merge,
  and classified deletion with cross-worktree safety checks.
