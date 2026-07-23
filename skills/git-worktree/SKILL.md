---
name: git-worktree
description: Manage Git worktrees and local branch maintenance. Use when Codex needs to list or create worktrees, merge a worktree or local branch with an explicit merge commit, safely remove a worktree, or analyze the most recent N or last N days of unmerged branches and merge, retain, or delete each branch from evidence. Checks affected worktrees for dirty state, inventories patch equivalence and divergence, and keeps remote deletion, pushing, rebasing, squashing, stashing, and forced worktree removal outside the workflow.
---

# Git Worktree

Manage worktrees from creation through merge and cleanup, and maintain bounded
sets of unmerged local branches from evidence.

## Prepare

1. Read the target repository instructions.
2. Check `git status --short`, the current branch, and `git worktree list --porcelain` before changing state.
3. Resolve `SKILL_DIR` to this skill directory and invoke the CLI with:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <repository-or-worktree> <command>
```

## List Worktrees

Run:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> list
```

Use the JSON result to identify worktree paths, checked-out branches, detached worktrees, and the main worktree.

## Create a Worktree

Choose a short branch name aligned with repository conventions. Default the base to the current branch only when the user did not specify another base.

Classify ownership when creating the worktree:

- A worktree explicitly requested by the user is user-owned. Keep it until the
  user explicitly requests cleanup or removal.
- A worktree the agent creates only to isolate an internal temporary task is
  agent-created temporary state. Record its path and automatically remove it
  after the task finishes, before the final handoff. Its creation authorizes
  that cleanup; do not ask the user for separate removal confirmation.

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> create \
  --branch <new-branch> [--base <base-branch>] [--path <worktree-path>]
```

The default path is a sibling of the main worktree named `<project>-T-<branch>`, with `/` in branch names converted to `-`.

The CLI performs only Git creation. Afterward, inspect the new worktree's repository instructions and initialize dependencies only when appropriate. Follow the target repository's tools; for example, use FVM for Flutter, nvm plus pnpm for Node, and uv for Python. Do not fall back to global `flutter`, `npm`, or `pip` merely because a manifest exists.

## Maintain Recent Branches

Treat “最近 N 个未合并分支” as the N newest local unmerged branches by
committer time. Treat “最近 N 天” as branches whose newest commit is within the
last N×24 hours. Default the integration target to the current branch.

Inventory exactly one bounded window:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-audit \
  --recent-count <N> [--target <branch>]

uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-audit \
  --recent-days <N> [--target <branch>]
```

The result covers local unmerged branches only and reports divergence, patch
equivalence, upstream, commit identity, and associated worktree state. Refresh
remote refs first only when current remote state is relevant and the user's
request permits it. Do not interpret age alone as evidence for deletion.

For every selected branch, inspect its unique commits, diff, current code,
governing requirements or baselines, later replacement commits, tests, and
review history when available. Assign exactly one decision:

- **merge**: unique behavior is still required and compatible with current
  authority. Validate it, merge it, then delete the merged topic branch unless
  ongoing work requires retaining it.
- **retain**: the branch remains valuable but is incomplete, actively used,
  semantically unresolved, protected, or unsafe to integrate or delete.
- **delete**: the change is already integrated or patch-equivalent, is
  demonstrably superseded by accepted behavior, or has no remaining value.
  Record the evidence and the branch's final commit before deletion.

A request to maintain branches and merge/retain/delete them authorizes those
actions only for the selected local window. It does not authorize remote branch
deletion, pushing, tag changes, or cleanup of unrelated worktrees.

Use the normal merge workflow for `merge`. Delete one classified branch with:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> branch-delete \
  --branch <branch> [--target <branch>] --reason "<evidence summary>" \
  [--allow-unmerged] [--remove-worktree]
```

Use `--allow-unmerged` only for a branch explicitly classified `delete` from
evidence. Use `--remove-worktree` only after the command's clean-state checks
can safely remove every linked non-main worktree. The command refuses dirty,
locked, prunable, missing, main, or merge-in-progress worktrees and leaves
remote branches untouched. `release/*` and `hotfix/*` require separate explicit
`--allow-protected` authorization; otherwise retain them.

## Merge a Branch

Run the merge from the worktree checked out on the target branch:

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <target-worktree> merge \
  [--source <source-branch>] [--target <target-branch>]
```

Defaults:

- target: current branch;
- source: auto-select only when exactly one unmerged local branch is ahead of the target;
- strategy: `git merge --no-ff --no-edit`;
- dirty check: every active worktree checked out on the source or target branch.

Interpret user authorization narrowly:

- **Merge `<branch>`**: stop if either affected worktree is dirty.
- **Commit and merge `<branch>`**: inspect and commit only the source worktree changes, then rerun the merge command. Do not commit target-worktree changes as an implied part of the request.
- **Merge and clean up `<branch>`**: merge first; remove the source worktree only after merge and validation succeed.

If the merge pauses with conflicts, inspect conflicted files, preserve both branches' intended behavior when it is clear, run focused validation, stage resolved files, and finish with `git merge --continue` or `git commit --no-edit`. Stop for user input only when multiple semantic resolutions remain plausible. Never resolve blindly with `ours` or `theirs`.

## Remove a Worktree

Remove a user-owned worktree only when the user explicitly requests cleanup or
removal. Automatically remove an agent-created temporary worktree after its
temporary use ends; do not ask for confirmation merely because removal is
normally destructive.

```bash
uv run python "$SKILL_DIR/scripts/git_worktree.py" --repo <path> remove \
  --worktree <worktree-path> [--require-merged-into <branch>]
```

Use `--require-merged-into` after a merge-and-cleanup flow. The CLI refuses to remove the main worktree, a dirty worktree, a worktree with a merge in progress, or a worktree whose branch is not merged into the required target.

Before automatic temporary cleanup, verify that the worktree contains no
user-authored or otherwise unpreserved changes and no Git operation is in
progress. Never force removal. If safe cleanup fails, preserve the worktree and
report the exact blocker instead of silently abandoning or deleting it.

Removing a worktree does not delete its branch. Delete a branch only through an
explicit cleanup request or the bounded maintenance workflow above. Do not use
force on a worktree, stash changes, push, rebase, or squash unless the user
explicitly authorizes the exact operation.

## Report

Report:

- created or removed worktree path;
- source, target, and merge commit for a merge;
- initialization or validation commands run outside the CLI;
- unresolved dirty state or conflicts;
- each maintained branch's merge, retain, or delete decision and evidence;
- the commit identity of every deleted branch and whether a linked worktree was
  removed;
- whether remote branches were left untouched;
- breaking or compatibility effects.

## Resource

- `scripts/git_worktree.py`: deterministic worktree lifecycle, branch audit,
  merge, and classified local-branch deletion with cross-worktree safety checks.
