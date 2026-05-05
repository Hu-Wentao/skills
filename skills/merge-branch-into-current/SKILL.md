---
name: merge-branch-into-current
description: Merge a specified branch into the current branch with a merge commit. Use this when the user wants to merge one branch into the current branch, or when Codex should auto-detect the source branch that has commits after the current branch. The skill checks whether the source branch and target branch have uncommitted work in any active git worktree and aborts if either branch is dirty.
---

# Merge Branch Into Current

## Scope

Use this skill inside a Git repository when the goal is to merge one branch into the current branch and keep an explicit merge commit.

Default behavior:

- Target branch: the current branch
- Source branch: the branch explicitly provided by the user
- Merge strategy: `git merge --no-ff`
- Dirty-check scope: the current worktree plus any active worktree that is currently checked out on the source or target branch

Do not use squash merge or rebase unless the user explicitly overrides the request.

## Workflow

### 1. Resolve branch names

Collect:

- source branch, called "specified branch"
- target branch, called "current branch"

If the user gave both names, use them directly after verifying they exist.

If the user did not give names, inspect the repository:

```bash
git branch --show-current
git branch --format='%(refname:short)'
```

When resolving the specified branch automatically, inspect local branches relative to the current branch:

- it is not the current branch
- it is not merged into the current branch
- `git rev-list --count CURRENT_BRANCH..BRANCH` is at least `1`

If there are multiple unmerged branches in the repository, narrow them to the branches that have commits after the current branch by using the `CURRENT_BRANCH..BRANCH` ahead count above.

If exactly one local branch satisfies these conditions, auto-select it as the source branch and continue without asking:

- source branch = that branch
- target branch = current branch

If more than one branch has commits after the current branch, stop and ask the user to specify which one should be the source branch. Target branch remains the current branch unless the user states otherwise.

If no branch has commits after the current branch, stop and ask the user for the source branch name.

### 2. Preflight checks

Verify the repository and branch state before merging:

```bash
git rev-parse --show-toplevel
git branch --show-current
git show-ref --verify --quiet refs/heads/<source-branch>
git show-ref --verify --quiet refs/heads/<target-branch>
```

The merge must run from a worktree currently checked out on the target branch. If the current worktree is not on the target branch, stop and tell the user to switch first.

### 3. Dirty-check both branches

Run the bundled script:

```bash
scripts/merge_branch_into_current.sh [source-branch] [target-branch]
```

The script must:

- inspect `git worktree list --porcelain`
- find any active worktree checked out on the source or target branch
- run `git status --short` inside each matching worktree
- abort if either branch has uncommitted tracked or untracked changes

If a matching branch has no active worktree, treat it as clean because Git cannot hold uncommitted state for that branch without a checked-out worktree.

When aborting, clearly report which branch and which worktree path is dirty, and tell the user to整理 or commit/stash those changes before retrying.

### 4. Merge

If both branches are clean, run:

```bash
git merge --no-ff <source-branch>
```

This preserves a merge commit even when fast-forward would be possible.

If merge conflicts occur:

- stop immediately
- report the conflicted files from `git status --short`
- do not auto-resolve unless the user asks

### 5. Report result

On success, report:

- source branch
- target branch
- resulting merge commit SHA from `git rev-parse HEAD`

## Resources

### scripts/

- `merge_branch_into_current.sh`: resolves branches when possible, checks worktree cleanliness for the source and target branches, and runs `git merge --no-ff`.
